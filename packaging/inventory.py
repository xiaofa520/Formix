"""Write a SHA-256 inventory for the host platform only."""
import hashlib
import json
import platform
import re
import tomllib
from pathlib import Path
from urllib.parse import unquote, urlsplit
from urllib.request import url2pathname

ROOT = Path(__file__).resolve().parents[1]
system, machine = platform.system(), platform.machine().lower()
if system == "Windows":
    slug = "windows-arm64" if machine == "arm64" else "windows-x64"
elif system == "Darwin":
    slug = "macos-arm64" if machine == "arm64" else "macos-x64"
elif system == "Linux":
    slug = "linux-arm64" if machine in {"aarch64", "arm64"} else "linux-x64"
else:
    raise SystemExit(f"Unsupported host: {system} {machine}")
folder = ROOT / "dependencies" / slug
lock = folder / "pylock.toml"
if not lock.is_file():
    raise SystemExit(f"No platform lock for {slug}")
files = []
missing = []

def record(file, expected=None):
    if not file.is_file():
        missing.append(file.relative_to(folder).as_posix())
        return
    with file.open("rb") as stream:
        digest = hashlib.file_digest(stream, "sha256").hexdigest()
    if expected and digest.lower() != expected.lower():
        raise ValueError(f"SHA-256 mismatch: {file}")
    files.append({"file": file.relative_to(folder).as_posix(), "bytes": file.stat().st_size, "sha256": digest})

for package in tomllib.loads(lock.read_text())["packages"]:
    spec = package.get("archive") or package["wheels"][0]
    if spec.get("path"):
        filename = Path(spec["path"]).name
        wheel_path = folder / "wheels" / filename
    elif spec["url"].startswith("file:"):
        source = Path(url2pathname(urlsplit(spec["url"]).path))
        filename = source.name
        wheel_path = folder / "wheels" / filename
    else:
        filename = Path(unquote(urlsplit(spec["url"]).path)).name
        wheel_path = folder / "wheels" / filename
    record(wheel_path, spec.get("hashes", {}).get("sha256"))
    if (folder / "wheels" / filename).exists() and package["name"] == "imageio-ffmpeg":
        executable = folder / "ffmpeg" / ("ffmpeg.exe" if system == "Windows" else "ffmpeg")
        executable.parent.mkdir(exist_ok=True)
        record(executable)
archive = folder / "python-3.11.15.tar.gz"
checksum_manifest = ROOT / "dependencies" / "shared" / "python-SHA256SUMS"
triple = {"windows-x64": "x86_64-pc-windows-msvc", "windows-arm64": "aarch64-pc-windows-msvc", "macos-arm64": "aarch64-apple-darwin", "macos-x64": "x86_64-apple-darwin", "linux-x64": "x86_64-unknown-linux-gnu", "linux-arm64": "aarch64-unknown-linux-gnu"}[slug]
archive_name = f"cpython-3.11.15+20260602-{triple}-install_only_stripped.tar.gz"
expected = next((row.split()[0] for row in checksum_manifest.read_text().splitlines() if row.endswith("  " + archive_name)), None)
record(archive, expected)
for engine in folder.glob("*.msi"):
    record(engine)
for engine in folder.glob("*.dmg"):
    record(engine)
for engine in folder.glob("*Linux*deb.tar.gz"):
    record(engine)
for engine in folder.glob("*VCRedist*.exe"):
    record(engine)
for engine in folder.glob("Microsoft Visual C++*.exe"):
    record(engine)
packages = tomllib.loads(lock.read_text())["packages"]
requirements = [f"{package['name']}=={package['version']} --hash=sha256:{(package.get('archive') or package['wheels'][0])['hashes']['sha256']}" for package in packages]
(folder / "offline.txt").write_text("\n".join(requirements) + "\n", encoding="utf-8")
manifest = {"platform": slug, "files": files, "missing": missing}
(folder / "inventory.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
print(f"{slug}: {len(files)} files, {sum(row['bytes'] for row in files) / 1024**3:.2f} GiB, {len(missing)} missing")
if missing:
    raise SystemExit(1)
