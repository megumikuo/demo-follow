import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1]/'scripts'/'make_embed.py'

class EmbedTests(unittest.TestCase):
    def test_mp4_only_player_has_no_dead_webm_links_and_escapes_text(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)
            for name in ('demo.mp4','poster.jpg'): (p/name).write_bytes(b'fixture')
            subprocess.run([sys.executable,str(SCRIPT),'--out',str(p/'embed.html'),'--title','<demo>'],check=True,capture_output=True)
            page=(p/'embed.html').read_text()
            self.assertIn('&lt;demo&gt;',page)
            self.assertIn('src="demo.mp4"',page)
            self.assertNotIn('demo.webm',page)
    def test_webm_source_and_download_are_included_when_present(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)
            for name in ('demo.mp4','demo.webm','poster.jpg'): (p/name).write_bytes(b'fixture')
            subprocess.run([sys.executable,str(SCRIPT),'--out',str(p/'embed.html')],check=True,capture_output=True)
            page=(p/'embed.html').read_text()
            self.assertIn('src="demo.webm"',page)
            self.assertIn('href="demo.webm"',page)
