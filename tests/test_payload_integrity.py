import json
from pathlib import Path
import re
import sys
import tempfile
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'packaging'))
import payload_integrity as integrity

class PayloadIntegrityTests(unittest.TestCase):
    def test_nested_dependency_directories_are_preserved(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            names = ['runtime/Lib/site-packages/pip/_internal/models/scheme.py',
                     'python/lib/pkg/cache/data.bin', 'vendor/office/data/table.dat',
                     'runtime/Lib/pkg/logs/parser.py', 'runtime/Lib/pkg/output/writer.py',
                     'runtime/Lib/pkg/templates/layout.html', 'runtime/Lib/pkg/kernel.obj']
            for name in [*names, 'models/weights.bin', 'cache/scratch.bin']:
                path = root / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(b'abc')
            integrity.write(root)
            entries = json.loads((root / integrity.MANIFEST).read_text())
            self.assertTrue(all(name in entries for name in names))
            self.assertNotIn('models/weights.bin', entries)
            integrity.verify(root)
            target = root / names[0]
            target.write_bytes(b'xyz')
            with self.assertRaises(RuntimeError):
                integrity.verify(root)
            target.unlink()
            with self.assertRaises(RuntimeError):
                integrity.verify(root)

    def test_symlink_target_is_verified(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root/'lib').write_bytes(b'library')
            try:
                (root/'link').symlink_to('lib')
            except OSError:
                self.skipTest('Symlink privilege unavailable')
            integrity.write(root)
            integrity.verify(root)
            (root/'link').unlink()
            (root/'link').symlink_to('missing')
            with self.assertRaises(RuntimeError):
                integrity.verify(root)

    def test_both_windows_templates_anchor_exclusions(self):
        root = Path(__file__).resolve().parents[1]
        for template in ('packaging/windows.iss', 'packaging/windows-release/install.iss'):
            patterns = re.findall(r'Excludes: "([^";]+)"', (root/template).read_text(encoding='utf-8'))
            self.assertTrue(patterns)
            for group in patterns:
                for pattern in group.split(','):
                    self.assertTrue(pattern.startswith(chr(92)), (template, pattern))
