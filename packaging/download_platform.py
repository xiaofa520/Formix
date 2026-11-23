"""Resolve and fetch only the runtime packages matching this host."""
import argparse
import hashlib
import os
import platform
import re
import shutil
import subprocess
import sys
import tarfile
import time
import urllib.request
import tomllib
from engine_versions import write_versions
from wheel_manifest import write_offline_requirements, package_artifact, materialize_wheel
from pathlib import Path
from urllib.parse import unquote, urlsplit

ROOT = Path(__file__).resolve().parents[1]
PYTHON_RELEASE = "3.11.15+20260602"
PLATFORMS = {
    ("Windows", "AMD64"): ("windows-x64", "x86_64-pc-windows-msvc", "x86_64-pc-windows-msvc"),
    ("Windows", "ARM64"): ("windows-arm64", "aarch64-pc-windows-msvc", "aarch64-pc-windows-msvc"),
    ("Darwin", "arm64"): ("macos-arm64", "aarch64-apple-darwin", "aarch64-apple-darwin"),
    ("Darwin", "x86_64"): ("macos-x64", "x86_64-apple-darwin", "x86_64-apple-darwin"),
    ("Linux", "x86_64"): ("linux-x64", "x86_64-manylinux_2_35", "x86_64-unknown-linux-gnu"),
    ("Linux", "aarch64"): ("linux-arm64", "aarch64-manylinux_2_35", "aarch64-unknown-linux-gnu"),
}
key = (platform.system(), platform.machine())
if key not in PLATFORMS:
    raise SystemExit(f"Unsupported build host: {key[0]} {key[1]}")
name, uv_tag, python_tag = PLATFORMS[key]
argument_parser = argparse.ArgumentParser()
argument_parser.add_argument("--refresh", action="store_true", help="re-resolve versions within the project requirements")
ARGS = argument_parser.parse_args()
DEST = ROOT / "dependencies" / name
SHARED = ROOT / "dependencies" / "shared"
WHEELS = DEST / "wheels"
SHARED.mkdir(parents=True, exist_ok=True)
WHEELS.mkdir(parents=True, exist_ok=True)


def sha256(file):
    with file.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def download(url, target):
    part = target.with_suffix(target.suffix + ".part")
    request = urllib.request.Request(url, headers={"User-Agent": "Formix-dependency-cache"})
    for attempt in range(3):
        try:
            with urllib.request.urlopen(request, timeout=90) as response, part.open("wb") as output:
                shutil.copyfileobj(response, output)
            part.replace(target)
            return
        except (OSError, urllib.error.URLError):
            part.unlink(missing_ok=True)
            if attempt == 2:
                raise
            time.sleep(2 ** attempt)


def get_wheels():
    lock = DEST / "pylock.toml"
    requirements = "\n".join((ROOT / "requirements.txt").read_text().splitlines() + (ROOT / "src" / "formix" / "requirements-model.txt").read_text().splitlines() + ["imageio-ffmpeg", "accelerate"])
    requirements_by_name = {}
    from packaging.requirements import Requirement
    from packaging.version import InvalidVersion, Version
    for line in requirements.splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            requirement = Requirement(line)
            if requirement.marker and not requirement.marker.evaluate():
                continue
            normalized = requirement.name.lower().replace("_", "-")
            requirements_by_name.setdefault(normalized, []).append(requirement)
    if lock.exists() and not ARGS.refresh:
        packages = tomllib.loads(lock.read_text())["packages"]
        locked_versions = {}
        for package in packages:
            normalized = package["name"].lower().replace("_", "-")
            try:
                locked_versions[normalized] = Version(package["version"])
            except InvalidVersion:
                continue
        lock_satisfies_requirements = all(
            normalized in locked_versions
            and all(requirement.specifier.contains(locked_versions[normalized], prereleases=True)
                    for requirement in specs)
            for normalized, specs in requirements_by_name.items()
        )
        if lock_satisfies_requirements and all(p["name"] != "opencv-python-headless" or p.get("wheels") for p in packages):
            return fetch_packages(packages, lock)
    source = ROOT / "build" / f"resolve-{name}-requirements.txt"
    source.parent.mkdir(parents=True, exist_ok=True)
    source.write_text(requirements, encoding="utf-8")
    command = ["uv", "pip", "compile", str(source), "--output-file", str(lock), "--python", sys.executable, "--python-version", "3.11", "--python-platform", uv_tag, "--find-links", str(SHARED), "--only-binary", "opencv-python-headless", "--quiet"]
    if platform.system() != "Darwin":
        command += ["--torch-backend", "cpu"]
    subprocess.run(command, cwd=ROOT, check=True)
    lock_text = lock.read_text()
    resolved = tomllib.loads(lock_text)
    for package in resolved["packages"]:
        for spec in ([package["archive"]] if "archive" in package else package.get("wheels", [])):
            if not spec.get("hashes", {}).get("sha256") and spec.get("url", "").startswith("file:"):
                from urllib.request import url2pathname
                local = Path(url2pathname(__import__("urllib.parse").parse.urlsplit(spec["url"]).path))
                digest = sha256(local)
                spec.setdefault("hashes", {})["sha256"] = digest
                lock_text = lock_text.replace("hashes = {}", f'hashes = {{ sha256 = "{digest}" }}', 1)
    lock.write_text(lock_text, encoding="utf-8")
    items = resolved["packages"]
    return fetch_packages(items, lock)

