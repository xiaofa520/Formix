import os
import subprocess
import sys
from pathlib import Path

root = Path(sys.executable).resolve().parent
host = root / 'runtime/格式转换通.exe'
if not host.is_file():
    host = root / 'runtime/Formix.exe'
environment = os.environ.copy()
for key in ('PYTHONHOME', 'PYTHONPATH', 'PYTHONUSERBASE', 'VIRTUAL_ENV'):
    environment.pop(key, None)
environment['PYTHONNOUSERSITE'] = '1'
# The child embeds its own Python DLL, not PyInstaller's bootstrap runtime.
if sys.platform == 'win32':
    import ctypes
    ctypes.windll.kernel32.SetDllDirectoryW(None)
raise SystemExit(subprocess.call(
    [str(host), '-I', str(root / 'main.pyc'), *sys.argv[1:]],
    cwd=root, env=environment, creationflags=subprocess.CREATE_NO_WINDOW))
