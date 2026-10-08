"""Editable cursor, click treatment and framed backgrounds. No source UI is invented."""
import math
import cv2
import numpy as np

PRESETS = {
    'studio': dict(cursor_style='bold', cursor_size=1.2, cursor_color='#F5F8FF',
                   click_effect='ripple', click_color='#50D9E8', background='graphite',
                   speed=1., transition=1., hide_idle=True, smoothing=.025),
    'playful': dict(cursor_style='touch', cursor_size=1.35, cursor_color='#4EE4C4',
                    click_effect='spark', click_color='#FFBE66', background='aurora',
                    speed=1.1, transition=1., hide_idle=True, smoothing=.035),
    'punchy': dict(cursor_style='ring', cursor_size=1.1, cursor_color='#FFF6E7',
                   click_effect='pulse', click_color='#FFAF58', background='sunset',
                   speed=1.4, transition=.95, hide_idle=True, smoothing=.02),
    'classic': dict(cursor_style='auto', cursor_size=1., cursor_color='#F8F8F8',
                    click_effect='ripple', click_color='#2974AF', background='none',
                    speed=1., transition=1., hide_idle=False, smoothing=0.),
}
for _name,_preset in PRESETS.items():
    _preset['click_duration'] = .65
    _preset['rotate_cursor'] = _name == 'studio'


def ease(x):
    x = min(1., max(0., x))
    return x*x*x*(x*(x*6.-15.)+10.)


def color(hex_color):
    if len(hex_color) != 7 or not hex_color.startswith('#'):
        raise ValueError('Colors must use #RRGGBB')
    try:
        r, g, b = [int(hex_color[i:i+2], 16) for i in (1, 3, 5)]
    except ValueError as e:
        raise ValueError('Colors must use #RRGGBB') from e
    return b, g, r


class PointerMotion:
    def __init__(self, points, sample, smoothing=0.):
        self.points, self.sample, self.smoothing = points, sample, smoothing
        self.clicks = [p for p in points if p.get('type') == 'pointerdown']
        previous, self.moves = None, []
        for p in points:
            xy = (p['x'], p['y'])
            if previous is None or math.dist(xy, previous) > .25:
                self.moves.append(float(p['t']))
                previous = xy

    def at(self, t):
        x, y, kind = self.sample(t)
        if self.smoothing > 0:
            samples = [self.sample(t+k*self.smoothing) for k in (-2,-1,0,1,2)]
            weights = np.array([1.,4.,6.,4.,1.])/16.
            x = float(sum(p[0]*w for p,w in zip(samples, weights)))
            y = float(sum(p[1]*w for p,w in zip(samples, weights)))
            nearby = [p for p in self.clicks if abs(t-p['t']) < .1]
            if nearby:
                p = min(nearby, key=lambda p: abs(t-p['t']))
                pin = 1.-ease(abs(t-p['t'])/.1)
                x, y = x+(p['x']-x)*pin, y+(p['y']-y)*pin
        return x, y, kind

    def opacity(self, t, hide_idle):
        if not self.points or t < self.points[0]['t']:
            return 0.
        if not hide_idle:
            return 1.
        last = max((v for v in self.moves if v <= t), default=t)
        last = max(last, max((p['t'] for p in self.clicks if p['t'] <= t), default=last))
        return 1.-ease((t-last-1.1)/.3)


def blend_patch(image, patch, left, top):
    x0, y0 = max(0,left), max(0,top)
    x1, y1 = min(image.shape[1],left+patch.shape[1]), min(image.shape[0],top+patch.shape[0])
    if x1 <= x0 or y1 <= y0:
        return
    layer = patch[y0-top:y1-top,x0-left:x1-left]
    alpha = layer[:,:,3:4].astype(np.float32)/255.
    image[y0:y1,x0:x1] = np.clip(layer[:,:,:3]*alpha+image[y0:y1,x0:x1]*(1-alpha),0,255).astype(np.uint8)


def draw_click(image, x, y, age, effect, hex_color, duration=.65):
    if effect == 'none' or not 0 <= age <= duration:
        return
    p, center = age/duration, (96,96)
    layer = np.zeros((192,192,4), np.uint8)
    ink = color(hex_color)
    alpha = round(230*(1-p)**1.5)
    if effect == 'ripple':
        for delay in (0., .2):
            q = (p-delay)/(1-delay)
            if q >= 0:
                cv2.circle(layer, center, round(12+38*ease(q)), (*ink,round(alpha*.85)), 3, cv2.LINE_AA)
    elif effect == 'pulse':
        cv2.circle(layer, center, round(14+30*ease(p)), (*ink,round(alpha*.28)), -1, cv2.LINE_AA)
        cv2.circle(layer, center, round(10+24*ease(p)), (*ink,alpha), 2, cv2.LINE_AA)
    elif effect == 'spark':
        for k in range(8):
            theta = k*math.pi/4
            lo, hi = 14+27*ease(p), 25+25*ease(p)
            a = (round(96+lo*math.cos(theta)),round(96+lo*math.sin(theta)))
            b = (round(96+hi*math.cos(theta)),round(96+hi*math.sin(theta)))
            cv2.line(layer,a,b,(*ink,alpha),3,cv2.LINE_AA)
    blend_patch(image,layer,round(x)-96,round(y)-96)


