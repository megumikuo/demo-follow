"""Real Chromium integration: clock calibration, navigation and assertions."""
import json
import sys
import tempfile
import unittest
from pathlib import Path
import cv2
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from record import record


class RecordingTests(unittest.TestCase):
    def test_navigation_keeps_telemetry_and_sync_matches_real_pixels(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            (root/'first.html').write_text('''<body style="margin:0;background:rgb(17,51,85)">
              <a id="next" href="second.html" style="display:block;position:absolute;left:150px;top:120px;color:white">Next page</a></body>''')
            (root/'second.html').write_text('''<body style="background:#113355"><button id="help" style="position:absolute;left:80px;top:80px">Help</button><button id="done" style="position:absolute;left:200px;top:180px" onclick="this.textContent='Done'">Finish</button></body>''')
            plan={'html_file':'first.html','viewport':{'width':640,'height':480},'settle_ms':700,'intro_ms':250,'tail_ms':1200,
                  'actions':[{'type':'click','selector':'#next','after_ms':300,'assert':{'selector':'#done'}},
                             {'type':'key','key':'Tab','after_ms':10},
                             {'type':'click','selector':'#done','camera_context_selectors':['#help'],'after_ms':300,'assert':{'selector':'#done','text':'Done'}}]}
            path=root/'plan.json';path.write_text(json.dumps(plan))
            m=record(path,root/'recording')
            self.assertEqual(m['status'],'complete')
            self.assertGreaterEqual(len([p for p in m['pointer'] if p['type']=='pointerdown']),2)
            self.assertFalse(any(e['type']=='reset' for e in m['events']))
            self.assertEqual(len(m['assertions']),2)
            focus=[e for e in m['events'] if e.get('selector')=='#done'][0]
            self.assertEqual(focus['context_bounds'][0]['selector'],'#help')
            self.assertEqual(focus['context_bounds'][0]['bounds']['y'],80)
            self.assertGreater(m['video_offset'],.7)
            self.assertLessEqual(m['sync_quantization_seconds'],.05)
            times=[p['t'] for p in m['pointer']]
            self.assertEqual(times,sorted(times))
            cap=cv2.VideoCapture(str(root/'recording/raw.webm'))
            cap.set(cv2.CAP_PROP_POS_FRAMES,m['sync_frame'])
            ok,frame=cap.read();cap.release()
            self.assertTrue(ok)
            b,g,r=frame[8:36,8:36].mean(axis=(0,1))
            for observed,expected in zip((b,g,r),(85,51,17)):
                self.assertLess(abs(observed-expected),12)

    def test_failed_assertion_does_not_mark_capture_complete(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            (root/'page.html').write_text('<button id="a" style="margin:100px">No change</button>')
            path=root/'plan.json'
            path.write_text(json.dumps({'html_file':'page.html','viewport':{'width':640,'height':480},
                'settle_ms':100,'intro_ms':10,'actions':[{'type':'click','selector':'#a','after_ms':10,
                'assert':{'selector':'#a','text':'Not present'}}]}))
            with self.assertRaises(RuntimeError):
                record(path,root/'recording')
            m=json.loads((root/'recording/events.json').read_text())
            self.assertEqual(m['status'],'failed')
            self.assertFalse((root/'recording/demo.mp4').exists())


if __name__=='__main__':
    unittest.main()
