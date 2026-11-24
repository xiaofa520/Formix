"""Assemble an application folder from only the current native dependency cache."""
import importlib.util
import os
import platform
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
from pathlib import Path
from urllib.parse import unquote
import tomllib
from engine_versions import write_versions

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "src" / "formix"
SYSTEM = platform.system()
MACHINE = platform.machine().lower()
if SYSTEM == "Windows":
    SLUG = "windows-arm64" if MACHINE == "arm64" else "windows-x64"
    PYTHON_EXE = "python.exe"
elif SYSTEM == "Darwin":
    SLUG = "macos-arm64" if MACHINE == "arm64" else "macos-x64"
    PYTHON_EXE = "bin/python3.11"
elif SYSTEM == "Linux":
    SLUG = "linux-arm64" if MACHINE in {"arm64", "aarch64"} else "linux-x64"
    PYTHON_EXE = "bin/python3.11"
else:
    raise SystemExit(f"Unsupported packaging OS: {SYSTEM}")

parser = __import__("argparse").ArgumentParser()
parser.add_argument("version")
args = parser.parse_args()
if not re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+", args.version):
    parser.error("Use a MAJOR.MINOR.PATCH release version.")
deps = ROOT / "dependencies" / SLUG
lock = deps / "pylock.toml"
if not lock.is_file():
    raise SystemExit(f"No dependency cache for this machine ({SLUG}). Run packaging/download_platform.py first.")
app = ROOT / "build" / f"{SLUG}-app"
if app.exists():
    raise SystemExit(f"Build folder already exists: {app}. Move it aside before rebuilding.")
app.mkdir(parents=True)
package = app / "formix"
shutil.copytree(SOURCE, package, ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "*.pyo"))
shutil.copy2(ROOT / "main.py", app / "main.py")

def run(*command):
    subprocess.run(list(map(str, command)), check=True)

with tarfile.open(deps / "python-3.11.15.tar.gz", "r:gz") as archive:
    archive.extractall(app, filter="data")
python = app / "python" / PYTHON_EXE
site = app / "python" / ("Lib/site-packages" if SYSTEM == "Windows" else "lib/python3.11/site-packages")
site.mkdir(parents=True, exist_ok=True)
# Also honor the lean payload when reusing an older dependency cache.
offline = ROOT / "build" / f"{SLUG}-offline.txt"
offline.write_text("\n".join(line for line in (deps / "offline.txt").read_text(encoding="utf-8").splitlines()
                             if not line.lower().startswith("pyvips-binary==")) + "\n", encoding="utf-8")
if shutil.which("uv"):
    run("uv", "pip", "install", "--python", python, "--no-index", "--find-links", deps / "wheels", "--require-hashes", "-r", offline)
else:
    run(python, "-m", "pip", "install", "--no-index", "--find-links", deps / "wheels", "--require-hashes", "-r", offline)

vendor = app / "vendor"
vendor.mkdir()
ffmpeg_dir = deps / "ffmpeg"
ffmpeg = ffmpeg_dir / ("ffmpeg.exe" if SYSTEM == "Windows" else "ffmpeg")
if not ffmpeg.is_file():
    # On Windows the selected ffmpeg wheel is the bundled binary source.
    name = next(package for package in tomllib.loads(lock.read_text())["packages"] if package["name"] == "imageio-ffmpeg")
    wheel = deps / "wheels" / Path(unquote(name["wheels"][0]["url"].split("/")[-1]))
    import zipfile
    ffmpeg_dir.mkdir(exist_ok=True)
    with zipfile.ZipFile(wheel) as archive:
        member = next(path for path in archive.namelist() if "/binaries/ffmpeg-" in path)
        with archive.open(member) as source, ffmpeg.open("wb") as target:
            shutil.copyfileobj(source, target)
    if SYSTEM != "Windows":
        ffmpeg.chmod(0o755)
shutil.copy2(ffmpeg, vendor / ffmpeg.name)

if SYSTEM == "Windows":
    arch = SLUG.split("-")[1]
    redist = next(path for path in deps.glob("*.exe") if arch in path.name.lower())
    shutil.copy2(redist, ROOT / "build" / f"vc_redist.{arch}.exe")
elif SYSTEM == "Linux":
    import tarfile as tf
    outer = next(deps.glob("LibreOffice*Linux*deb.tar.gz"))
    with tf.open(outer, "r:gz") as archive:
        archive.extractall(vendor / "office-debs", filter="data")
    office = vendor / "office"
    office.mkdir()
    for package in (vendor / "office-debs").rglob("*.deb"):
        run("dpkg-deb", "-x", package, office)
    shutil.rmtree(vendor / "office-debs")
    run(sys.executable, ROOT / "packaging" / "linux_libs.py", office)
    # Keep only the small host-library compatibility layer for later downloads.
    shutil.copytree(next(office.rglob("formix-libs")), vendor / "office-runtime-libs")
    shutil.rmtree(office)

shutil.copy2(ROOT / "README.md", app / "README.md")
if SYSTEM == "Windows":
    with tempfile.TemporaryDirectory(dir=ROOT / "build") as scratch:
        subprocess.run([str(ROOT / "packaging/build_host.cmd"), str(app / "python"),
                        SLUG.split("-")[1], args.version, str(app / "python/Formix.exe")],
                       cwd=scratch, check=True)
shutil.copy2(write_versions(deps), app / "engine-versions.json")
(app / "release.txt").write_text(args.version, encoding="ascii")
run(python, "-c", "import torch,torchvision,transformers,pdfplumber,pypdfium2,docx,openpyxl;from PySide6 import QtWidgets;from transformers import AutoModelForImageTextToText, AutoProcessor, GlmOcrForConditionalGeneration, AutoModelForCausalLM")
run(sys.executable, ROOT / "packaging/payload_integrity.py", "write", app)
print(f"Prepared {app} for {SLUG}")