def draw_pointer(image, x, y, kind, config, opacity=1., rotation=0., age=None):
    if opacity <= 0:
        return
    style = config['cursor_style']
    # Rasterize at 2x, then rotate/scale around the actual pointer hotspot.
    layer = np.zeros((256,256,4),np.uint8)
    origin = np.array([128,128])
    ink = (*color(config['cursor_color']),255)
    if style in ('touch','ring'):
        if style == 'touch':
            cv2.circle(layer,(128,128),22,(20,28,34,90),-1,cv2.LINE_AA)
            cv2.circle(layer,(128,128),17,ink,-1,cv2.LINE_AA)
            cv2.circle(layer,(128,128),17,(255,255,255,255),3,cv2.LINE_AA)
        else:
            cv2.circle(layer,(128,128),20,(20,25,35,255),7,cv2.LINE_AA)
            cv2.circle(layer,(128,128),20,ink,4,cv2.LINE_AA)
            cv2.circle(layer,(128,128),3,ink,-1,cv2.LINE_AA)
    elif style == 'auto' and kind in ('text','vertical-text'):
        cv2.line(layer,(128,98),(128,158),(20,20,20,255),7,cv2.LINE_AA)
        for yy in (98,158):cv2.line(layer,(116,yy),(140,yy),ink,4,cv2.LINE_AA)
        cv2.line(layer,(128,98),(128,158),ink,3,cv2.LINE_AA)
    else:
        if style == 'auto' and kind in ('pointer','hand'):
            poly = np.array([[7,-18],[13,-18],[13,-2],[17,-8],[22,-6],[22,-1],[26,-5],[31,-2],[29,16],[24,24],[8,24],[2,11],[2,3],[7,3]])*2+origin
        else:
            poly = np.array([[0,0],[0,31],[8,23],[15,39],[21,36],[14,20],[27,20]])*2+origin
        cv2.fillPoly(layer,[poly+np.array([3,5])],(8,15,25,100),cv2.LINE_AA)
        cv2.polylines(layer,[poly.astype(np.int32)],True,(16,22,33,255),8,cv2.LINE_AA)
        cv2.fillPoly(layer,[poly.astype(np.int32)],ink,cv2.LINE_AA)
    press = 1.-.14*math.sin(math.pi*age/.22) if age is not None and 0<=age<.22 else 1.
    matrix = cv2.getRotationMatrix2D((128,128),rotation,config['cursor_size']*press/2.)
    matrix[0,2] += x-math.floor(x)
    matrix[1,2] += y-math.floor(y)
    layer = cv2.warpAffine(layer,matrix,(256,256),flags=cv2.INTER_LINEAR)
    layer[:,:,3] = (layer[:,:,3]*opacity).astype(np.uint8)
    blend_patch(image,layer,math.floor(x)-128,math.floor(y)-128)


class Frame:
    def __init__(self, viewport, background='graphite', canvas=None, padding=72, radius=26):
        self.vw, self.vh = viewport['width'], viewport['height']
        self.width, self.height = canvas or ((self.vw,self.vh) if background=='none' else (1920,1080))
        if background == 'none' and canvas is None:
            padding, radius = 0, 0
        divisor = math.gcd(self.vw,self.vh)
        unit_w,unit_h = self.vw//divisor,self.vh//divisor
        units = math.floor(min((self.width-2*padding)/unit_w,(self.height-2*padding)/unit_h))
        self.scale = units/divisor
        if self.scale <= 0:
            raise ValueError('Canvas padding leaves no room for the recording')
        self.w, self.h = units*unit_w,units*unit_h
        self.x, self.y = (self.width-self.w)//2,(self.height-self.h)//2
        colors = {'graphite':('#142338','#30425D'),'aurora':('#20264F','#347F86'),
                  'sunset':('#402739','#B86B48'),'none':('#000000','#000000')}
        a,b = (np.array(color(c),np.float32) for c in colors[background])
        yy,xx = np.mgrid[0:self.height,0:self.width]
        u = np.clip(.65*xx/max(1,self.width-1)+.35*yy/max(1,self.height-1),0,1)[:,:,None]
        self.base = (a*(1-u)+b*u).astype(np.uint8)
        self.mask = np.zeros((self.h,self.w),np.uint8)
        r = min(radius,self.h//2,self.w//2)
        cv2.rectangle(self.mask,(r,0),(self.w-r-1,self.h-1),255,-1)
        cv2.rectangle(self.mask,(0,r),(self.w-1,self.h-r-1),255,-1)
        for cx,cy in ((r,r),(self.w-r-1,r),(r,self.h-r-1),(self.w-r-1,self.h-r-1)):
            cv2.circle(self.mask,(cx,cy),r,255,-1,cv2.LINE_AA)
        shadow = np.zeros((self.height,self.width),np.uint8)
        sy = min(self.height-self.h,self.y+12)
        shadow[sy:sy+self.h,self.x:self.x+self.w] = self.mask
        shadow = cv2.GaussianBlur(shadow,(0,0),22)
        self.base = (self.base*(1-shadow[:,:,None]/255.*.38)).astype(np.uint8)
        self.alpha = self.mask[:,:,None].astype(np.float32)/255.

    def compose(self, source):
        image = self.base.copy()
        screen = cv2.resize(source,(self.w,self.h),interpolation=cv2.INTER_AREA if self.scale<1 else cv2.INTER_CUBIC)
        roi = image[self.y:self.y+self.h,self.x:self.x+self.w]
        roi[:] = np.clip(screen*self.alpha+roi*(1-self.alpha),0,255).astype(np.uint8)
        return image
