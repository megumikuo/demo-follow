#!/usr/bin/env python3
"""Decode delivery frames, inspect camera motion, and emit a review contact sheet."""
import argparse
import json
import math
from pathlib import Path
import cv2
import numpy as np


def check_framing(track, report, events):
    """Check measured required controls against the actual video-card rectangle."""
    f=report.get('frame',{'x':0,'y':0,'width':report['viewport_resolution'][0],
                           'height':report['viewport_resolution'][1],'scale':1.})
    checked,steady,minimum,balance=0,0,float('inf'),0.
    for intent in report.get('framing',[]):
        start=intent['sample_t']
        terminal_types=('focus','context','reset') if report.get('holds_protected_end') else ('focus','context','reset','end')
        end=min((e['t'] for e in events['events'] if e['t']>start and
                 e['type'] in terminal_types),default=report['source_duration'])
        boxes=[intent['bounds'],*(b.get('bounds',b) for b in intent['context_bounds'])]
        top=min(b['y'] for b in boxes);bottom=max(b['y']+b['height'] for b in boxes)
        target=intent['target'];expected=np.array([target[0]*f['scale'],f['x']+target[1]*f['scale'],f['y']+target[2]*f['scale']])
        for p in track:
            if not start<=p['source_t']<end:continue
            checked+=1
            for b in boxes:
                left=p['zoom']*b['x']+p['tx'];right=p['zoom']*(b['x']+b['width'])+p['tx']
                upper=p['zoom']*b['y']+p['ty'];lower=p['zoom']*(b['y']+b['height'])+p['ty']
                clearance=min(left-f['x'],upper-f['y'],f['x']+f['width']-right,f['y']+f['height']-lower)
                minimum=min(minimum,clearance)
                if clearance < -1e-6:raise AssertionError(f'Required control/region clipped: {intent["label"]}, {p["t"]:.3f}s')
            if np.allclose([p['zoom'],p['tx'],p['ty']],expected,atol=1e-7,rtol=0):
                steady+=1
                center=p['zoom']*(top+bottom)/2+p['ty']
                balance=max(balance,abs(center-(f['y']+f['height']/2)))
    return {'checked_frames':checked,'steady_frames':steady,'clipped_frames':0,
            'minimum_region_clearance_px':None if not checked else minimum,
            'max_steady_vertical_center_error_px':balance,
            'basis':'Measured source DOM bounds projected through every applicable output transform; pixels inspected separately.'}


def inspect(out):
    out=Path(out)
    track=json.loads((out/'camera-track.json').read_text())
    report=json.loads((out/'render-report.json').read_text())
    events=json.loads((out/'events.json').read_text())
    cap=cv2.VideoCapture(str(out/'demo.mp4'))
    fps=cap.get(cv2.CAP_PROP_FPS)
    w,h=int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)),int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    if not cap.isOpened() or fps<=0:
        raise ValueError('MP4 could not be decoded')
    sample_times=[0.,max(0,len(track)/fps-.4)]
    def output_time(source_t):
        for span in report.get('timeline',[]):
            if source_t<=span['source_end']:
                return span['output_start']+(source_t-span['source_start'])/span['speed']
        return source_t if not report.get('timeline') else report['duration']
    sample_times += [output_time(e['t']) for e in events['events'] if e['type']=='checkpoint']
    sample_times += [(lo+hi)/2 for lo,hi in report['locks']]
    sample_times += [(tr['start']+tr['end'])/2 for tr in report['transitions']]
    sample_times=sorted(set(sample_times))
    if len(sample_times)>18:
        sample_times=[sample_times[i] for i in np.linspace(0,len(sample_times)-1,18).astype(int)]
    sample_indices={min(len(track)-1,round(t*fps)):t for t in sample_times if t<len(track)/fps}
    samples=[]
    n=0
    while True:
        ok,frame=cap.read()
        if not ok:break
        if n in sample_indices:
            scale=min(480/w,300/h)
            small=cv2.resize(frame,(round(w*scale),round(h*scale)),interpolation=cv2.INTER_AREA)
            tile=np.full((334,480,3),248,np.uint8)
            x,y=(480-small.shape[1])//2,(300-small.shape[0])//2
            tile[y:y+small.shape[0],x:x+small.shape[1]]=small
            cv2.putText(tile,f'{n/fps:.2f}s',(12,323),cv2.FONT_HERSHEY_SIMPLEX,.6,(45,35,30),1,cv2.LINE_AA)
            samples.append(tile)
            cv2.imwrite(str(out/f'frame-{n:04d}.jpg'),frame)
        n+=1
    cap.release()
    if n!=len(track) or n!=report['frames']:
        raise AssertionError(f'Decoded frame count {n} != camera frames {len(track)}')
    columns=3;rows=math.ceil(len(samples)/columns)
    sheet=np.full((rows*334,columns*480,3),248,np.uint8)
    for i,tile in enumerate(samples):sheet[(i//columns)*334:(i//columns+1)*334,(i%columns)*480:(i%columns+1)*480]=tile
    cv2.imwrite(str(out/'contact-sheet.jpg'),sheet)
    a=np.array([[p['zoom'],p['tx'],p['ty']] for p in track])
    # Measure camera-induced motion at all four source corners, in output pixels.
    vw,vh=report.get('viewport_resolution',[w,h])
    trajectories=np.stack([a[:,1:]+a[:,:1]*np.array(corner) for corner in ((0,0),(vw,0),(0,vh),(vw,vh))],axis=1)
    delta=np.diff(trajectories,axis=0)
    max_step=float(np.linalg.norm(delta,axis=2).max())
    max_accel=float(np.linalg.norm(np.diff(delta,axis=0),axis=2).max()) if len(delta)>1 else 0.
    reversals=0
    for tr in report['transitions']:
        lo,hi=max(0,math.ceil(tr['start']*fps)),min(n-1,math.floor(tr['end']*fps))
        d=delta[lo:hi]
        for corner in range(4):
            for axis in range(2):
                v=d[:,corner,axis];v=v[np.abs(v)>1e-7]
                reversals+=int(np.count_nonzero(v[1:]*v[:-1]<0))
    lock_drift=[]
    for start,end in report['locks']:
        held=a[math.ceil(start*fps):math.floor(end*fps)+1]
        lock_drift.append(float(np.ptp(held,axis=0).max()) if len(held) else 0.)
    result={'decoded_frames':n,'fps':fps,'resolution':[w,h],'duration':n/fps,
            'action_assertions_passed':len([x for x in events['assertions'] if x['passed']]),
            'camera_max_corner_step_px':max_step,'camera_max_corner_acceleration_px_per_frame2':max_accel,
            'camera_direction_reversals_inside_transitions':reversals,'camera_max_lock_drift':max(lock_drift,default=0.),
            'visual_review':'Contact sheet generated; a person or agent must inspect frames before claiming visual quality.',
            'capture_fps':report['capture_fps'],'output_fps':report['output_fps'],
            'preset':report.get('preset','legacy'),'style':report.get('style',{}),
            'source_duration':report.get('source_duration',n/fps),
            'framing':check_framing(track,report,events),
            'note':'Camera metrics do not prove absence of source-page animation, compression artifacts, or capture judder.'}
    if reversals or max(lock_drift,default=0.)>1e-9 or max_step>35 or max_accel>3:
        raise AssertionError(f'Camera regression: {result}')
    (out/'validation.json').write_text(json.dumps(result,indent=2)+'\n')
    return result


if __name__=='__main__':
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('output');a=ap.parse_args()
    print(json.dumps(inspect(a.output),indent=2))
