import hashlib
import shutil
import json
import errno
import io
import os
import zipfile
import xml.etree.ElementTree as ET
import re
import subprocess
import sys
import tempfile
import urllib.request
from pathlib import Path
if __package__:
    from .runtime_paths import ASSET, FEED, ROOT, SLUG, active_engine, app_version, engine_store, executable
    from .engine_install import install
else:
    from runtime_paths import ASSET, FEED, ROOT, SLUG, active_engine, app_version, engine_store, executable
    from engine_install import install
from packaging.tags import sys_tags
from packaging.utils import parse_wheel_filename
from packaging.version import Version


def bundled_versions():
    folder = ROOT if (ROOT / "release.txt").exists() else ROOT / "dependencies" / SLUG
    try:
        result = json.loads((folder / "engine-versions.json").read_text("utf-8"))
        return result if isinstance(result, dict) else {}
    except (OSError, ValueError):
        return {}


def cache_folder(*parts):
    base = ROOT / "cache"
    if sys.platform == "win32":
        fallback = Path(os.environ.get("LOCALAPPDATA", Path.home())) / "Formix" / "cache"
    elif sys.platform == "darwin":
        fallback = Path.home() / "Library" / "Caches" / "Formix"
    else:
        fallback = Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache")) / "Formix"
    folder = (fallback if os.environ.get("APPIMAGE") else base).joinpath(*parts)
    try:
        folder.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryFile(dir=folder):
            pass
    except OSError as exc:
        if exc.errno not in (errno.EACCES, errno.EPERM, errno.EROFS):
            raise
        folder = fallback.joinpath(*parts)
        folder.mkdir(parents=True, exist_ok=True)
    return folder


def request(url, **headers):
    return urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "Formix-updater", **headers}), timeout=60)


def wheel_release(component):
    project = "imageio-ffmpeg" if component == "ffmpeg" else "pyvips-binary"
    with request(f"https://pypi.org/pypi/{project}/json") as response:
        release = json.load(response)
    supported = set(sys_tags())
    for file in release["urls"]:
        name = file["filename"]
        if file.get("yanked") or not name.endswith(".whl") or not supported.intersection(parse_wheel_filename(name)[3]):
            continue
        version = release["info"]["version"]
        if component == "ffmpeg":
            # Only the ZIP directory is needed to read the bundled FFmpeg version.
            with request(file["url"], Range="bytes=-65536") as tail:
                if tail.status != 206:
                    raise ValueError("The server did not return the wheel directory")
                with zipfile.ZipFile(io.BytesIO(tail.read(65536))) as archive:
                    member = next(n for n in archive.namelist() if "/binaries/ffmpeg-" in n)
                version = re.search(r"-v([\d.]+?)(?:\.exe)?$", member)[1]
        return dict(version=str(Version(version)), name=name, url=file["url"], size=file["size"], sha256=file["digests"]["sha256"])
    raise ValueError(f"No compatible {project} binary for {SLUG}")


def office_release():
    base = "https://download.documentfoundation.org/libreoffice/stable/"
    with request(base) as response:
        versions = re.findall(r'href="(\d+(?:\.\d+)+)/"', response.read().decode())
    version = str(max(map(Version, versions)))
    system, arch = SLUG.split("-")
    cpu = "x86_64" if arch == "x64" else "aarch64"
    if system == "windows":
        directory = f"win/{cpu}"
        suffix = "Win_x86-64.msi" if arch == "x64" else "Win_aarch64.msi"
    elif system == "macos":
        directory, suffix = f"mac/{cpu}", f"MacOS_{cpu}.dmg"
    else:
        linux_cpu = "x86-64" if arch == "x64" else cpu
        directory, suffix = f"deb/{cpu}", f"Linux_{linux_cpu}_deb.tar.gz"
    name = f"LibreOffice_{version}_{suffix}"
    url = f"{base}{version}/{directory}/{name}"
    with request(url + ".meta4") as response:
        file = ET.parse(response).find(".//{*}file")
    if file is None or file.get("name") != name:
        raise ValueError("Unexpected LibreOffice release metadata")
    return dict(version=version, name=name, url=url, size=int(file.findtext("{*}size")),
                sha256=file.findtext("{*}hash[@type='sha-256']"))


