#!/usr/bin/env python3
"""Record real browser actions and synchronize telemetry to decoded video.

The v5 workflow is retained; clocks, pointer pacing, assertions, context
selection and failure handling are repaired. A brief sync marker is pre-roll
only and is removed from the delivered video, never from the actual UI flow.
"""
import argparse
import json
import math
import shutil
from pathlib import Path

import cv2
from playwright.sync_api import sync_playwright

TELEMETRY = r"""(() => {
  if (window.__cinematicInstalled) return;
  window.__cinematicInstalled = true;
  for (const type of ['pointermove','pointerdown','pointerup']) {
    addEventListener(type, e => {
      const el = e.target instanceof Element ? e.target : document.documentElement;
      window.__cinematicEvent({epoch:(performance.timeOrigin+performance.now())/1000,
        type,x:e.clientX,y:e.clientY,buttons:e.buttons,cursor:getComputedStyle(el).cursor,
        tag:el.tagName,role:el.getAttribute('role')||''}).catch(()=>{});
    }, true);
  }
})();"""


def resolve(page, action, prefix=''):
    names = action.get(prefix+'selectors') or [action.get(prefix+'selector')]
    if not any(names):
        raise ValueError(f'{prefix}selector/selectors is required')
    last_error = None
    for name in names:
        if not name:
            continue
        try:
            loc = page.locator(name)
            loc.first.wait_for(state='visible',timeout=action.get('timeout_ms',10000))
            if loc.count() != 1:
                raise ValueError(f'Ambiguous selector ({loc.count()} matches): {name}')
            return loc, name
        except Exception as e:
            last_error = e
    raise ValueError(f'No unique visible target: {names}; {last_error}')


def box_for(locator, viewport, allow_scroll=False):
    box = locator.bounding_box()
    def inside(b):
        return b and b['x'] >= -.5 and b['y'] >= -.5 and b['x']+b['width'] <= viewport['width']+.5 and b['y']+b['height'] <= viewport['height']+.5
    if not inside(box) and allow_scroll:
        locator.scroll_into_view_if_needed()
        box = locator.bounding_box()
    if not inside(box):
        raise ValueError('Target is clipped/off-screen. Add an explicit scroll or set allow_scroll for this action.')
    return box


def visible_context(page):
    loc = page.locator('dialog[open], [role="dialog"]:visible, [aria-modal="true"]:visible')
    return loc.first.bounding_box() if loc.count() else None


def framing_context(page, action, viewport):
    """Measure explicitly required real controls; missing/clipped context fails."""
    result = []
    for selector in action.get('camera_context_selectors', []):
        locator, used = resolve(page, {'selector':selector,'timeout_ms':action.get('timeout_ms',10000)})
        result.append({'selector':used,'bounds':box_for(locator,viewport)})
    return result


def detect_video_offset(path):
    """Find the first decoded frame after magenta -> green sync pre-roll."""
    cap = cv2.VideoCapture(str(path))
    if not cap.isOpened():
        raise ValueError('Raw video is unreadable')
    fps = cap.get(cv2.CAP_PROP_FPS)
    w,h = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)),int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    state = 0
    index = 0
    try:
        while True:
            ok, frame = cap.read()
            if not ok:
                break
            b,g,r = frame[8:36,8:36].mean(axis=(0,1))
            magenta = b>180 and r>180 and g<70
            green = g>180 and r<70 and b<70
            if magenta:
                state = 1
            elif state == 1 and green:
                state = 2
            elif state == 2 and not green:
                return {'video_offset':index/fps,'capture_fps':fps,'record_size':{'width':w,'height':h},
                        'sync_method':'decoded magenta-green pre-roll marker',
                        'sync_quantization_seconds':1/fps,'sync_frame':index}
            index += 1
    finally:
        cap.release()
    raise ValueError('Synchronization marker was not decoded. Do not render unaligned telemetry.')


def assert_result(page, assertion):
    loc = page.locator(assertion['selector'])
    if 'scroll_min' in assertion:
        value = loc.evaluate('(el)=>el.scrollTop')
        if value < assertion['scroll_min']:
            raise AssertionError(f'Scroll only reached {value}; expected {assertion["scroll_min"]}')
        return {'scroll_top':value}
    state = assertion.get('state','visible')
    loc.wait_for(state=state,timeout=assertion.get('timeout_ms',10000))
    if 'text' in assertion and assertion['text'] not in loc.inner_text():
        raise AssertionError('Expected text did not appear')
    return {'state':state}


