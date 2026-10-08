import sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from camera import target_pose
from validate_video import check_framing

class FramingChecks(unittest.TestCase):
 def fixture(self):
  vp={'width':1440,'height':900};event={'type':'focus','shot':'context','zoom':1.25,'bounds':{'x':440,'y':170,'width':560,'height':560},'context_bounds':[{'x':234,'y':9,'width':180,'height':63}]};pose=target_pose(event,vp)
  report={'viewport_resolution':[1440,900],'source_duration':6,'frame':{'x':0,'y':0,'width':1440,'height':900,'scale':1},'framing':[{'label':'board','sample_t':2,'bounds':event['bounds'],'context_bounds':event['context_bounds'],'target':pose.values()}]}
  track=[dict(t=i,source_t=i,zoom=pose.zoom,tx=pose.x,ty=pose.y) for i in (3,4,5)]
  return track,report,{'events':[{'type':'end','t':6}]}
 def test_every_steady_frame_has_whole_controls_and_balanced_composition(self):
  track,report,events=self.fixture();r=check_framing(track,report,events)
  self.assertEqual(r['checked_frames'],3);self.assertEqual(r['steady_frames'],3);self.assertGreaterEqual(r['minimum_region_clearance_px'],9-1e-8);self.assertLess(r['max_steady_vertical_center_error_px'],1e-8)
 def test_old_board_only_crop_is_rejected(self):
  track,report,events=self.fixture();track[1].update(zoom=1.25,tx=-180,ty=-112.5)
  with self.assertRaisesRegex(AssertionError,'clipped'):check_framing(track,report,events)
