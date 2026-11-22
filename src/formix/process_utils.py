"""Timeouts terminate owned process trees, including converter launchers."""
import os
import subprocess
import shutil
import tempfile

if __package__:
    from .runtime_paths import ROOT
else:
    from runtime_paths import ROOT


def run_pip(args, **kwargs):
    import psutil
    root = ROOT / "cache" / "python" / "tmp"
    root.mkdir(parents=True, exist_ok=True)
    for previous in root.glob("install-*-*"):
        pid = previous.name.split("-", 2)[1]
        if pid.isdecimal() and not psutil.pid_exists(int(pid)):
            shutil.rmtree(previous, ignore_errors=True)
    with tempfile.TemporaryDirectory(dir=root, prefix=f"install-{os.getpid()}-",
                                     ignore_cleanup_errors=True) as work:
        env = dict(os.environ)
        env.update(kwargs.pop('env', {}) or {})
        env.update(TEMP=work, TMP=work, TMPDIR=work,
                   PIP_CACHE_DIR=str((ROOT / 'cache' / 'python' / 'pip').resolve()),
                   UV_CACHE_DIR=str((ROOT / 'cache' / 'python' / 'uv').resolve()))
        return run_process(args, env=env, **kwargs)


def kill_tree(pid):
    import psutil
    try:
        root = psutil.Process(pid)
        children = root.children(recursive=True)
    except (psutil.NoSuchProcess, psutil.AccessDenied):
        return
    for process in [*reversed(children), root]:
        try:
            process.kill()
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass


def run_process(args, *, timeout, check=False, capture_output=False, **kwargs):
    if capture_output:
        kwargs.update(stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    kwargs.setdefault('creationflags', getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    with subprocess.Popen(args, **kwargs) as process:
        try:
            stdout, stderr = process.communicate(timeout=timeout)
        except BaseException:
            kill_tree(process.pid)
            process.kill()
            process.communicate()
            raise
        result = subprocess.CompletedProcess(args, process.returncode, stdout, stderr)
        if check:
            result.check_returncode()
        return result


def timeout_setting(name, default):
    try:
        return max(1, float(os.environ.get(name, default)))
    except (TypeError, ValueError):
        return default
