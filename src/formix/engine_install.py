"""Prepare private, immutable engines and publish one pointer after a conversion probe."""
import json
import os
import re
import shlex
import shutil
import sys
import tarfile
import tempfile
import zipfile
from pathlib import Path

if __package__:
    from .runtime_paths import ROOT, SYSTEM, engine_store
    from .process_utils import run_process
else:
    from runtime_paths import ROOT, SYSTEM, engine_store
    from process_utils import run_process


def run(*args, timeout=600, cwd=None):
    result = run_process(list(map(str, args)), cwd=cwd, capture_output=True, timeout=timeout)
    if result.returncode:
        reason = (result.stderr or result.stdout).decode(errors="replace").strip()[-500:]
        raise RuntimeError(reason or f"{Path(args[0]).name}: exit {result.returncode}")
    return result.stdout.decode(errors="replace")


def unpack_wheel(package, folder, component):
    with zipfile.ZipFile(package) as archive:
        if component == "ffmpeg":
            member = next(n for n in archive.namelist() if "/binaries/ffmpeg-" in n)
            entry = folder / ("ffmpeg.exe" if SYSTEM == "Windows" else "ffmpeg")
            with archive.open(member) as src, entry.open("xb") as dst:
                shutil.copyfileobj(src, dst)
            entry.chmod(0o755)
            return entry
        entry = folder / "site"
        for item in archive.infolist():
            parts = Path(item.filename).parts
            if not parts or item.is_dir():
                continue
            # Wheel .data/{platlib,purelib} belongs at the import root.
            if parts[0].endswith(".data"):
                if len(parts) < 3 or parts[1] not in {"platlib", "purelib"}:
                    continue
                parts = parts[2:]
            target = entry.joinpath(*parts)
            if not target.resolve().is_relative_to(entry.resolve()):
                raise ValueError("Invalid wheel path")
            target.parent.mkdir(parents=True, exist_ok=True)
            with archive.open(item) as src, target.open("xb") as dst:
                shutil.copyfileobj(src, dst)
        return entry


def unpack_deb(deb, folder):
    if shutil.which("dpkg-deb"):
        run("dpkg-deb", "-x", deb, folder)
        return
    # Also support non-Debian hosts. The official distribution contains ar
    # packages with a compressed data.tar member; only the private opt tree is needed.
    with deb.open("rb") as stream:
        if stream.read(8) != b"!<arch>\n":
            raise ValueError("Invalid Debian package")
        while header := stream.read(60):
            if len(header) != 60 or header[-2:] != b"`\n":
                raise ValueError("Invalid Debian package member")
            size = int(header[48:58])
            if header[:16].strip().rstrip(b"/").startswith(b"data.tar"):
                with tarfile.open(fileobj=stream, mode="r|*") as payload:
                    for item in payload:
                        if item.name.removeprefix("./").startswith("opt/"):
                            payload.extract(item, folder, filter="data")
                return
            stream.seek(size + size % 2, os.SEEK_CUR)
    raise ValueError("Missing Debian package payload")


def unpack_office(package, folder):
    if SYSTEM == "Windows":
        if __package__:
            from .office_msi import unpack
        else:
            from office_msi import unpack
        return unpack(package, folder)
    if SYSTEM == "Darwin":
        mount = Path(tempfile.mkdtemp(prefix="formix-office-"))
        try:
            run("hdiutil", "attach", "-readonly", "-nobrowse", "-quiet", "-mountpoint", mount, package)
            try:
                run("ditto", next(mount.glob("LibreOffice*.app")), folder / "LibreOffice.app")
            finally:
                run("hdiutil", "detach", mount)
        finally:
            if not mount.is_mount():
                mount.rmdir()
        return folder / "LibreOffice.app/Contents/MacOS/soffice"
    with tarfile.open(package, "r|gz") as outer, tempfile.TemporaryDirectory(dir=folder) as tmp:
        # Consume one Debian package at a time instead of expanding the entire archive twice.
        for item in outer:
            if item.isfile() and item.name.endswith(".deb"):
                deb = Path(tmp) / "part.deb"
                with outer.extractfile(item) as src, deb.open("wb") as dst:
                    shutil.copyfileobj(src, dst)
                unpack_deb(deb, folder)
    binary = next(folder.rglob("program/soffice"))
    wrapper = binary.with_name("formix-office")
    bundled_libs = next((ROOT / "vendor/office").glob("**/formix-libs"), None)
    fallback = ':' + shlex.quote(str(bundled_libs)) if bundled_libs else ''
    wrapper.write_text('#!/bin/sh\ndir="$(dirname "$0")"\nexport SAL_USE_VCLPLUGIN=svp\n'
                       f'export LD_LIBRARY_PATH="$dir"{fallback}"${{LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}}"\n'
                       'exec "$dir/soffice" "$@"\n', encoding="utf-8")
    wrapper.chmod(0o755)
    return wrapper


def probe(component, entry, version, tmp):
    if component == "libvips":
        package_dir = repr(str(Path(__file__).resolve().parent))
        script = (f"import sys; sys.path.insert(0, {package_dir}); "
                  "from runtime_paths import load_vips; v=load_vips(sys.argv[1]); "
                  "v.Image.black(2,2).write_to_buffer('.png'); print('.'.join(str(v.version(i)) for i in range(3)))")
        actual = run(sys.executable, "-X", "utf8", "-c", script, entry, cwd=ROOT, timeout=45).strip()
    elif component == "ffmpeg":
        banner = run(entry, "-version", timeout=20)
        actual = re.search(r"ffmpeg version n?(\d+(?:\.\d+)+)", banner)[1]
        run(entry, "-nostdin", "-loglevel", "error", "-f", "lavfi", "-i", "anullsrc",
            "-t", "0.05", tmp / "probe.wav", timeout=30)
    else:
        profile = "-env:UserInstallation=" + (tmp / "profile").as_uri()
        banner = run(entry, profile, "--version", timeout=30)
        actual = re.search(r"LibreOffice (\d+(?:\.\d+)+)", banner)[1]
        doc = tmp / "probe.txt"
        doc.write_text("Formix", encoding="utf-8")
        run(entry, profile, "--headless", "--convert-to", "pdf", "--outdir", tmp, doc, timeout=90)
        with doc.with_suffix(".pdf").open("rb") as pdf:
            if pdf.read(5) != b"%PDF-":
                raise ValueError("LibreOffice PDF probe failed")
    # LibreOffice's banner may include an extra build number; a binary wheel
    # can also carry a packaging revision after the native libvips version.
    if not (actual == version or component == "libreoffice" and actual.startswith(version + ".")
            or component == "libvips" and version.startswith(actual + ".")):
        raise ValueError(f"Expected {version}, found {actual}")


def install(component, version, package):
    folder = engine_store() / component
    folder.mkdir(parents=True, exist_ok=True)
    candidate = Path(tempfile.mkdtemp(prefix="engine-", dir=folder))
    try:
        entry = (unpack_office(package, candidate) if component == "libreoffice"
                 else unpack_wheel(package, candidate, component))
        with tempfile.TemporaryDirectory(dir=folder) as tmp:
            probe(component, entry, version, Path(tmp))
        receipt = candidate / "active.tmp"
        receipt.write_text(json.dumps({"version": version, "entry": entry.relative_to(folder).as_posix()}),
                           encoding="utf-8")
        # The old executable and receipt stay usable until this single rename.
        os.replace(receipt, folder / "active.json")
    except Exception:
        shutil.rmtree(candidate, ignore_errors=True)
        raise
    return {"version": version}
