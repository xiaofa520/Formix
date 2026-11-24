"""Check private engines outside the GUI and repair only unusable components."""
import json
import shutil
import subprocess
import sys
import tempfile
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

if __package__:
    from .engine_update import bundled_versions, engine_release, install, update_engine, verified
    from .runtime_paths import ROOT, SLUG, engine_store, executable, missing_runtime
    from .process_utils import run_pip, kill_tree, run_process, timeout_setting
else:
    from engine_update import bundled_versions, engine_release, install, update_engine, verified
    from runtime_paths import ROOT, SLUG, engine_store, executable, missing_runtime
    from process_utils import run_pip, kill_tree, run_process, timeout_setting


def check(component):
    with tempfile.TemporaryDirectory(prefix="formix-check-") as tmp:
        folder = Path(tmp)
        module_path = f"import sys; sys.path.insert(0, {str(Path(__file__).resolve().parent)!r}); "
        if component == "libreoffice":
            source = folder / "probe.txt"
            source.write_text("Formix", encoding="utf-8")
            cmd = [executable("soffice"), "-env:UserInstallation=" + (folder / "profile").as_uri(),
                   "--headless", "--norestore", "--convert-to", "pdf", "--outdir", tmp, str(source)]
        elif component == "ffmpeg":
            cmd = [executable("ffmpeg"), "-version"]
        elif component == "pdf":
            cmd = [sys.executable, "-X", "utf8", "-c", module_path + "from runtime_paths import use_worker_modules; "
                   "use_worker_modules('pdf'); import pdfplumber,pypdfium2,docx,pptx,PIL.Image,pdf2docx; "
                   "from docx import Document; Document()"]
        else:
            cmd = [sys.executable, "-X", "utf8", "-c", module_path +
                   "import json; from worker import image_output_formats; "
                   "print(json.dumps({'image_formats': image_output_formats()}))"]
        if not cmd[0]:
            raise FileNotFoundError(component)
        result = run_process(cmd, stdout=subprocess.PIPE if component == 'libvips' else subprocess.DEVNULL,
                             stderr=subprocess.PIPE, cwd=ROOT, check=True, timeout=35)
        if component == 'libvips':
            return json.loads(result.stdout)
        if component == "libreoffice":
            with source.with_suffix(".pdf").open("rb") as pdf:
                if pdf.read(5) != b"%PDF-":
                    raise ValueError("LibreOffice PDF probe failed")


def install_worker_modules(component):
    packages, probe = {
        "pdf": (["pdf2docx==0.5.13", "PyMuPDF>=1.26.7,<2", "pdfplumber>=0.11", "pypdfium2>=4.30", "python-docx>=1.1", "python-pptx>=1.0", "Pillow>=10"],
                "import pdfplumber,pypdfium2,docx,pptx,PIL.Image,pdf2docx; from docx import Document; Document()"),
        "libvips": (["pyvips[binary]>=3.0"], "import pyvips; pyvips.Image.black(2,2).write_to_buffer('.png')"),
    }[component]
    folder = engine_store() / ("python-" + component + "-" + sys.implementation.cache_tag)
    folder.mkdir(parents=True, exist_ok=True)
    candidate = Path(tempfile.mkdtemp(prefix="site-", dir=folder))
    try:
        run_pip([sys.executable, "-m", "pip", "install", "--no-input", "--no-cache-dir",
                        "--target", str(candidate), *packages], check=True, stdout=sys.stderr,
                    timeout=timeout_setting('FORMIX_RUNTIME_TIMEOUT', 1800))
        run_process([sys.executable, "-c", "import sys; sys.path.insert(0,sys.argv[1]); " + probe,
                        str(candidate)], check=True, timeout=60)
        receipt = candidate / "current.tmp"
        receipt.write_text(candidate.name, encoding="ascii")
        receipt.replace(folder / "current")
    except Exception:
        shutil.rmtree(candidate, ignore_errors=True)
        raise


def repair(component):
    # Development checkouts can recover Office offline from the verified MSI.
    deps = ROOT / "dependencies" / SLUG
    if component == "libreoffice" and sys.platform == "win32" and (deps / "inventory.json").is_file():
        for item in json.loads((deps / "inventory.json").read_text(encoding="utf-8"))["files"]:
            path = deps / item["file"]
            if path.name.startswith("LibreOffice") and path.suffix.lower() == ".msi":
                if verified(path, {"size": item["bytes"], "sha256": item["sha256"]}):
                    try:
                        install(component, bundled_versions()[component], path)
                        return
                    except (OSError, RuntimeError, ValueError) as error:
                        print(f"Local LibreOffice repair failed: {error}", file=sys.stderr)
    version = engine_release(component)["version"]
    update_engine(component, version, lambda *_: None)


def ensure(component):
    if __package__:
        from .runtime_paths import optional_engine_missing
    else:
        from runtime_paths import optional_engine_missing
    if optional_engine_missing(component):
        return {"optional_missing": True}
    try:
        return check(component) or {}
    except Exception as error:
        if isinstance(error, subprocess.CalledProcessError):
            detail = (error.stderr or b"").decode(errors="replace")
            manual = missing_runtime(detail, error.returncode)
            if manual == "vc":
                return {"manual": "vc"}
        if sys.platform == "win32":
            import ctypes
            try:
                for dll in ("msvcp140.dll", "vcruntime140.dll", "vcruntime140_1.dll"):
                    ctypes.WinDLL(dll)
            except OSError:
                return {"manual": "vc"}
        print(json.dumps({"component": component, "preparing": True}), flush=True)
        if component == "pdf" or (component == "libvips" and isinstance(error, subprocess.CalledProcessError)
                                  and b"No module named 'pyvips'" in (error.stderr or b"")):
            install_worker_modules(component)
        else:
            repair(component)
        return check(component) or {}


def check_independently(name, output_lock):
    command = [sys.executable, '-X', 'utf8', str(Path(__file__).resolve()), '--component', name]
    with subprocess.Popen(command, stdout=subprocess.PIPE, stderr=sys.stderr,
                          creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0)) as process:
        timed_out = threading.Event()
        def expire():
            timed_out.set()
            kill_tree(process.pid)
        timer = threading.Timer(timeout_setting('FORMIX_RUNTIME_TIMEOUT', 1800), expire)
        timer.daemon = True
        timer.start()
        completed = False
        try:
            for line in process.stdout:
                try:
                    record = json.loads(line)
                except (ValueError, UnicodeError):
                    continue
                if record.get('component') != name:
                    continue
                completed = completed or not record.get('preparing')
                with output_lock:
                    print(json.dumps(record), flush=True)
            process.wait()
        finally:
            timer.cancel()
        if not completed:
            error = 'Runtime check timed out' if timed_out.is_set() else 'Runtime check failed'
            with output_lock:
                print(json.dumps({'component': name, 'error': error}), flush=True)


if __name__ == "__main__":
    components = ('ffmpeg', 'libvips', 'pdf', 'libreoffice')
    if len(sys.argv) == 3 and sys.argv[1] == '--component' and sys.argv[2] in components:
        name = sys.argv[2]
        try:
            status = ensure(name)
        except Exception as error:
            status = {'error': str(error)}
        print(json.dumps({'component': name, **status}), flush=True)
    elif len(sys.argv) == 1:
        lock = threading.Lock()
        with ThreadPoolExecutor(max_workers=len(components)) as pool:
            futures = [pool.submit(check_independently, name, lock) for name in components]
            for future in futures:
                future.result()
    else:
        raise SystemExit('Unknown runtime component')
