"""Write the hash-checked offline install input from the resolved lock."""
import re
import hashlib
import subprocess
import sys
import tempfile
import shutil
from pathlib import Path
from packaging.utils import canonicalize_name, parse_wheel_filename
from packaging.version import Version


def package_artifact(package):
    spec = package.get("archive") or next(iter(package.get("wheels", [])), None) or package.get("sdist")
    if not spec:
        raise ValueError(f"No installable artifact for {package['name']}")
    return spec


def materialize_wheel(package, archive, wheels):
    """Build verified source archives on the native runner before offline staging."""
    expected = package_artifact(package).get("hashes", {}).get("sha256", "")
    with archive.open("rb") as stream:
        digest = hashlib.file_digest(stream, "sha256").hexdigest()
    if digest != expected:
        raise ValueError(f"SHA-256 mismatch for {archive.name}")
    if archive.suffix == ".whl":
        wheel = archive
    else:
        with tempfile.TemporaryDirectory(prefix="wheel-build-", dir=wheels.parent) as temporary:
            subprocess.run([sys.executable, "-m", "pip", "wheel", "--no-cache-dir", "--no-deps", "--wheel-dir", temporary, str(archive.resolve())], check=True)
            built = list(Path(temporary).glob("*.whl"))
            if len(built) != 1:
                raise ValueError(f"Expected one wheel for {package['name']}, got {len(built)}")
            wheel = built[0]
            name, version, _, _ = parse_wheel_filename(wheel.name)
            if name != canonicalize_name(package['name']) or version != Version(package['version']):
                raise ValueError(f"Unexpected built wheel: {wheel.name}")
            destination = wheels / wheel.name
            shutil.copyfile(wheel, destination)
            wheel = destination
    with wheel.open("rb") as stream:
        digest = hashlib.file_digest(stream, "sha256").hexdigest()
    result = dict(package)
    result.pop("archive", None)
    result["wheels"] = [{"path": str(wheel.resolve()), "hashes": {"sha256": digest}}]
    return result

def write_offline_requirements(packages, folder):
    lines = []
    for package in packages:
        if not package.get("wheels") and not package.get("archive"):
            raise ValueError(f"Build source package before offline staging: {package['name']}")
        spec = package_artifact(package)
        digest = spec.get("hashes", {}).get("sha256", "")
        if not re.fullmatch(r"[0-9a-fA-F]{64}", digest):
            raise ValueError(f"Missing SHA-256 for {package['name']}")
        lines.append(f"{package['name']}=={package['version']} --hash=sha256:{digest}")
    path = folder / "offline.txt"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path
