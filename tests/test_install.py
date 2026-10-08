import sys
import tempfile
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from install import install


class InstallTests(unittest.TestCase):
    def test_install_preserves_skill_and_refuses_existing_target(self):
        with tempfile.TemporaryDirectory() as d:
            source=Path(d)/'source';source.mkdir()
            (source/'SKILL.md').write_text('---\nname: example\ndescription: example\n---\n')
            (source/'output').mkdir();(source/'output/private.webm').write_bytes(b'private')
            target=Path(d)/'destination'
            install(source,target)
            self.assertEqual((target/'SKILL.md').read_bytes(),(source/'SKILL.md').read_bytes())
            self.assertFalse((target/'output').exists())
            with self.assertRaises(FileExistsError):install(source,target)


if __name__=='__main__':unittest.main()
