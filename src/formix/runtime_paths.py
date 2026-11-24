import json
import os
import platform
import shutil
import sys
from pathlib import Path

MODULE_ROOT = Path(__file__).resolve().parent
if MODULE_ROOT.parent.name == "src" and (MODULE_ROOT.parent.parent / "pyproject.toml").is_file():
    ROOT = MODULE_ROOT.parent.parent
elif (MODULE_ROOT.parent / "release.txt").is_file():
    ROOT = MODULE_ROOT.parent
else:
    ROOT = MODULE_ROOT
SYSTEM = platform.system()
MACHINE = platform.machine().lower()
ARCH = "arm64" if MACHINE in {"arm64", "aarch64"} else "x64"
if SYSTEM == "Windows":
    SLUG = f"windows-{ARCH}"
    ASSET = f"Formix-{SLUG}.exe"
elif SYSTEM == "Darwin":
    SLUG = f"macos-{ARCH}"
    ASSET = f"Formix-{SLUG}.pkg"
elif SYSTEM == "Linux":
    SLUG = f"linux-{ARCH}"
    ASSET = f"Formix-{SLUG}.tar.gz"
else:
    raise RuntimeError(f"Unsupported operating system: {SYSTEM}")
FEED = "https://api.github.com/repos/xiaofa520/Formix/releases/latest"


def script_path(name):
    """Resolve subprocess entry points in source and bytecode-only releases."""
    source = MODULE_ROOT / name
    if source.is_file():
        return str(source)
    compiled = source.with_suffix('.pyc')
    if compiled.is_file():
        return str(compiled)
    raise FileNotFoundError(f'Missing application entry point: {name}')


def app_version():
    release = ROOT / "release.txt"
    return release.read_text(encoding="ascii").strip() if release.is_file() else "1.2.9"


def group_windows_processes():
    """Children inherit the GUI's kernel job from the moment they start."""
    if SYSTEM != "Windows":
        return
    import ctypes
    import warnings
    from ctypes import wintypes
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.CreateJobObjectW.argtypes = (ctypes.c_void_p, wintypes.LPCWSTR)
    kernel.CreateJobObjectW.restype = wintypes.HANDLE
    kernel.AssignProcessToJobObject.argtypes = (wintypes.HANDLE, wintypes.HANDLE)
    kernel.CloseHandle.argtypes = (wintypes.HANDLE,)
    job = kernel.CreateJobObjectW(None, None)
    try:
        if not job or not kernel.AssignProcessToJobObject(job, wintypes.HANDLE(-1)):
            warnings.warn(f"Windows process grouping unavailable: {ctypes.WinError(ctypes.get_last_error())}")
    finally:
        if job:
            # Membership keeps the job alive until its last process exits.
            kernel.CloseHandle(job)


def missing_runtime(error, exit_code):
    detail = error.strip()
    for component in ("libvips", "libreoffice"):
        if f"Optional engine not installed: {component}" in detail:
            return component
    if SYSTEM == "Windows":
        import re
        dlls = ("vcruntime140.dll", "vcruntime140_1.dll", "msvcp140.dll")
        if re.search(r"(?i)(?:not found|missing|找不到|无法找到).*?(?:vcruntime140(?:_1)?|msvcp140)\.dll|(?:vcruntime140(?:_1)?|msvcp140)\.dll.*?(?:missing|not found|找不到)", detail):
            return "vc"
        if exit_code & 0xffffffff == 0xc0000135:
            system_dir = Path(os.environ.get("SystemRoot", "C:/Windows")) / "System32"
            if any(not (system_dir / name).is_file() for name in dlls):
                return "vc"
    if detail.startswith("No LibreOffice MSI in ") or detail == "请安装 LibreOffice，或将 soffice 加入 PATH":
        return "office"
    if detail == "请安装 FFmpeg 并将其加入 PATH":
        return "ffmpeg"
    if detail == "Bundled engine is missing. Repair Formix using the installer." or any(
        f"No module named '{module}'" in detail for module in ("pyvips", "_libvips", "pypdfium2", "pdfplumber", "pymupdf", "fitz")
    ):
        return "repair"
    return None


def engine_store():
    if SYSTEM == "Windows":
        base = Path(os.environ.get("LOCALAPPDATA") or Path.home() / "AppData/Local")
    elif SYSTEM == "Darwin":
        base = Path.home() / "Library/Application Support"
    else:
        base = Path(os.environ.get("XDG_DATA_HOME") or Path.home() / ".local/share")
    return base / "Formix" / "engines" / SLUG


def active_engine(component):
    folder = engine_store() / component
    try:
        info = json.loads((folder / "active.json").read_text("utf-8"))
        entry = (folder / info["entry"]).resolve()
        if (entry.is_relative_to(folder.resolve()) and isinstance(info["version"], str)
                and (entry.is_dir() if component == "libvips" else entry.is_file())):
            return info["version"], entry
    except (OSError, ValueError, TypeError, KeyError):
        pass
    return None


