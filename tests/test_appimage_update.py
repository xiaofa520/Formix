import functools
import hashlib
import http.server
import os
from pathlib import Path
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from formix import engine_update


class AppImageDownloadTests(unittest.TestCase):
    def test_selected_package_download_survives_extraction_cleanup(self):
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            extracted = base / 'extracted'
            extracted.mkdir()
            (extracted / 'package-format').write_text('appimage')
            source = base / 'server'
            source.mkdir()
            name = 'formix-linux-64-v9.0.0.AppImage'
            payload = b'AppImage download integrity fixture' * 1024
            (source / name).write_bytes(payload)
            server = http.server.ThreadingHTTPServer(('127.0.0.1', 0),
                functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(source)))
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                release = dict(tag_name='v9.0.0', assets=[dict(name=name, size=len(payload),
                    digest='sha256:' + hashlib.sha256(payload).hexdigest(),
                    browser_download_url=f'http://127.0.0.1:{server.server_port}/{name}')])
                with patch.object(engine_update, 'ROOT', extracted), \
                     patch.object(engine_update, 'SLUG', 'linux-x64'), \
                     patch.object(engine_update.sys, 'platform', 'linux'), \
                     patch.dict(os.environ, {'APPIMAGE': str(base / 'Original.AppImage'),
                                            'XDG_CACHE_HOME': str(base / 'cache')}):
                    asset = engine_update.latest(release, for_repair=True)
                    directory = engine_update.cache_folder('app', 'linux-x64', '9.0.0')
                    self.assertTrue(directory.is_relative_to(base / 'cache'))
                    with patch.object(engine_update, 'latest', return_value=asset):
                        downloaded = Path(engine_update.fetch('9.0.0', directory))
                        self.assertEqual(downloaded.name, name)
                        self.assertEqual(downloaded.read_bytes(), payload)
                        import shutil
                        shutil.rmtree(extracted)
                        self.assertEqual(downloaded.read_bytes(), payload)
                        (source / name).write_bytes(b'corrupt')
                        with self.assertRaises(ValueError):
                            engine_update.fetch('9.0.0', directory)
                        self.assertEqual(downloaded.read_bytes(), payload)
            finally:
                server.shutdown()
                server.server_close()
                thread.join()