def record(plan_path, out, browser_path=None, headed=False):
    plan_path, out = Path(plan_path).resolve(),Path(out).resolve()
    plan = json.loads(plan_path.read_text())
    viewport = plan.get('viewport',{'width':1440,'height':900})
    if any(not isinstance(viewport.get(k),int) or viewport[k]<200 or viewport[k]%2 for k in ('width','height')):
        raise ValueError('Viewport width and height must be even integers >= 200')
    scale = float(plan.get('capture_scale',2))
    out.mkdir(parents=True,exist_ok=True)
    if (out/'events.json').exists() or (out/'raw.webm').exists():
        raise FileExistsError('Use a fresh output directory; existing recordings are not overwritten.')
    raw_dir = out/'raw'
    raw_dir.mkdir(exist_ok=True)
    events, pointer, assertions = [],[],[]
    meta = {'schema_version':8,'viewport':viewport,'capture_scale':scale,
            'capture_scale_note':'Browser DPR only; actual video resolution is measured after capture.',
            'source_url':plan.get('url','local-fixture'),'fixture':not bool(plan.get('url')),
            'status':'recording','events':events,'pointer':pointer,'assertions':assertions}
    failure = None
    start_epoch = None
    with sync_playwright() as pw:
        launch = {'headless':not headed}
        if browser_path:
            launch['executable_path'] = browser_path
        browser = pw.chromium.launch(**launch)
        ctx = browser.new_context(viewport=viewport,device_scale_factor=scale,
                                  record_video_dir=str(raw_dir),record_video_size=viewport)
        ctx.expose_binding('__cinematicEvent',lambda source,data:pointer.append(data))
        ctx.add_init_script(TELEMETRY)
        page = ctx.new_page()
        video = page.video
        try:
            if plan.get('html_file'):
                html = Path(plan['html_file'])
                if not html.is_absolute():
                    html = plan_path.parent/html
                page.goto(html.resolve().as_uri())
            else:
                page.goto(plan['url'],wait_until='domcontentloaded',timeout=plan.get('timeout_ms',45000))
            page.wait_for_timeout(plan.get('settle_ms',1500))
            # This visible calibration is outside the delivered timeline.
            page.evaluate("""() => {const el=document.createElement('div'); el.id='cinematic-sync';
              el.style='position:fixed;left:0;top:0;width:48px;height:48px;background:rgb(255,0,255);z-index:2147483647;pointer-events:none';
              document.documentElement.appendChild(el)}""")
            page.wait_for_timeout(320)
            page.evaluate("document.getElementById('cinematic-sync').style.background='rgb(0,255,0)'")
            page.wait_for_timeout(320)
            start_epoch = page.evaluate("""() => {document.getElementById('cinematic-sync').remove();
                return (performance.timeOrigin+performance.now())/1000} """)
            def now():
                return page.evaluate('()=>(performance.timeOrigin+performance.now())/1000')-start_epoch
            def emit(typ, **data):
                item = {'t':now(),'type':typ,**data}
                events.append(item)
                return item
            current = [viewport['width']/2,viewport['height']/2]
            def move(x,y,ms=650):
                old = current.copy()
                steps = max(1,round(ms/20))
                for i in range(1,steps+1):
                    u=i/steps; u=u*u*(3-2*u)
                    page.mouse.move(old[0]+(x-old[0])*u,old[1]+(y-old[1])*u)
                    page.wait_for_timeout(ms/steps)
                current[:]=[x,y]
            emit('start')
            page.mouse.move(*current)
            page.wait_for_timeout(plan.get('intro_ms',1200))
            for n,action in enumerate(plan.get('actions',[])):
                kind = action['type']
                label = action.get('label',f'{n+1}: {kind}')
                if kind == 'wait':
                    page.wait_for_timeout(action.get('ms',800)); continue
                if kind == 'key':
                    page.keyboard.press(action['key'])
                    if action['key']=='Escape' or action.get('shot')=='reset':
                        emit('reset',label=label)
                    else:
                        emit('key',key=action['key'],label=label)
                elif kind == 'scroll':
                    loc,used=resolve(page,action)
                    box=box_for(loc,viewport)
                    x,y=box['x']+box['width']/2,box['y']+box['height']/2
                    move(x,y)
                    emit('lock',label=label,bounds=visible_context(page) or box)
                    steps=max(1,round(action.get('scroll_ms',1200)/40))
                    previous=0
                    for i in range(1,steps+1):
                        u=i/steps; u=u*u*(3-2*u)
                        total=round(action.get('dy',600)*u)
                        page.mouse.wheel(0,total-previous)
                        previous=total
                        page.wait_for_timeout(action.get('scroll_ms',1200)/steps)
                    page.wait_for_timeout(action.get('after_ms',900))
                    emit('unlock',label=label)
                elif kind == 'drag':
                    origin,_=resolve(page,action,'from_'); destination,_=resolve(page,action,'to_')
                    a,b=box_for(origin,viewport),box_for(destination,viewport)
                    union={'x':min(a['x'],b['x']),'y':min(a['y'],b['y'])}
                    union['width']=max(a['x']+a['width'],b['x']+b['width'])-union['x']
                    union['height']=max(a['y']+a['height'],b['y']+b['height'])-union['y']
                    move(a['x']+a['width']/2,a['y']+a['height']/2)
                    emit('follow_start',bounds=union,zoom=action.get('zoom'),label=label)
                    page.mouse.down()
                    move(b['x']+b['width']/2,b['y']+b['height']/2,action.get('drag_ms',1100))
                    page.mouse.up();emit('follow_end',label=label)
                elif kind in ('click','hover','fill'):
                    loc,used=resolve(page,action)
                    box=box_for(loc,viewport,action.get('allow_scroll',False))
                    x,y=box['x']+box['width']/2,box['y']+box['height']/2
                    move(x,y,action.get('move_ms',650))
                    page.wait_for_timeout(action.get('pre_ms',300))
                    camera_box=box
                    if action.get('camera_selector') and not action.get('camera_after'):
                        camera_box=page.locator(action['camera_selector']).bounding_box()
                    event=emit('focus',x=x,y=y,bounds=camera_box,shot=action.get('shot','focus'),zoom=action.get('zoom'),label=label,selector=used)
                    if not action.get('camera_after'):
                        event['context_bounds']=framing_context(page,action,viewport)
                        event['context_sample_t']=now()
                    event['safe_margin']=action.get('safe_margin',12)
                    prior_context=visible_context(page)
                    if kind=='click':
                        page.mouse.click(x,y)
                    elif kind=='fill':
                        page.mouse.click(x,y);emit('lock',label=label)
                        loc.fill(action.get('text',''));emit('unlock',label=label)
                    page.wait_for_timeout(action.get('context_probe_ms',220))
                    if action.get('camera_after'):
                        target=page.locator(action['camera_selector'])
                        target.wait_for(state='visible')
                        event['bounds']=target.bounding_box()
                        event['context_bounds']=framing_context(page,action,viewport)
                        event['context_sample_t']=now()
                        event['lead']=0.  # Don't crop a dialog before the close action.
                    context=visible_context(page)
                    if kind=='click' and context and not prior_context:
                        emit('context',bounds=context,label=label)
                else:
                    raise ValueError(f'Unknown action type: {kind}')
                if kind!='scroll':
                    page.wait_for_timeout(action.get('after_ms',1000))
                if action.get('assert'):
                    result=assert_result(page,action['assert'])
                    assertions.append({'action':n,'label':label,'t':now(),'passed':True,**result})
                page.screenshot(path=str(out/f'action-{n+1:02d}.png'))
                emit('checkpoint',action=n,label=label)
            emit('end')
            page.wait_for_timeout(plan.get('tail_ms',2000))
            meta['duration']=now()
            meta['status']='complete'
        except Exception as e:
            failure=e
            meta.update(status='failed',error=str(e))
            try:
                page.screenshot(path=str(out/'failure.png'))
            except Exception:
                pass
        finally:
            ctx.close()
            browser.close()
            shutil.copy2(video.path(),out/'raw.webm')
    if start_epoch is not None:
        meta['pointer']=[dict(p,t=p['epoch']-start_epoch) for p in pointer if p['epoch']>=start_epoch]
        for p in meta['pointer']:
            p.pop('epoch',None)
    if not failure:
        try:
            meta.update(detect_video_offset(out/'raw.webm'))
        except Exception as e:
            failure=e
            meta.update(status='failed',error=str(e))
    (out/'events.json').write_text(json.dumps(meta,indent=2)+'\n')
    if failure:
        raise RuntimeError(f'Recording failed; diagnostics saved in {out}: {failure}') from failure
    return meta


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('plan');ap.add_argument('--out',default='output')
    ap.add_argument('--browser');ap.add_argument('--headed',action='store_true')
    a=ap.parse_args()
    m=record(a.plan,a.out,a.browser,a.headed)
    print(json.dumps({k:m[k] for k in ('status','duration','record_size','capture_fps','video_offset','assertions')},indent=2))


if __name__=='__main__':
    main()
