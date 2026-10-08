import math
import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from camera import Camera, Pose, target_pose

VP = {'width': 1280, 'height': 720}


class CameraTests(unittest.TestCase):
    def test_required_controls_fit_and_complete_composition_is_balanced(self):
        viewport={'width':1440,'height':900}
        board={'x':440,'y':170,'width':560,'height':560}
        controls=[{'x':234,'y':10,'width':180,'height':63},
                  {'x':734,'y':85,'width':266,'height':63}]
        event={'t':2.,'type':'focus','shot':'context','zoom':1.25,'bounds':board,
               'context_bounds':controls,'safe_margin':12}
        p=target_pose(event,viewport)
        self.assertGreater(p.zoom,1.1)
        for b in [board,*controls]:
            self.assertGreaterEqual(p.zoom*b['x']+p.x,12-1e-8)
            self.assertGreaterEqual(p.zoom*b['y']+p.y,12-1e-8)
            self.assertLessEqual(p.zoom*(b['x']+b['width'])+p.x,1428+1e-8)
            self.assertLessEqual(p.zoom*(b['y']+b['height'])+p.y,888+1e-8)
        self.assertAlmostEqual(p.zoom*720+p.x,720)
        self.assertAlmostEqual(p.zoom*(10+730)/2+p.y,450)

    def test_required_controls_remain_whole_during_entry_and_exit(self):
        viewport={'width':1440,'height':900}
        event={'t':2.,'type':'focus','shot':'context','zoom':1.25,
               'bounds':{'x':440,'y':170,'width':560,'height':560},
               'context_bounds':[{'x':234,'y':10,'width':180,'height':63}]}
        c=Camera([event,{**event,'t':4.},{'t':6.,'type':'reset'}],viewport)
        self.assertEqual(len(c.transitions),2)
        for i in range(480):
            p=c.at(i/60); b=event['context_bounds'][0]
            self.assertGreaterEqual(p.zoom*b['y']+p.y,10-1e-8)
            self.assertLessEqual(p.zoom*(b['y']+b['height'])+p.y,900)

    def test_control_at_source_edge_preserves_pixels_and_meaningful_zoom(self):
        event={'type':'context','bounds':{'x':300,'y':150,'width':400,'height':400},
               'context_bounds':[{'x':10,'y':0,'width':100,'height':60}]}
        p=target_pose(event,VP)
        self.assertGreater(p.zoom,1.)
        self.assertEqual(p.y,0.)

    def test_clipped_required_source_context_is_rejected(self):
        with self.assertRaisesRegex(ValueError,'clipped'):
            target_pose({'type':'focus','bounds':{'x':300,'y':100,'width':400,'height':400},
                         'context_bounds':[{'x':10,'y':-2,'width':100,'height':60}]},VP)

    def test_protected_composition_stays_balanced_through_video_end(self):
        event={'t':2.,'type':'focus','bounds':{'x':300,'y':150,'width':400,'height':400},
               'context_bounds':[{'x':100,'y':60,'width':150,'height':60}]}
        c=Camera([event,{'t':5.,'type':'end'}],VP)
        self.assertTrue(c.end_held)
        self.assertEqual(c.at(4.),c.at(8.))

    def test_isolated_second_focus_has_continuous_lead_in(self):
        c = Camera([{'t':1.,'type':'focus','x':200,'y':200},
                    {'t':5.,'type':'focus','x':1000,'y':400}], VP)
        self.assertLess(c.at(4.9).x, c.at(4.2).x)
        self.assertLess(abs(c.at(5.).x-c.at(4.999).x), 2.)
        self.assertGreater(c.at(4.).zoom, 1.)

    def test_context_supersedes_trigger_and_fits_entire_dialog(self):
        events = [{'t':2.,'type':'focus','x':1150,'y':50},
                  {'t':2.16,'type':'context','bounds':{'x':340,'y':110,'width':600,'height':500}}]
        c = Camera(events, VP)
        self.assertEqual(len(c.transitions), 1)
        self.assertEqual(c.transitions[0].reason, 'context')
        self.assertLessEqual(c.at(4).zoom, 720/(500*1.12))
        large = target_pose({'type':'context','bounds':{'x':340,'y':36,'width':600,'height':648}},VP)
        self.assertEqual(large.zoom,1.)

    def test_scroll_lock_is_exactly_stationary(self):
        events = [{'t':1.,'type':'focus','x':200,'y':200},
                  {'t':2.,'type':'lock','bounds':{'x':0,'y':0,'width':1200,'height':600}},
                  {'t':3.,'type':'focus','x':1100,'y':500},
                  {'t':4.,'type':'unlock'}]
        c = Camera(events, VP)
        self.assertEqual(len({c.at(2+i/100) for i in range(201)}),1)

    def test_all_frame_transforms_inside_source_and_smooth(self):
        events = [{'t':2.,'type':'focus','x':0,'y':0},
                  {'t':4.,'type':'focus','x':1280,'y':720},
                  {'t':6.,'type':'reset'}]
        c = Camera(events, VP)
        for i in range(480):
            p = c.at(i/60)
            self.assertTrue((1-p.zoom)*1280-1e-8 <= p.x <= 1e-8)
            self.assertTrue((1-p.zoom)*720-1e-8 <= p.y <= 1e-8)
        for tr in c.transitions:
            for t in (tr.start,tr.end):
                eps = 1e-4
                a,b,d = c.at(t-eps),c.at(t),c.at(t+eps)
                for l,m,r in zip(a.values(),b.values(),d.values()):
                    self.assertLess(abs(r-l)/(2*eps), .001)
                    self.assertLess(abs(r-2*m+l)/eps**2, 2.)

    def test_rapid_actions_do_not_interrupt_camera(self):
        c = Camera([{'t':1+i*.1,'type':'focus','x':i*30,'y':200} for i in range(6)],VP)
        self.assertEqual(len(c.transitions),1)

    def test_drag_explicit_zoom_is_used_and_end_releases(self):
        c = Camera([{'t':2.,'type':'follow_start','zoom':1.3,
                    'bounds':{'x':300,'y':200,'width':150,'height':150}},
                    {'t':4.,'type':'end'}], VP)
        self.assertAlmostEqual(c.at(3.5).zoom,1.3)
        self.assertEqual(c.at(6.),Pose())


if __name__ == '__main__':
    unittest.main()
