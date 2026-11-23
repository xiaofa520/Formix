"""Copy non-base ELF dependencies needed by the private LibreOffice process."""
import argparse
import os
import re
import shutil
import subprocess
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
launcher = program/"formix-office"
launcher.write_text("""#!/bin/sh
dir="$(dirname "$0")"
export LD_LIBRARY_PATH="$dir:$dir/../formix-libs${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
export SAL_USE_VCLPLUGIN=svp
exec "$dir/soffice" "$@"
""")
os.chmod(launcher,0o755)
