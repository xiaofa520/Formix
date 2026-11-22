import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


class DiagnosticTests(unittest.TestCase):
    def run_script(self, script, folder):
        source = Path(__file__).resolve().parents[1]/'src'
        code = 'import sys;sys.path.insert(0,sys.argv[1]);\n' + script
        return subprocess.run([sys.executable, '-I', '-X', 'utf8', '-c', code,
                               str(source), str(folder)], capture_output=True, timeout=30)

    def test_logs_flush_and_capture_full_exception(self):
        with tempfile.TemporaryDirectory() as folder:
            result = self.run_script('''
from formix import diagnostics as d
d.setup(sys.argv[2])
d.install_exception_hooks()
d.event('file_written', task='example', path='中文.docx')
try:
    raise PermissionError('test denied')
except PermissionError:
    sys.excepthook(*sys.exc_info())
d.shutdown()
''', folder)
            self.assertEqual(result.returncode, 0, result.stderr)
            text = next(Path(folder).glob('*.log')).read_text('utf-8')
            for value in ('application_start', 'file_written', '中文.docx',
                          'Traceback', 'PermissionError: test denied', 'application_stop'):
                self.assertIn(value, text)

    def test_rotation_is_bounded(self):
        with tempfile.TemporaryDirectory() as folder:
            result = self.run_script('''
from formix import diagnostics as d
d.setup(sys.argv[2])
d._listener.handlers[0].maxBytes = 1000
for i in range(100):
    d.event('engine_output', line='x'*200, index=i)
d.shutdown()
''', folder)
            self.assertEqual(result.returncode, 0, result.stderr)
            files = list(Path(folder).glob('*.log*'))
            self.assertEqual(len(files), 4)
            self.assertIn('application_stop', next(Path(folder).glob('*.log')).read_text('utf-8'))

    def test_unwritable_log_directory_does_not_crash(self):
        with tempfile.TemporaryDirectory() as folder:
            result = self.run_script('''
from unittest.mock import patch
from pathlib import Path
from formix import diagnostics as d
with patch.object(Path, 'mkdir', side_effect=PermissionError('denied')):
    assert d.setup(sys.argv[2]) is None
d.event('still_running')
''', folder)
            self.assertEqual(result.returncode, 0, result.stderr)
