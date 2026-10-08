"""Deterministic semantic camera, in output-space affine coordinates.

Interpolate valid transforms instead of clamping an animated crop every frame.
This keeps the path inside the source and avoids edge-clamp direction changes.
No pointer samples enter camera planning.
"""
from dataclasses import dataclass
import math


def ease(u):
    u = max(0., min(1., u))
    return u * u * u * (u * (u * 6. - 15.) + 10.)


@dataclass(frozen=True)
class Pose:
    zoom: float = 1.
    x: float = 0.
    y: float = 0.

    def blend(self, other, u):
        s = ease(u)
        return Pose(*(a + (b - a) * s for a, b in zip(self.values(), other.values())))

    def values(self):
        return (self.zoom, self.x, self.y)


@dataclass(frozen=True)
class Transition:
    start: float
    end: float
    before: Pose
    after: Pose
    reason: str


def target_pose(event, viewport):
    w, h = viewport['width'], viewport['height']
    if event.get('type') in ('reset', 'end') or event.get('shot') == 'reset':
        return Pose()
    box = event.get('bounds')
    shot = event.get('shot', event.get('type', 'focus'))
    if box:
        bw, bh = max(1., box['width']), max(1., box['height'])
        x, y = box['x'] + bw / 2., box['y'] + bh / 2.
        pad = 1.12 if shot == 'context' else 1.45
        fit = min(w / (bw * pad), h / (bh * pad))
        preferred = (1.42 if shot == 'context' else 1.6)
        # A nearly viewport-sized dialog must be allowed to remain at 1x.
        z = max(1., min(float(event.get('zoom') or preferred), fit))
    else:
        x, y = event.get('x', w / 2.), event.get('y', h / 2.)
        z = float(event.get('zoom') or 1.5)
    z = max(1., min(2., z))
    contexts = event.get('context_bounds') or []
    if box and contexts:
        boxes = [box, *(entry.get('bounds', entry) for entry in contexts)]
        left = min(b['x'] for b in boxes)
        top = min(b['y'] for b in boxes)
        right = max(b['x']+b['width'] for b in boxes)
        bottom = max(b['y']+b['height'] for b in boxes)
        if left < 0 or top < 0 or right > w or bottom > h:
            raise ValueError('Required framing context is clipped in the source recording')
        margin = float(event.get('safe_margin', 12.))
        if not math.isfinite(margin) or not 0 <= margin < min(w,h)/2:
            raise ValueError('safe_margin must be finite and smaller than half the viewport')
        # Keep the primary region horizontally centered; balance the complete
        # vertical composition, including its required controls. A protected
        # region limits zoom before planning, never by clamping moving frames.
        y = (top+bottom)/2.
        preferred_z = z
        z = max(1., min(z, (w-2*margin)/max(1.,right-left),
                       (h-2*margin)/max(1.,bottom-top)))
        for _ in range(2):
            lo_x, hi_x = max((1-z)*w,margin-z*left), min(0.,w-margin-z*right)
            lo_y, hi_y = max((1-z)*h,margin-z*top), min(0.,h-margin-z*bottom)
            if lo_x <= hi_x+1e-8 and lo_y <= hi_y+1e-8:
                return Pose(z,max(lo_x,min(hi_x,w/2-z*x)),
                            max(lo_y,min(hi_y,h/2-z*y)))
            # A source control near an edge limits the achievable margin.
            # Relax that margin to its original source clearance, then refit;
            # keep meaningful zoom rather than unnecessarily resetting to 1x.
            margin = min(margin,left,top,w-right,h-bottom)
            z = max(1., min(preferred_z,(w-2*margin)/max(1.,right-left),
                           (h-2*margin)/max(1.,bottom-top)))
    return Pose(z, max((1. - z) * w, min(0., w / 2. - z * x)),
                max((1. - z) * h, min(0., h / 2. - z * y)))


class Camera:
    """Continuous quintic ramps with zero velocity/acceleration at joins.

    Hold composition between meaningful actions. Context events immediately
    following a click replace that click's brief button shot. Lock events hold
    the current composition, with ramps scheduled before the lock begins.
    Dense non-context targets are coalesced before planning, never interrupted
    halfway through a ramp. Explicit resets release to 1x. The end releases
    unprotected shots, but holds a protected, balanced final composition.
    """
    def __init__(self, events, viewport, transition=1.0, lead=.8):
        if transition <= 0 or not math.isfinite(transition):
            raise ValueError('transition must be finite and positive')
        self.transitions = []
        self.locks = []
        self.end_held = False
        intent = []
        lock_start = None
        for original in sorted(events, key=lambda e: e['t']):
            e = dict(original)
            t, typ = float(e['t']), e['type']
            if typ == 'end' and intent and intent[-1].get('context_bounds'):
                # Finish on the balanced protected composition. An automatic
                # final zoom-out would bring back the original empty margins.
                self.end_held = True
                continue
            if typ == 'lock':
                lock_start = t
                continue
            if typ == 'unlock':
                if lock_start is not None:
                    self.locks.append((lock_start, t))
                lock_start = None
                continue
            if typ not in ('focus', 'context', 'follow_start', 'reset', 'end'):
                continue
            if typ == 'context' and intent and intent[-1]['type'] == 'focus' and t-intent[-1]['t'] < .65:
                prior = intent.pop()
                e['t'] = prior['t']
            # Repeated semantic region: retain the composition instead of pulsing.
            if intent and target_pose(e, viewport) == target_pose(intent[-1], viewport):
                continue
            if intent and e['t'] - intent[-1]['t'] < transition and typ not in ('end', 'reset'):
                e['t'] = intent[-1]['t']
                intent[-1] = e
            else:
                intent.append(e)
        if lock_start is not None:
            self.locks.append((lock_start, math.inf))
        pose = Pose()
        last_end = 0.
        for e in intent:
            after = target_pose(e, viewport)
            if after == pose:
                continue
            reset = e['type'] in ('reset', 'end')
            start = max(last_end, float(e['t']) - (0. if reset else float(e.get('lead',lead))))
            end = start + transition
            for lock_lo, lock_hi in self.locks:
                if start < lock_hi and end > lock_lo:
                    # Move the whole transition before the lock when feasible;
                    # otherwise delay it until unlock. Never move during a lock.
                    if lock_lo - transition >= last_end and float(e['t']) <= lock_lo:
                        start, end = lock_lo-transition, lock_lo
                    else:
                        start, end = lock_hi, lock_hi+transition
            if not math.isfinite(start):
                continue
            self.transitions.append(Transition(start, end, pose, after, e['type']))
            pose, last_end = after, end

    def at(self, t):
        pose = Pose()
        for tr in self.transitions:
            if t < tr.start:
                return pose
            if t < tr.end:
                return tr.before.blend(tr.after, (t-tr.start)/(tr.end-tr.start))
            pose = tr.after
        return pose

    def serializable(self):
        return [{'start':t.start,'end':t.end,'before':t.before.values(),
                 'after':t.after.values(),'reason':t.reason} for t in self.transitions]
