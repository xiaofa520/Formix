"""Start Formix with its private interpreter, including all child workers."""
import os
import platform
from pathlib import Path
import subprocess
import sys
import json
import hashlib


def configure_temporary_storage(root):
    """Keep application and inherited installer scratch files out of the project root."""
    import tempfile
    temporary = (root / 'cache' / 'python' / 'tmp').resolve()
    try:
        temporary.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryFile(dir=temporary):
            pass
    except OSError:
        if os.name == 'nt':
            base = Path(os.environ.get('LOCALAPPDATA') or Path.home() / 'AppData/Local')
        elif platform.system() == 'Darwin':
            base = Path.home() / 'Library/Caches'
        else:
            base = Path(os.environ.get('XDG_CACHE_HOME') or Path.home() / '.cache')
        temporary = base / 'Formix/python/tmp'
        temporary.mkdir(parents=True, exist_ok=True)
    for key in ('TEMP', 'TMP', 'TMPDIR'):
        os.environ[key] = str(temporary)
    tempfile.tempdir = str(temporary)
    os.environ['PIP_CACHE_DIR'] = str((temporary.parent / 'pip').resolve())
    os.environ['UV_CACHE_DIR'] = str((temporary.parent / 'uv').resolve())


def desktop_runtime(root, bundled):
    """Use an explicitly installed user runtime when the workspace is Low-labelled."""
    if os.name != 'nt':
        return bundled
    try:
        config = json.loads((root/'cache/desktop-runtime.json').read_text('utf-8-sig'))
        candidate = Path(config['python']).resolve()
        allowed = (Path(os.environ['LOCALAPPDATA'])/'Formix/runtimes').resolve()
        if allowed not in candidate.parents or candidate.name.lower() != 'python.exe':
            return bundled
        digest = hashlib.sha256(bundled.read_bytes()).hexdigest()
        if digest != config['source_sha256'] or hashlib.sha256(candidate.read_bytes()).hexdigest() != digest:
            return bundled
        return candidate
    except (OSError, ValueError, KeyError):
        return bundled


def main():
    source = Path(__file__).resolve().parent.parent
    root = source.parent if source.name == "src" else source
    relative = "runtime/Formix.exe" if os.name == "nt" else "python/bin/python3.11"
    python = root / relative
    chinese_host = root / "runtime/格式转换通.exe"
    if chinese_host.is_file():
        python = chinese_host
    if not python.is_file():
        python = root / "build/app" / relative
    if not python.is_file():
        system = {"Darwin": "macos", "Windows": "windows", "Linux": "linux"}.get(platform.system())
        arch = "arm64" if platform.machine().lower() in {"arm64", "aarch64"} else "x64"
        python = root / "build" / f"{system}-{arch}-app" / relative
    if not python.is_file():
        raise SystemExit(f"Formix private Python is missing: {python}")
    # A packaged application always uses its own native host.
    # Never delegate packaged work to a user-installed Python.
    for key in ("PYTHONHOME", "PYTHONPATH", "PYTHONUSERBASE", "VIRTUAL_ENV", "PIP_TARGET",
                "PIP_PREFIX", "PIP_USER"):
        os.environ.pop(key, None)
    os.environ["PYTHONNOUSERSITE"] = "1"
    os.environ["PIP_CONFIG_FILE"] = os.devnull
    os.environ["PATH"] = str(python.parent) + os.pathsep + os.environ.get("PATH", "")
    if Path(sys.executable).resolve().parent != python.resolve().parent or not sys.flags.isolated:
        return subprocess.call([str(python), "-I", __file__, *sys.argv[1:]])
    sys.executable = str(python)
    sys.path.insert(0, str(source))
    configure_temporary_storage(root)
    from formix.diagnostics import setup, install_exception_hooks
    setup()
    install_exception_hooks()
    from formix.main import main as run
    return run()


if __name__ == "__main__":
    raise SystemExit(main())
