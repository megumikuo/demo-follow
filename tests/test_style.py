import json
import hashlib
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

import cv2
import numpy as np

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from timeline import Timeline
from style import PRESETS, PointerMotion, Frame, draw_pointer, draw_click


class TimelineTests(unittest.TestCase):
    def test_segment_round_trip_and_preserved_order(self):
        t=Timeline(10,1.,[{'start':2.,'end':6.,'speed':2.}])
        self.assertAlmostEqual(t.duration,8.)
        values=np.linspace(0,10,401)
        for v in values:self.assertAlmostEqual(t.source_at(t.output_at(v)),v)
        self.assertTrue(all(b>=a for a,b in zip([t.output_at(v) for v in values],
                                               [t.output_at(v) for v in values][1:])))

    def test_invalid_rates_regions_and_overlap_are_rejected(self):
        for rate in (0,-1,4,float('nan')):
            with self.assertRaises(ValueError):Timeline(10,rate)
        for segments in ([{'start':4,'end':2,'speed':1}],
                         [{'start':0,'end':11,'speed':1}],
                         [{'start':1,'end':4,'speed':2},{'start':3,'end':5,'speed':2}]):
            with self.assertRaises(ValueError):Timeline(10,segments=segments)


class StyleTests(unittest.TestCase):
    def test_smoothing_keeps_actual_click_hotspot_exact(self):
        points=[{'t':1.,'x':100,'y':45,'type':'pointerdown'}]
        motion=PointerMotion(points,lambda t:(t*70,t*50,'pointer'),.035)
        self.assertEqual(motion.at(1.)[:2],(100.,45.))

    def test_idle_fade_hides_and_click_reveals_cursor(self):
        points=[{'t':0.,'x':100,'y':45,'type':'pointermove'},
                {'t':2.,'x':100,'y':45,'type':'pointerdown'}]
        m=PointerMotion(points,lambda t:(100.,45.,'default'),.025)
        self.assertEqual(m.opacity(1.5,True),0.)
        self.assertEqual(m.opacity(2.,True),1.)
        self.assertEqual(m.opacity(10.,False),1.)

    def test_frame_fits_without_stretching_or_losing_center_content(self):
        source=np.full((100,160,3),235,np.uint8);source[40:60,70:90]=(20,180,80)
        frame=Frame({'width':160,'height':100},'graphite',(320,180),8,12)
        self.assertEqual(frame.w/frame.h,1.6)
        output=frame.compose(source)
        np.testing.assert_array_equal(output[90,160],(20,180,80))
        self.assertFalse(np.array_equal(output[0,0],source[0,0]))

    def test_click_effects_are_distinct_and_expire(self):
        outputs=[]
        for effect in ('ripple','pulse','spark','none'):
            image=np.zeros((180,220,3),np.uint8)
            draw_click(image,110,90,.15,effect,'#FFBB44')
            outputs.append(image)
        self.assertTrue(all(not np.array_equal(a,b) for i,a in enumerate(outputs) for b in outputs[i+1:]))
        expired=np.zeros((180,220,3),np.uint8)
        draw_click(expired,110,90,1.,'ripple','#FFBB44')
        self.assertEqual(int(expired.sum()),0)

    def test_cursor_styles_support_screen_edges_and_transparency(self):
        for name in PRESETS:
            config=PRESETS[name]
            image=np.zeros((100,160,3),np.uint8)
            draw_pointer(image,1.25,2.75,'pointer',config)
            self.assertGreater(int(image.sum()),0)
            hidden=np.zeros_like(image)
            draw_pointer(hidden,80,50,'default',config,opacity=0.)
            self.assertEqual(int(hidden.sum()),0)

    def test_real_encoder_retimes_without_modifying_source_fixture(self):
        # Explicit local fixture, not evidence of recording the live website.
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);raw=root/'fixture.avi';meta=root/'events.json';out=root/'render'
            writer=cv2.VideoWriter(str(raw),cv2.VideoWriter_fourcc(*'MJPG'),20.,(160,100))
            self.assertTrue(writer.isOpened())
            for i in range(20):
                image=np.full((100,160,3),30+i*5,np.uint8)
                image[40:60,70:90]=(20,180,80)
                writer.write(image)
            writer.release();before=hashlib.sha256(raw.read_bytes()).digest()
            meta.write_text(json.dumps({'status':'complete','video_offset':0.,'duration':1.,
                'viewport':{'width':160,'height':100},'events':[],
                'pointer':[{'t':.5,'x':80,'y':50,'type':'pointerdown'}],'assertions':[]}))
            script=Path(__file__).resolve().parents[1]/'scripts/render.py'
            run=subprocess.run([sys.executable,str(script),str(raw),str(meta),'--out-dir',str(out),
                '--preset','playful','--speed','2','--fps','24','--canvas','320x180','--padding','8','--mp4-only'],
                capture_output=True,text=True)
            self.assertEqual(run.returncode,0,run.stderr)
            self.assertEqual(hashlib.sha256(raw.read_bytes()).digest(),before)
            report=json.loads((out/'render-report.json').read_text())
            track=json.loads((out/'camera-track.json').read_text())
            self.assertEqual(report['frames'],12)
            self.assertEqual(report['output_resolution'],[320,180])
            self.assertAlmostEqual(track[6]['source_t'],.5)
            self.assertAlmostEqual(track[6]['cursor_x'],160)
            cap=cv2.VideoCapture(str(out/'demo.mp4'));count=0
            while cap.read()[0]:count+=1
            cap.release();self.assertEqual(count,12)


if __name__=='__main__':unittest.main()
