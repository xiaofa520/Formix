import contextlib
import io
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from formix import worker


class ModelDownloadTests(unittest.TestCase):
    def test_existing_broken_private_runtime_is_repaired_and_probed(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            worker.runtime_dir(root).mkdir()
            failure = subprocess.CompletedProcess([], 1, b'', b'broken dependency')
            success = subprocess.CompletedProcess([], 0, b'', b'')
            with patch.object(worker, 'run_process', side_effect=[failure, success]) as probe, \
                 patch.object(worker, 'run_pip') as install:
                self.assertEqual(worker.prepare_private_model_runtime(root, 'pp-ocrv5-mobile'), worker.runtime_dir(root))
                install.assert_called_once()
                self.assertEqual(probe.call_count, 2)

    def setUp(self):
        # These are isolated download/runtime tests; a missed mock must never install packages.
        guard = patch.object(subprocess, 'Popen', side_effect=AssertionError('Unexpected real subprocess in model test'))
        guard.start()
        self.addCleanup(guard.stop)

    def test_intel_mac_uses_compatible_runtime_requirements(self):
        with tempfile.TemporaryDirectory() as tmp, \
                patch.object(worker.platform, 'system', return_value='Darwin'), \
                patch.object(worker.platform, 'machine', return_value='x86_64'), \
                patch.object(sys, 'path', list(sys.path)), \
                patch.object(worker, 'run_process') as run, \
                patch.object(worker, 'run_pip') as pip:
            run.side_effect = [subprocess.CompletedProcess([], code, b'', b'')
                               for code in (1, 0)]
            worker.prepare_runtime(Path(tmp) / '.download-test')
            install = pip.call_args.args[0]
            self.assertTrue(install[-1].endswith('requirements-model-intel-mac.txt'))
            with self.assertRaisesRegex(ValueError, 'Intel Mac'):
                worker.download(Path(tmp) / 'model', 'dots-ocr', 'revision')

    def test_runtime_paths_separate_os_and_architecture(self):
        paths = set()
        for system, arch in [('Windows', 'AMD64'), ('Linux', 'x86_64'),
                             ('Linux', 'aarch64'), ('Darwin', 'arm64'),
                             ('Darwin', 'x86_64')]:
            with self.subTest(system=system, arch=arch), \
                    patch.object(worker.platform, 'system', return_value=system), \
                    patch.object(worker.platform, 'machine', return_value=arch):
                paths.add(worker.runtime_dir(Path('models')))
        self.assertEqual(len(paths), 5)

    def test_failed_install_retries_at_final_path_on_all_platforms(self):
        for system in ('Windows', 'Linux', 'Darwin'):
            with self.subTest(system=system), tempfile.TemporaryDirectory() as tmp, \
                    patch.object(worker.platform, 'system', return_value=system), \
                    patch.object(sys, 'path', list(sys.path)), \
                    patch.object(worker, 'run_process') as run, \
                    patch.object(worker, 'run_pip') as pip:
                stage = Path(tmp) / '.download-test'
                stage.mkdir()
                target = worker.runtime_dir(stage.parent)
                failure = subprocess.CompletedProcess([], 1, b'', b'missing dependency')
                success = subprocess.CompletedProcess([], 0, b'', b'')
                run.side_effect = [failure]
                pip.side_effect = subprocess.CalledProcessError(1, 'pip')
                with self.assertRaises(subprocess.CalledProcessError):
                    worker.prepare_runtime(stage)
                self.assertTrue(target.is_dir())
                run.reset_mock()
                pip.reset_mock()
                pip.side_effect = None
                run.side_effect = [failure, success]
                with patch.object(Path, 'rename', side_effect=PermissionError('locked')), \
                        contextlib.redirect_stderr(io.StringIO()):
                    worker.prepare_runtime(stage)
                install = pip.call_args.args[0]
                self.assertEqual(install[install.index('--target') + 1], str(target))
                self.assertIn(str(target), sys.path)
                run.reset_mock()
                pip.reset_mock()
                run.side_effect = [success]
                worker.prepare_runtime(stage)
                self.assertEqual(run.call_count, 1)
                pip.assert_not_called()

    def test_system_proxy_is_inherited_by_dependency_installer(self):
        for system in ('Windows', 'Linux', 'Darwin'):
            with self.subTest(system=system), patch.dict(os.environ, {}, clear=True), \
                    patch.object(worker.platform, 'system', return_value=system), \
                    patch.object(worker.urllib.request, 'getproxies', return_value={
                        'http': '127.0.0.1:7890', 'https': '127.0.0.1:7890'}), \
                    patch.object(worker.urllib.request, 'install_opener'):
                worker.configure_download_network()
                self.assertEqual(os.environ['HTTPS_PROXY'], 'http://127.0.0.1:7890')
                self.assertEqual(os.environ['HTTP_PROXY'], 'http://127.0.0.1:7890')

    def test_direct_network_does_not_invent_proxy(self):
        with patch.dict(os.environ, {}, clear=True), \
                patch.object(worker.urllib.request, 'getproxies', return_value={}), \
                patch.object(worker.urllib.request, 'install_opener'):
            worker.configure_download_network()
            self.assertNotIn('HTTPS_PROXY', os.environ)

    def test_download_retries_reports_bytes_and_marks_ready_only_when_complete(self):
        with tempfile.TemporaryDirectory() as tmp, \
                patch.object(worker, 'manifest', return_value=('revision', {'config.json': 3})), \
                patch.object(worker, 'prepare_runtime'), \
                patch.object(worker, 'configure_download_network'), \
                patch.object(worker.time, 'sleep'), \
                patch.object(worker.urllib.request, 'urlopen', side_effect=[
                    OSError('network disconnected'), io.BytesIO(b'abc')]):
            target = Path(tmp) / 'model'
            output = io.StringIO()
            with contextlib.redirect_stderr(output):
                worker.download(target, 'granite-docling-258m', 'revision')
            self.assertTrue((target / 'READY').is_file())
            self.assertIn('FORMIX_PROGRESS|model|3|3', output.getvalue())

    def test_incomplete_download_never_marks_ready(self):
        with tempfile.TemporaryDirectory() as tmp, \
                patch.object(worker, 'manifest', return_value=('revision', {'config.json': 5})), \
                patch.object(worker, 'prepare_runtime'), \
                patch.object(worker, 'configure_download_network'), \
                patch.object(worker.time, 'sleep'), \
                patch.object(worker.urllib.request, 'urlopen', side_effect=lambda *a, **k: io.BytesIO(b'ab')):
            target = Path(tmp) / 'model'
            with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(OSError):
                worker.download(target, 'granite-docling-258m', 'revision')
            self.assertFalse((target / 'READY').exists())


if __name__ == '__main__':
    unittest.main()