def engine_release(component):
    if component not in {"ffmpeg", "libvips", "libreoffice"}:
        raise ValueError("Unknown conversion engine")
    asset = office_release() if component == "libreoffice" else wheel_release(component)
    if not re.fullmatch(r"[0-9a-fA-F]{64}", asset.get("sha256") or "") or Path(asset["name"]).name != asset["name"]:
        raise ValueError("Invalid download metadata")
    return asset


def local_version(component):
    active = active_engine(component)
    if active:
        return active[0]
    recorded = bundled_versions().get(component)
    if isinstance(recorded, str) and recorded:
        return recorded
    current = None
    build = None
    if component == "libvips":
        try:
            import pyvips
            current = ".".join(str(pyvips.version(i)) for i in range(3))
        except (ImportError, OSError):
            pass
    else:
        is_ffmpeg = component == "ffmpeg"
        try:
            program = executable("ffmpeg" if is_ffmpeg else "soffice")
        except RuntimeError:
            program = None
        if program:
            try:
                output = subprocess.check_output([program, "-version" if is_ffmpeg else "--version"],
                                                 stderr=subprocess.STDOUT, timeout=10)
            except (OSError, subprocess.SubprocessError):
                return None
            prefix = r"ffmpeg version n?" if is_ffmpeg else r"LibreOffice "
            banner = output.decode(errors="replace")
            match = re.search(prefix + r"(\d+\.\d+(?:\.\d+)*)", banner)
            if match:
                current = match.group(1)
            elif is_ffmpeg:
                identifier = re.search(r"ffmpeg version (\S+)", banner)
                if identifier:
                    build = identifier.group(1)
    return current or build


def check_engine(component):
    asset = engine_release(component)
    current = local_version(component)
    numeric = re.match(r"^n?(\d+\.\d+(?:\.\d+)*)", current or "")
    available = not numeric or Version(numeric[1]) < Version(asset["version"])
    return dict(local=current, build=current if not numeric else None, available=available,
                version=asset["version"], size=asset["size"])


def verified(path, asset):
    if not path.is_file() or path.stat().st_size != asset["size"]:
        return False
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest() == asset["sha256"]


def fetch_engine(component, version, progress):
    asset = engine_release(component)
    if version != asset["version"]:
        raise ValueError("发行版本已变更，请重新检查更新")
    directory = cache_folder("engines", SLUG, component, version)
    target = directory / asset["name"]
    with tempfile.TemporaryDirectory(dir=directory) as tmp:
        if target.is_file():
            progress("verify")
        if not verified(target, asset):
            partial = Path(tmp) / target.name
            received = 0
            last = -1
            progress("download", 0)
            with request(asset["url"]) as response, partial.open("wb") as output:
                while chunk := response.read(1024 * 1024):
                    output.write(chunk)
                    received += len(chunk)
                    if received > asset["size"]:
                        raise ValueError("安装包完整性检查失败")
                    percent = received * 100 // max(1, asset["size"])
                    if percent != last:
                        progress("download", percent)
                        last = percent
            progress("verify")
            if not verified(partial, asset):
                raise ValueError("安装包完整性检查失败")
            partial.replace(target)
        record = dict(component=component, platform=SLUG, version=version, file=target.name, sha256=asset["sha256"])
        receipt = Path(tmp) / "version.json"
        receipt.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
        receipt.replace(directory / receipt.name)
    return str(target)


def update_engine(component, version, progress):
    from PySide6.QtCore import QLockFile
    if component not in {"ffmpeg", "libvips", "libreoffice"}:
        raise ValueError("Unknown conversion engine")
    directory = engine_store() / component
    directory.mkdir(parents=True, exist_ok=True)
    lock = QLockFile(str(directory / "update.lock"))
    lock.setStaleLockTime(0)
    if not lock.tryLock(0):
        raise RuntimeError("Another engine update is in progress")
    try:
        package = Path(fetch_engine(component, version, progress))
        progress("install")
        return install(component, version, package)
    finally:
        lock.unlock()