def use_worker_modules(component):
    if component == 'pdf' and (ROOT / 'pyproject.toml').is_file():
        local = ROOT / 'dependencies' / 'pdf-layout'
        try:
            receipt = json.loads((local / 'formix-runtime.json').read_text('utf-8'))
            if (receipt == {'platform': SLUG, 'python': sys.implementation.cache_tag}
                    and str(local) not in sys.path):
                sys.path.append(str(local))
        except (OSError, ValueError):
            pass
    folder = engine_store() / ("python-" + component + "-" + sys.implementation.cache_tag)
    try:
        name = (folder / "current").read_text(encoding="ascii").strip()
        if name.startswith("site-") and name == Path(name).name and (folder / name).is_dir():
            sys.path.insert(0, str(folder / name))
    except FileNotFoundError:
        pass


def ncm_cache_dir():
    """Return a writable NCM source cache, preferring the project root."""
    preferred = ROOT / "cache" / "ncm"
    try:
        preferred.mkdir(parents=True, exist_ok=True)
        probe = preferred / ".write-check"
        probe.touch(exist_ok=True)
        probe.unlink(missing_ok=True)
        return preferred
    except OSError:
        if SYSTEM == "Windows":
            base = Path(os.environ.get("LOCALAPPDATA") or Path.home() / "AppData/Local")
        elif SYSTEM == "Darwin":
            base = Path.home() / "Library/Caches"
        else:
            base = Path(os.environ.get("XDG_CACHE_HOME") or Path.home() / ".cache")
        fallback = base / "Formix" / "cache" / "ncm"
        fallback.mkdir(parents=True, exist_ok=True)
        return fallback


def downloaded_engine_present(component):
    if component not in {"ffmpeg", "libvips", "libreoffice"}:
        return False
    folder = engine_store() / component
    try:
        return any(child.name != "update.lock" for child in folder.iterdir())
    except OSError:
        return False


def optional_engine_missing(component):
    """Only explicitly omitted release engines require a user-initiated download."""
    if component not in {"libvips", "libreoffice"} or not (ROOT / "release.txt").is_file():
        return False
    if active_engine(component):
        return False
    try:
        versions = json.loads((ROOT / "engine-versions.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return False
    return component not in versions


def load_vips(directory=None):
    if directory is None and optional_engine_missing("libvips"):
        raise RuntimeError("Optional engine not installed: libvips")
    use_worker_modules("libvips")
    if directory is None:
        active = active_engine("libvips")
        directory = active[1] if active else None
    if directory is not None:
        directory = Path(directory).resolve()
        sys.path.insert(0, str(directory))
        import _libvips
        if Path(_libvips.__file__).resolve().parent != directory:
            raise RuntimeError("Could not load the selected libvips binary")
    import pyvips
    if directory is not None and not pyvips.API_mode:
        raise RuntimeError("Incompatible libvips binary")
    return pyvips


def executable(name):
    if name == "soffice" and optional_engine_missing("libreoffice"):
        raise RuntimeError("Optional engine not installed: libreoffice")
    active = active_engine("ffmpeg" if name == "ffmpeg" else "libreoffice")
    if active:
        return str(active[1])
    folder = ROOT / "vendor"
    if name == "ffmpeg":
        path = folder / ("ffmpeg.exe" if SYSTEM == "Windows" else "ffmpeg")
        if path.is_file():
            return str(path)
    else:
        if SYSTEM == "Darwin":
            path = folder / "LibreOffice.app/Contents/MacOS/soffice"
            if path.is_file():
                return str(path)
        else:
            filename = "soffice.com" if SYSTEM == "Windows" else "soffice"
            for candidate in folder.glob(f"office/**/program/{filename}"):
                if candidate.is_file():
                    if SYSTEM == "Linux":
                        wrapper = candidate.with_name("formix-office")
                        return str(wrapper if wrapper.is_file() else candidate)
                    return str(candidate)
    if (ROOT / "release.txt").exists():
        raise RuntimeError("Bundled engine is missing. Repair Formix using the installer.")
    if name == "ffmpeg":
        local = ROOT / "dependencies" / SLUG / "ffmpeg" / ("ffmpeg.exe" if SYSTEM == "Windows" else "ffmpeg")
        if local.is_file():
            return str(local)
    if name == "soffice" and SYSTEM == "Windows":
        cached = ROOT / "cache" / "office" / SLUG
        for program in cached.glob("**/program/soffice.com"):
            if program.is_file():
                return str(program)
    path = shutil.which(name)
    if path or name != "soffice":
        return path
    for candidate in (Path("C:/Program Files/LibreOffice/program/soffice.com"),
                      Path("/Applications/LibreOffice.app/Contents/MacOS/soffice")):
        if candidate.is_file():
            return str(candidate)
    return None
