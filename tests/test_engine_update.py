import hashlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from formix import engine_install, engine_update, runtime_paths


class EngineUpdateTests(unittest.TestCase):
    def test_download_checks_bytes_and_reuses_only_a_verified_cache(self):
        body = b"F" * (1024 * 1024 + 10)
        asset = dict(name="test.whl", version="1.2", url="unused", size=len(body),
                     sha256=hashlib.sha256(body).hexdigest())
        with tempfile.TemporaryDirectory() as tmp, patch.object(engine_update, "cache_folder", return_value=Path(tmp)), \
                patch.object(engine_update, "engine_release", return_value=asset):
            events = []
            with patch.object(engine_update, "request", return_value=io.BytesIO(body)):
                path = Path(engine_update.fetch_engine("ffmpeg", "1.2", lambda *event: events.append(event)))
            self.assertIn(("download", 100), events)
            self.assertEqual(events[-1], ("verify",))
            self.assertEqual(path.read_bytes(), body)
            with patch.object(engine_update, "request", side_effect=AssertionError("Downloaded again")):
                engine_update.fetch_engine("ffmpeg", "1.2", lambda *_: None)
            path.write_bytes(b"X" * len(body))
            with patch.object(engine_update, "request", return_value=io.BytesIO(b"partial")), \
                    self.assertRaises(ValueError):
                engine_update.fetch_engine("ffmpeg", "1.2", lambda *_: None)

    def test_failed_probe_keeps_previous_executable_and_version(self):
        def unpack(_, candidate, __):
            entry = candidate / "ffmpeg"
            entry.write_bytes(b"candidate")
            return entry

        with tempfile.TemporaryDirectory() as tmp, patch.object(runtime_paths, "engine_store", return_value=Path(tmp)), \
                patch.object(engine_install, "engine_store", return_value=Path(tmp)), \
                patch.object(engine_install, "unpack_wheel", side_effect=unpack):
            with patch.object(engine_install, "probe"):
                engine_install.install("ffmpeg", "1.0", None)
            previous = runtime_paths.executable("ffmpeg")
            pointer = Path(tmp) / "ffmpeg/active.json"
            original = pointer.read_bytes()
            with patch.object(engine_install, "probe", side_effect=RuntimeError("incompatible binary")), \
                    self.assertRaises(RuntimeError):
                engine_install.install("ffmpeg", "2.0", None)
            self.assertEqual(pointer.read_bytes(), original)
            self.assertEqual(engine_update.local_version("ffmpeg"), "1.0")
            self.assertEqual(runtime_paths.executable("ffmpeg"), previous)
            self.assertTrue(Path(previous).is_file())
            with patch.object(engine_install, "probe"):
                engine_install.install("ffmpeg", "2.0", None)
            self.assertEqual(json.loads(pointer.read_bytes())["version"], "2.0")
            self.assertNotEqual(runtime_paths.executable("ffmpeg"), previous)
            self.assertTrue(Path(previous).is_file())  # Existing jobs can finish.
