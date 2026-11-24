import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from formix import runtime_paths, runtime_check


class OptionalEnginesTest(unittest.TestCase):
    def test_missing_engines_do_not_download_at_startup(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "release.txt").write_text("1.2.9")
            (root / "engine-versions.json").write_text(json.dumps({"ffmpeg": "9.0.2"}))
            with patch.object(runtime_paths, "ROOT", root), patch.object(runtime_paths, "active_engine", return_value=None), \
                 patch.object(runtime_check, "check") as check, patch.object(runtime_check, "repair") as repair:
                for component in ("libvips", "libreoffice"):
                    self.assertTrue(runtime_paths.optional_engine_missing(component))
                    self.assertEqual(runtime_check.ensure(component), {"optional_missing": True})
                check.assert_not_called()
                repair.assert_not_called()
                with self.assertRaisesRegex(RuntimeError, "Optional engine"):
                    runtime_paths.executable("soffice")
                with self.assertRaisesRegex(RuntimeError, "Optional engine"):
                    runtime_paths.load_vips()
                self.assertEqual(runtime_paths.missing_runtime("Optional engine not installed: libvips", 1), "libvips")
            with patch.object(runtime_paths, "ROOT", root), patch.object(runtime_paths, "active_engine", return_value=("1", root)):
                self.assertFalse(runtime_paths.optional_engine_missing("libvips"))

    def test_offline_manifest_omits_only_native_image_engine(self):
        sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "packaging"))
        from wheel_manifest import write_offline_requirements
        with tempfile.TemporaryDirectory() as tmp:
            packages = [{"name": name, "version": "1", "wheels": [{"hashes": {"sha256": "a" * 64}}]}
                        for name in ("pyvips-binary", "pyvips", "pip", "imageio-ffmpeg")]
            text = write_offline_requirements(packages, Path(tmp)).read_text()
            self.assertNotIn("pyvips-binary", text)
            for name in ("pyvips", "pip", "imageio-ffmpeg"):
                self.assertIn(name + "==", text)


if __name__ == "__main__":
    unittest.main()
