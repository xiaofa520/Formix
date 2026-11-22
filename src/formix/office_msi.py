"""Read a verified LibreOffice MSI as data, without running system installation actions."""
import ctypes
import os
import re
import subprocess
import tempfile
from contextlib import contextmanager
from functools import lru_cache
from pathlib import Path


def prepare_local_office():
    """Publish a verified development runtime only after it can convert a file."""
    import hashlib
    import json
    if __package__:
        from .engine_install import probe
        from .runtime_paths import ROOT, SLUG, executable
    else:
        from engine_install import probe
        from runtime_paths import ROOT, SLUG, executable

    ready = executable("soffice")
    if ready:
        return ready
    deps = ROOT / "dependencies" / SLUG
    inventory = json.loads((deps / "inventory.json").read_text(encoding="utf-8"))
    entry = next((item for item in inventory["files"]
                  if re.fullmatch(r"LibreOffice[^/\\]*\.msi", item["file"], re.I)), None)
    if not entry:
        raise FileNotFoundError(f"No LibreOffice MSI in {deps}")
    package = deps / entry["file"]
    with package.open("rb") as stream:
        if hashlib.file_digest(stream, "sha256").hexdigest() != entry["sha256"]:
            raise ValueError(f"LibreOffice MSI checksum mismatch: {package.name}")
    cache = ROOT / "cache" / "office"
    cache.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=cache) as temp:
        folder = Path(temp) / "engine"
        folder.mkdir()
        binary = unpack(package, folder)
        version = json.loads((deps / "engine-versions.json").read_text(encoding="utf-8"))["libreoffice"]
        probe("libreoffice", binary, version, Path(temp))
        try:
            folder.rename(cache / SLUG)
        except OSError:
            if not executable("soffice"):
                raise
    return executable("soffice")


def unpack(package, folder):
    msi = ctypes.WinDLL("msi", winmode=0x800)  # LOAD_LIBRARY_SEARCH_SYSTEM32
    uint = ctypes.c_uint

    def check(code):
        if code:
            raise OSError(code, f"MSI: {ctypes.FormatError(code)}")

    @contextmanager
    def handle(function, *args):
        value = uint()
        check(function(*args, ctypes.byref(value)))
        try:
            yield value
        finally:
            msi.MsiCloseHandle(value)

    def records(sql):
        with handle(msi.MsiDatabaseOpenViewW, db, sql) as view:
            check(msi.MsiViewExecute(view, 0))
            while True:
                row = uint()
                code = msi.MsiViewFetch(view, ctypes.byref(row))
                if code == 259:  # ERROR_NO_MORE_ITEMS
                    break
                check(code)
                try:
                    yield row
                finally:
                    msi.MsiCloseHandle(row)

    def rows(sql, count):
        buffer = ctypes.create_unicode_buffer(4096)
        for row in records(sql):
            fields = []
            for index in range(1, count + 1):
                size = uint(len(buffer))
                check(msi.MsiRecordGetStringW(row, index, buffer, ctypes.byref(size)))
                fields.append(buffer.value)
            yield tuple(fields)

    def long_name(field):
        name = field.split(":", 1)[0].split("|")[-1]
        if name == ".":
            return ""
        if not name or name == ".." or Path(name).name != name:
            raise ValueError("Invalid name in MSI directory")
        return name

    with handle(msi.MsiOpenDatabaseW, str(package), None) as db:
        directories = {key: (parent, name) for key, parent, name in
                       rows("SELECT `Directory`, `Directory_Parent`, `DefaultDir` FROM `Directory`", 3)}
        components = dict(rows("SELECT `Component`, `Directory_` FROM `Component`", 2))

        @lru_cache(None)
        def directory(key):
            parent, name = directories[key]
            return directory(parent) / long_name(name) if parent else folder

        files = {key.casefold(): directory(components[component]) / long_name(name)
                 for key, component, name in rows("SELECT `File`, `Component_`, `FileName` FROM `File`", 3)}
        for (cab,) in rows("SELECT `Cabinet` FROM `Media`", 1):
            if not re.fullmatch(r"#[\w.-]+", cab):
                raise ValueError("Expected an embedded LibreOffice cabinet")
            with tempfile.TemporaryDirectory(dir=folder) as tmp:
                archive = Path(tmp) / "payload.cab"
                extracted = Path(tmp) / "files"
                extracted.mkdir()
                sql = f"SELECT `Data` FROM `_Streams` WHERE `Name`='{cab[1:]}'"
                for row in records(sql):
                    block = ctypes.create_string_buffer(1024 * 1024)
                    with archive.open("xb") as out:
                        while True:
                            size = uint(len(block))
                            check(msi.MsiRecordReadStream(row, 1, block, ctypes.byref(size)))
                            if not size.value:
                                break
                            out.write(block[:size.value])
                expand = Path(os.environ["SystemRoot"]) / "System32/expand.exe"
                subprocess.run([expand, "-F:*", archive, extracted], stdout=subprocess.DEVNULL,
                               stderr=subprocess.PIPE, creationflags=subprocess.CREATE_NO_WINDOW,
                               timeout=600, check=True)
                for source in extracted.iterdir():
                    dest = files.pop(source.name.casefold())
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    source.replace(dest)
        if files:
            raise ValueError("LibreOffice cabinet is incomplete")
    return next(folder.rglob("program/soffice.com"))