def fetch_packages(items, lock):
    prepared = []
    for package in items:
        spec = package_artifact(package)
        if "path" in spec:
            destination = (lock.parent / spec["path"]).resolve()
            if destination.parent != WHEELS.resolve():
                target = WHEELS / destination.name
                shutil.copyfile(destination, target)
                destination = target
        else:
            url = spec["url"]
            filename = Path(unquote(urlsplit(url).path)).name
            destination = WHEELS / filename
            if not destination.exists() or sha256(destination) != spec['hashes']['sha256']:
                download(url, destination)
        prepared.append(materialize_wheel(package, destination, WHEELS))
    return prepared


def get_python():
    triple = python_tag
    archive_name = f"cpython-3.11.15+20260602-{triple}-install_only_stripped.tar.gz"
    checksums = SHARED / "python-SHA256SUMS"
    if not checksums.exists():
        download("https://github.com/astral-sh/python-build-standalone/releases/download/20260602/SHA256SUMS", checksums)
    expected = next((line.split()[0] for line in checksums.read_text().splitlines() if line.endswith("  " + archive_name)), None)
    if not expected:
        raise ValueError(f"No standalone Python release for {triple}")
    target = DEST / "python-3.11.15.tar.gz"
    if not target.exists() or sha256(target) != expected:
        download(f"https://github.com/astral-sh/python-build-standalone/releases/download/20260602/{archive_name.replace('+','%2B')}", target)
    if sha256(target) != expected:
        raise ValueError("Python runtime hash mismatch")


def get_engines():
    system, machine = key
    if system == "Windows":
        arch = "arm64" if machine == "ARM64" else "x64"
        redist = DEST / f"vc_redist.{arch}.exe"
        download(f"https://aka.ms/vs/17/release/vc_redist.{arch}.exe", redist)
        # Validate the official signed executable before shipping it.
        environment = os.environ.copy()
        environment["FORMIX_REDIST"] = str(redist.resolve())
        shell = shutil.which("pwsh") or shutil.which("powershell")
        if not shell:
            raise RuntimeError("PowerShell is required to verify the Microsoft runtime")
        environment.pop("PSModulePath", None)
        subprocess.run([shell, "-NoProfile", "-NonInteractive", "-Command",
                        "$ErrorActionPreference='Stop'; "
                        "Import-Module ($PSHOME + '/Modules/Microsoft.PowerShell.Security/Microsoft.PowerShell.Security.psd1') -ErrorAction Stop; "
                        "$s=Get-AuthenticodeSignature -LiteralPath $env:FORMIX_REDIST; "
                        "if ($s.Status -ne 'Valid' -or $s.SignerCertificate.Subject -notmatch 'Microsoft Corporation') { exit 1 }"],
                       check=True, env=environment)
    major_minor = "26.8.2"
    if system == "Windows":
        arch = "aarch64" if machine == "ARM64" else "x86_64"
        file = f"LibreOffice_{major_minor}_Win_{arch.replace('_', '-')}.msi"
        relative = f"win/{arch}/{file}"
    elif system == "Darwin":
        arch = "aarch64" if machine == "arm64" else "x86_64"
        file = f"LibreOffice_{major_minor}_MacOS_{arch}.dmg"
        relative = f"mac/{arch}/{file}"
    else:
        arch = "x86-64" if machine == "x86_64" else "aarch64"
        file = f"LibreOffice_{major_minor}_Linux_{arch}_deb.tar.gz"
        relative = f"deb/{'x86_64' if machine == 'x86_64' else 'aarch64'}/{file}"
    metadata = DEST / "libreoffice.meta4"
    download(f"https://download.documentfoundation.org/libreoffice/stable/{major_minor}/{relative}.meta4", metadata)
    import xml.etree.ElementTree as ET
    item = ET.parse(metadata).find('.//{*}file')
    archive = DEST / item.attrib['name']
    if not archive.exists():
        mirrors = item.findall('{*}url')
        for mirror in mirrors:
            try:
                download(mirror.text, archive)
                break
            except Exception:
                archive.unlink(missing_ok=True)
        else:
            raise RuntimeError("Could not download LibreOffice from its official mirrors")
    expected = item.find('{*}hash[@type="sha-256"]').text
    if sha256(archive) != expected:
        archive.unlink(missing_ok=True)
        raise ValueError("LibreOffice archive hash mismatch")

if __name__ == "__main__":
    print(f"Preparing dependencies for {name} ({platform.machine()})", flush=True)
    get_python()
    packages = get_wheels()
    write_offline_requirements(packages, DEST)
    get_engines()
    write_versions(DEST)
    print(f"Ready: {len(packages)} locked wheels in {DEST}", flush=True)
