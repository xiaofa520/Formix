import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'src'))
from formix.launcher import desktop_runtime


@unittest.skipUnless(os.name == 'nt', 'Windows desktop runtime selection')
class DesktopRuntimeTests(unittest.TestCase):
    def test_installed_runtime_is_selected_only_when_hash_and_location_match(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            bundled = root/'bundled.exe'
            bundled.write_bytes(b'verified interpreter')
            candidate = root/'Formix/runtimes/test/python.exe'
            candidate.parent.mkdir(parents=True)
            candidate.write_bytes(bundled.read_bytes())
            (root/'cache').mkdir()
            config = {'python':str(candidate), 'source_sha256':hashlib.sha256(bundled.read_bytes()).hexdigest()}
            (root/'cache/desktop-runtime.json').write_text(json.dumps(config),'utf-8-sig')
            with patch.dict(os.environ, {'LOCALAPPDATA':str(root)}):
                self.assertEqual(desktop_runtime(root, bundled), candidate)
                candidate.write_bytes(b'changed')
                self.assertEqual(desktop_runtime(root, bundled), bundled)
                config['python'] = str(bundled)
                (root/'cache/desktop-runtime.json').write_text(json.dumps(config),'utf-8')
                self.assertEqual(desktop_runtime(root, bundled), bundled)

    def test_missing_config_keeps_bundled_runtime(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            self.assertEqual(desktop_runtime(root, root/'python.exe'), root/'python.exe')
