"""Inventory the exact native engines selected for this platform bundle."""
import json
import re
import subprocess
import tomllib
import zipfile
from pathlib import Path
from urllib.parse import unquote, urlsplit


def write_versions(folder):
    packages = {p["name"]: p for p in tomllib.loads((folder / "pylock.toml").read_text("utf-8"))["packages"]}
    ffmpeg = folder / "ffmpeg" / ("ffmpeg.exe" if folder.name.startswith("windows") else "ffmpeg")
    if ffmpeg.is_file():
        banner = subprocess.check_output([str(ffmpeg), "-version"], timeout=10)
        ff_version = re.search(rb"ffmpeg version (\S+)", banner)[1].decode()
    else:
        wheel = packages["imageio-ffmpeg"]["wheels"][0]
        filename = Path(unquote(urlsplit(wheel["url"]).path)).name
        with zipfile.ZipFile(folder / "wheels" / filename) as archive:
            member = next(n for n in archive.namelist() if "/binaries/ffmpeg-" in n)
            ff_version = re.search(r"-v([\d.]+?)(?:\.exe)?$", member)[1]
    office = next(p for p in sorted(folder.glob("LibreOffice*")) if p.suffix in {".msi", ".dmg", ".gz"})
    office_version = re.search(r"LibreOffice[_-](\d+(?:\.\d+)+)", office.name)[1]
    versions = {"ffmpeg": ff_version, "libvips": packages["pyvips-binary"]["version"], "libreoffice": office_version}
    target = folder / "engine-versions.json"
    target.write_text(json.dumps(versions, indent=2) + "\n", encoding="utf-8")
    return target