def remove_engine(component):
    """Remove only separately downloaded engines, never bundled files or models."""
    from PySide6.QtCore import QLockFile
    if __package__:
        from .background_work import remove_tree
    else:
        from background_work import remove_tree
    if component not in {"ffmpeg", "libvips", "libreoffice"}:
        raise ValueError("Unknown conversion engine")
    base = engine_store().resolve()
    folder = base / component
    if folder.is_symlink() or folder.resolve().parent != base:
        raise ValueError("Invalid engine directory")
    if not folder.exists():
        return {"removed": component}
    lock = QLockFile(str(folder / "update.lock"))
    lock.setStaleLockTime(0)
    if not lock.tryLock(0):
        raise RuntimeError("Another engine update is in progress")
    try:
        (folder / "active.json").unlink(missing_ok=True)
        for child in folder.iterdir():
            if child.name == "update.lock":
                continue
            if child.is_symlink() or child.is_file():
                child.unlink()
            else:
                remove_tree(child)
        cache_base = cache_folder("engines", SLUG).resolve()
        cached = cache_base / component
        if cached.is_symlink() or cached.resolve().parent != cache_base:
            raise ValueError("Invalid engine cache directory")
        if cached.exists():
            remove_tree(cached)
    finally:
        lock.unlock()
    return {"removed": component}


def latest_release():
    request = urllib.request.Request(FEED, headers={"User-Agent":"Formix-engine-updater"})
    with urllib.request.urlopen(request, timeout=20) as response:
        return json.load(response)


def latest(release=None, *, for_repair=False):
    if release is None:
        release = latest_release()
    version = Version(release["tag_name"].lstrip("vV"))
    if not for_repair and version <= Version(app_version()):
        return None
    names = {ASSET.casefold()}
    system, arch = SLUG.rsplit('-', 1)
    label, extension = {'windows': ('win', 'exe'), 'macos': ('mac', 'pkg'), 'linux': ('linux', 'tar.gz')}[system]
    if system == 'linux' and (ROOT / 'package-format').is_file():
        kind = (ROOT / 'package-format').read_text(encoding='utf-8').strip()
        if kind in {'deb', 'appimage'}:
            extension = 'deb' if kind == 'deb' else 'appimage'
            names.clear()
    names.add(f"formix-{label}-{'64' if arch == 'x64' else arch}-v{version}.{extension}")
    for asset in release["assets"]:
        digest = asset.get("digest") or ""
        if asset["name"].casefold() in names and digest.startswith("sha256:"):
            return dict(name=asset["name"],version=str(version),size=asset["size"],digest=digest,url=asset["browser_download_url"])
    raise ValueError("发行页尚无适用于本机的新版引擎安装包")

def fetch(version, directory):
    asset = latest()
    if not asset or asset["version"] != version:
        raise ValueError("发行版本已变更，请重新检查更新")
    directory.mkdir(parents=True,exist_ok=True)
    name = asset.get("name", ASSET)
    if Path(name).name != name or "/" in name or "\\" in name:
        raise ValueError("Invalid release filename")
    target = directory / name
    with tempfile.TemporaryDirectory(dir=directory) as tmp:
        partial = Path(tmp)/name
        digest = hashlib.sha256()
        with urllib.request.urlopen(asset["url"],timeout=60) as response, partial.open("wb") as stream:
            while chunk := response.read(1024*1024):
                stream.write(chunk)
                digest.update(chunk)
        if partial.stat().st_size != asset["size"] or "sha256:"+digest.hexdigest()!=asset["digest"]:
            raise ValueError("安装包完整性检查失败")
        partial.replace(target)
    return str(target)

if __name__ == "__main__":
    try:
        if sys.argv[1:] in (["app-check"], ["release-notes"]):
            release = latest_release()
            result = {"tag": release["tag_name"], "notes": release.get("body") or ""}
            if sys.argv[1] == "app-check":
                try:
                    result["update"] = latest(release)
                except ValueError:
                    result["unavailable"] = True
        elif len(sys.argv) == 3 and sys.argv[1] == "check":
            result = check_engine(sys.argv[2])
        elif len(sys.argv) == 3 and sys.argv[1] == "remove":
            result = remove_engine(sys.argv[2])
        elif len(sys.argv) == 4 and sys.argv[1] == "download":
            def progress(phase, percent=None):
                print("FORMIX_UPDATE " + json.dumps([phase, percent]), file=sys.stderr, flush=True)
            result = update_engine(sys.argv[2], sys.argv[3], progress)
        elif len(sys.argv) == 3 and sys.argv[1] == "app-download":
            version = str(Version(sys.argv[2]))
            result = fetch(version, cache_folder("app", SLUG, version))
        else:
            result = latest() if len(sys.argv)==1 else fetch(sys.argv[1],Path(sys.argv[2]))
        print(json.dumps(result))
    except Exception as exc:
        print(str(exc),file=sys.stderr)
        sys.exit(1)
