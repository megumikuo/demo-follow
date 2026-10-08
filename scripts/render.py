#!/usr/bin/env python3
import argparse
import json
import math
import subprocess
from pathlib import Path

import cv2
import numpy as np


from camera import Camera, target_pose
import imageio_ffmpeg
from timeline import Timeline
from style import PRESETS, PointerMotion, Frame, draw_pointer, draw_click, color


def smootherstep(x):
    x = max(0., min(1., x))
    return x*x*x*(x*(x*6.-15.)+10.)


def normalize_pointer(meta):
    points = meta.get('pointer') or []
    if points:
        return points
    # Compatibility with older recordings.
    return [
        {'t': e['t'], 'x': e.get('x', 0), 'y': e.get('y', 0), 'cursor': 'default', 'type': 'pointermove'}
        for e in meta.get('events', []) if e.get('type') in ('start', 'focus', 'context', 'follow_start', 'follow_end', 'end')
    ]


def pointer_at(t, points, default):
    if not points:
        return default[0], default[1], 'default'
    if t <= points[0]['t']:
        p = points[0]
        return float(p['x']), float(p['y']), p.get('cursor', 'default')
    if t >= points[-1]['t']:
        p = points[-1]
        return float(p['x']), float(p['y']), p.get('cursor', 'default')
    lo = 0
    hi = len(points) - 1
    while lo + 1 < hi:
        mid = (lo + hi) // 2
        if points[mid]['t'] <= t:
            lo = mid
        else:
            hi = mid
    a, b = points[lo], points[hi]
    span = max(1e-6, float(b['t']) - float(a['t']))
    # Do not drift across an idle gap; only interpolate recorded movement.
    effective_start = max(float(a['t']), float(b['t']) - .06) if span > .12 else float(a['t'])
    u = max(0., min(1., (t-effective_start)/max(1e-6,float(b['t'])-effective_start)))
    x = float(a['x']) + (float(b['x']) - float(a['x'])) * u
    y = float(a['y']) + (float(b['y']) - float(a['y'])) * u
    cursor = b.get('cursor') or a.get('cursor') or 'default'
    tag = (b.get('tag') or a.get('tag') or '').upper()
    role = (b.get('role') or a.get('role') or '').lower()
    if cursor in ('auto', 'default') and (tag in ('BUTTON','A') or role in ('button','link')):
        cursor = 'pointer'
    return x, y, cursor


def click_age(t, points):
    for p in reversed(points):
        if p.get('type') == 'pointerdown':
            age = t - float(p['t'])
            if 0.0 <= age <= 0.34:
                return age
            if age > 0.34:
                break
    return None


