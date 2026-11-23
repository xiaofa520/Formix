"""Copy non-base ELF dependencies needed by the private LibreOffice process."""
import argparse
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

parser = argparse.ArgumentParser()
parser.add_argument("office", type=Path)
office = parser.parse_args().office
soffice = next(office.rglob("soffice"))
program = soffice.parent
libdir = program.parent/"formix-libs"
libdir.mkdir()
environment = os.environ.copy()
environment['LD_LIBRARY_PATH'] = f"{program}:{libdir}" + (":" + environment['LD_LIBRARY_PATH'] if environment.get('LD_LIBRARY_PATH') else "")
# glibc and graphics drivers must match the host OS.
host = re.compile(r"^(ld-linux|lib(c|m|pthread|dl|rt|resolv|util|anl)\.so|lib(GL|EGL|drm|gbm))")
for file in list(office.rglob("*")):
    if not file.is_file():
        continue
    with file.open("rb") as stream:
        if stream.read(4) != b"\x7fELF":
            continue
    result = subprocess.run(["ldd",file],capture_output=True,text=True,env=environment)
    for name, path in re.findall(r"^\s*(\S+) => (/\S+)",result.stdout,re.M):
        if host.match(name) or (libdir/name).exists() or (program/name).exists() or Path(path).resolve().is_relative_to(office.resolve()):
            continue
        shutil.copy2(path,libdir/name)

# NSS loads crypto providers with dlopen; ldd does not list them. When we
# relocate the system NSS library, retain its matching provider modules too.
if (libdir / 'libnss3.so').exists():
    files = subprocess.check_output(['dpkg-query', '-L', 'libnss3'], text=True).splitlines()
    for entry in files:
        source = Path(entry)
        if source.is_file() and (source.suffix == '.so' or source.suffix == '.chk'):
            shutil.copy2(source, libdir / source.name)
    required = ('libnss3.so', 'libsoftokn3.so', 'libfreeblpriv3.so')
    for name in required:
        if not (libdir / name).is_file():
            raise RuntimeError(f'Missing NSS runtime module: {name}')
    subprocess.run([sys.executable, '-c',
                    'import ctypes,sys; n=ctypes.CDLL(sys.argv[1]); '
                    'n.NSS_NoDB_Init.argtypes=[ctypes.c_char_p]; '
                    'n.NSS_NoDB_Init.restype=ctypes.c_int; '
                    'result=n.NSS_NoDB_Init(None); '
                    'assert result == 0, "NSS initialization failed: %s" % result; '
                    'n.NSS_Shutdown(); print("Private NSS crypto modules initialized")',
                    str((libdir / 'libnss3.so').resolve())], check=True, env=environment)
launcher = program/"formix-office"
launcher.write_text("""#!/bin/sh
dir="$(dirname "$0")"
export LD_LIBRARY_PATH="$dir:$dir/../formix-libs${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
export SAL_USE_VCLPLUGIN=svp
exec "$dir/soffice" "$@"
""")
os.chmod(launcher,0o755)
