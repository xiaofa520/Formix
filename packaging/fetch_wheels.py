"""Fetch package files only for this machine's native build target."""
import argparse
import concurrent.futures
import hashlib
import shutil
import subprocess
import tomllib
from pathlib import Path
from urllib.parse import unquote, urlsplit
from urllib.request import url2pathname

ROOT = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser()
parser.add_argument("--platform", help="Override the host slug for a prepared native platform")
args = parser.parse_args()
if args.platform:
    slug = args.platform
else:
    import platform
    system, machine = platform.system(), platform.machine().lower()
    if system == "Windows":
        slug = "windows-arm64" if machine == "arm64" else "windows-x64"
    elif system == "Darwin":
        slug = "macos-arm64" if machine == "arm64" else "macos-x64"
    elif system == "Linux":
        slug = "linux-arm64" if machine in {"aarch64", "arm64"} else "linux-x64"
    else:
        raise SystemExit(f"Unsupported host OS {system}")
folder = ROOT / "dependencies" / slug
lock = folder / "pylock.toml"
if not lock.is_file():
    raise SystemExit(f"Run packaging/download_platform.py on the target OS first: {slug}")
wheels = folder / "wheels"
wheels.mkdir(exist_ok=True)


def checksum(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def fetch(package):
    spec = package.get("archive") or package["wheels"][0]
    local = spec.get("path")
    url = spec.get("url")
    if local:
        source = folder / local
        name = Path(local).name
    elif url.startswith("file:"):
        source = Path(url2pathname(urlsplit(url).path))
        name = source.name
    else:
        source = None
        name = Path(unquote(urlsplit(url).path)).name
    target = wheels / name
    expected = spec["hashes"]["sha256"]
    if target.exists() and checksum(target) == expected:
        return
    partial = target.with_suffix(target.suffix + ".part")
    if source:
        shutil.copyfile(source, partial)
    else:
        subprocess.run(["curl", "-fLsS", "--retry", "5", "--retry-all-errors", "--connect-timeout", "20", "--speed-time", "60", "--speed-limit", "128", "-o", str(partial), url], check=True)
    if checksum(partial) != expected:
        partial.unlink(missing_ok=True)
        raise ValueError(f"SHA-256 mismatch for {name}")
    partial.replace(target)
    print(name, flush=True)

packages = tomllib.loads(lock.read_text())["packages"]
with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
    list(pool.map(fetch, packages))
print(f"Prepared {len(packages)} packages for {slug}")