def main():
    ap = argparse.ArgumentParser(description='Style and pace a real browser recording with a stable semantic camera.')
    ap.add_argument('video')
    ap.add_argument('events')
    ap.add_argument('--out-dir', default='output')
    ap.add_argument('--fps', type=int, default=60)
    ap.add_argument('--preset', choices=PRESETS, default='studio')
    ap.add_argument('--cursor-style', choices=['auto','bold','touch','ring'])
    ap.add_argument('--cursor-size', type=float)
    ap.add_argument('--cursor-color')
    ap.add_argument('--click-effect', choices=['ripple','pulse','spark','none'])
    ap.add_argument('--click-color')
    ap.add_argument('--click-duration', type=float, help='Click animation duration in output seconds, 0.15–2.')
    ap.add_argument('--cursor-smoothing', dest='smoothing', type=float, help='Source-time smoothing window, 0–0.1 seconds.')
    ap.add_argument('--rotate-cursor', action=argparse.BooleanOptionalAction, default=None)
    ap.add_argument('--hide-idle', action=argparse.BooleanOptionalAction, default=None)
    ap.add_argument('--speed', type=float, help='Playback speed, 0.25–3; 1 is real time.')
    ap.add_argument('--speed-segments', type=Path, help='JSON array of source-time start/end/speed regions.')
    ap.add_argument('--transition', type=float)
    ap.add_argument('--background', choices=['graphite','aurora','sunset','none'])
    ap.add_argument('--canvas', help='Output WIDTHxHEIGHT; defaults to 1920x1080 with a frame.')
    ap.add_argument('--padding', type=int, default=72)
    ap.add_argument('--corner-radius', type=int, default=26)
    ap.add_argument('--mp4-only', action='store_true', help='Skip WebM for quick preview renders.')
    args = ap.parse_args()
    config = dict(PRESETS[args.preset])
    for key in config:
        value = getattr(args, key, None)
        if value is not None:
            config[key] = value
    if not 1 <= args.fps <= 120 or not .5 <= config['cursor_size'] <= 3:
        ap.error('FPS must be 1–120 and cursor size must be 0.5–3.')
    if not 0 <= args.padding <= 400 or not 0 <= args.corner_radius <= 160:
        ap.error('Padding must be 0–400; corner radius must be 0–160.')
    color(config['cursor_color']); color(config['click_color'])
    if not .15<=config['click_duration']<=2 or not 0<=config['smoothing']<=.1:
        ap.error('Click duration must be 0.15–2; cursor smoothing must be 0–0.1.')
    canvas = None
    if args.canvas:
        try:
            canvas = tuple(int(v) for v in args.canvas.lower().split('x'))
            if len(canvas)!=2 or any(v%2 or not 128<=v<=4096 for v in canvas):
                raise ValueError()
        except ValueError:
            ap.error('Canvas must be WIDTHxHEIGHT, even dimensions between 128 and 4096.')
    out = Path(args.out_dir)
    out.mkdir(parents=True, exist_ok=True)
    meta = json.loads(Path(args.events).read_text())
    if meta.get('status') != 'complete' or 'video_offset' not in meta:
        raise ValueError('Use a successful synchronized capture; uncalibrated telemetry cannot be delivered.')
    viewport = meta['viewport']
    w,h = int(viewport['width']),int(viewport['height'])
    frame_style = Frame(viewport,config['background'],canvas,args.padding,args.corner_radius)
    ow,oh = frame_style.width,frame_style.height
    if ow%2 or oh%2:
        raise ValueError('Output dimensions must be even for yuv420p.')
    cap = cv2.VideoCapture(args.video)
    if not cap.isOpened():
        raise ValueError('Cannot open source video')
    raw_fps = cap.get(cv2.CAP_PROP_FPS)
    sw,sh = cap.get(cv2.CAP_PROP_FRAME_WIDTH),cap.get(cv2.CAP_PROP_FRAME_HEIGHT)
    raw_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    offset,duration = float(meta['video_offset']),float(meta['duration'])
    if min(raw_fps,sw,sh,duration)<=0 or offset<0 or offset+duration>raw_frames/raw_fps+.1:
        raise ValueError('Recording duration/offset does not fit the decoded video')
    regions = json.loads(args.speed_segments.read_text()) if args.speed_segments else []
    timeline = Timeline(duration,config['speed'],regions)
    camera = Camera(meta['events'],viewport,transition=config['transition'])
    points = normalize_pointer(meta)
    motion = PointerMotion(points,lambda t:pointer_at(t,points,(w/2,h/2)),config['smoothing'])
    ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
    mp4,webm,poster = out/'demo.mp4',out/'demo.webm',out/'poster.jpg'
    proc = subprocess.Popen([ffmpeg,'-y','-v','error','-f','rawvideo','-pixel_format','bgr24',
        '-video_size',f'{ow}x{oh}','-framerate',str(args.fps),'-i','-',
        '-an','-c:v','libx264','-crf','18','-preset','medium','-pix_fmt','yuv420p',
        '-movflags','+faststart',str(mp4)],stdin=subprocess.PIPE)
    count = int(math.ceil(timeline.duration*args.fps))
    raw_index,frame,track = -1,None,[]
    clicks = [(p,timeline.output_at(p['t'])) for p in points if p.get('type')=='pointerdown']
    try:
        for i in range(count):
            output_t = i/args.fps
            t = timeline.source_at(output_t)
            wanted = min(raw_frames-1,int((t+offset)*raw_fps+1e-6))
            while raw_index<wanted:
                ok,next_frame = cap.read()
                if not ok:
                    raise RuntimeError(f'Source decode ended early at frame {raw_index+1}')
                frame,raw_index = next_frame,raw_index+1
            pose = camera.at(t)
            matrix = np.array([[pose.zoom*w/sw,0.,pose.x],[0.,pose.zoom*h/sh,pose.y]],dtype=np.float64)
            core = cv2.warpAffine(frame,matrix,(w,h),flags=cv2.INTER_LANCZOS4,borderMode=cv2.BORDER_REPLICATE)
            composed = frame_style.compose(core)
            z = frame_style.scale*pose.zoom
            tx,ty = frame_style.x+frame_style.scale*pose.x,frame_style.y+frame_style.scale*pose.y
            recent_age = None
            for click,click_t in clicks:
                age = output_t-click_t
                if 0<=age<=config['click_duration']:
                    draw_click(composed,z*click['x']+tx,z*click['y']+ty,age,config['click_effect'],config['click_color'],config['click_duration'])
                    recent_age = age if recent_age is None else min(recent_age,age)
            px,py,cursor = motion.at(t)
            before = motion.at(t-.04); after = motion.at(t+.04)
            rotation = float(np.clip((after[0]-before[0])/.08*.035,-12,12)) if config['rotate_cursor'] else 0.
            opacity = motion.opacity(t,config['hide_idle'])
            draw_pointer(composed,z*px+tx,z*py+ty,cursor,config,opacity,rotation,recent_age)
            proc.stdin.write(composed.tobytes())
            track.append({'t':round(output_t,6),'source_t':round(t,6),'zoom':z,'tx':tx,'ty':ty,
                          'source_frame':wanted,'cursor_x':z*px+tx,'cursor_y':z*py+ty,'cursor_opacity':opacity})
            if i==min(count-1,round(max(0,timeline.duration-1.7)*args.fps)):
                cv2.imwrite(str(poster),composed)
    finally:
        cap.release()
        proc.stdin.close()
    if proc.wait()!=0:
        raise RuntimeError('MP4 encoding failed')
    if not args.mp4_only:
        subprocess.run([ffmpeg,'-y','-v','error','-i',str(mp4),'-an','-c:v','libvpx-vp9',
                        '-crf','30','-b:v','0','-row-mt','1',str(webm)],check=True)
    transitions = camera.serializable()
    for tr in transitions:
        tr['source_start'],tr['source_end'] = tr['start'],tr['end']
        tr['start'],tr['end'] = timeline.output_at(tr['start']),timeline.output_at(tr['end'])
    report = {'output_fps':args.fps,'capture_fps':raw_fps,'capture_resolution':[int(sw),int(sh)],
              'output_resolution':[ow,oh],'viewport_resolution':[w,h],'frames':count,'duration':count/args.fps,
              'source_duration':duration,'video_offset':offset,'transitions':transitions,
              'holds_protected_end':camera.end_held,
              'locks':[(timeline.output_at(lo),timeline.output_at(hi)) for lo,hi in camera.locks],
              'timeline':timeline.serializable(),'preset':args.preset,'style':config,
              'frame':{'x':frame_style.x,'y':frame_style.y,'width':frame_style.w,'height':frame_style.h,'scale':frame_style.scale},
              'framing':[dict(label=e.get('label'),sample_t=e.get('context_sample_t',e['t']),
                              event_t=e['t'],bounds=e['bounds'],context_bounds=e['context_bounds'],
                              safe_margin=e.get('safe_margin',12),target=target_pose(e,viewport).values())
                         for e in meta['events'] if e.get('context_bounds')],
              'source_recording':'unchanged; decorations, camera and pacing are post-processing'}
    (out/'render-report.json').write_text(json.dumps(report,indent=2)+'\n')
    (out/'camera-track.json').write_text(json.dumps(track)+'\n')
    print(json.dumps(report,indent=2))


if __name__ == '__main__':
    main()
