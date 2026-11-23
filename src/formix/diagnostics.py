"""Asynchronous, bounded diagnostic logs; never write engine output on Qt's thread."""
import atexit
import json
import logging
from logging.handlers import QueueHandler, QueueListener, RotatingFileHandler
import os
from pathlib import Path
import queue
import re
import sys
import tempfile
import threading
import time

logger = logging.getLogger('formix')
logger.addHandler(logging.NullHandler())
logger.propagate = False
_listener = None
_handler = None
log_path = None
_cleanup_stop = None
_cleanup_thread = None


def clean_logs(folder, active_path=None, *, max_age_days=7, max_bytes=50*1024*1024):
    """Bound inactive Formix logs only; live processes keep their complete session."""
    import psutil
    cutoff = time.time() - max_age_days * 86400
    files = []
    for path in Path(folder).glob('formix-*.log*'):
        match = re.fullmatch(r'formix-\d{8}-\d{6}-(\d+)\.log(?:\.[1-3])?', path.name)
        if not match or path.is_symlink():
            continue
        try:
            stat = path.stat()
            protected = (path == active_path or psutil.pid_exists(int(match[1])))
            files.append((stat.st_mtime, path, stat.st_size, protected))
        except OSError:
            continue
    total = sum(row[2] for row in files)
    for modified, path, size, protected in sorted(files):
        if not protected and (modified < cutoff or total > max_bytes):
            try:
                path.unlink()
                total -= size
            except OSError:
                pass


def _maintain_logs(folder, active_path, stop):
    while not stop.is_set():
        try:
            clean_logs(folder, active_path)
        except Exception:
            pass  # Maintenance must never interrupt conversions or shutdown.
        stop.wait(3600)


def windows_appcontainer():
    """Report the current token only; never attempt to change its permissions."""
    if os.name != 'nt':
        return None
    import ctypes
    from ctypes import wintypes
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    security = ctypes.WinDLL('advapi32', use_last_error=True)
    kernel.GetCurrentProcess.restype = wintypes.HANDLE
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    security.OpenProcessToken.argtypes = [wintypes.HANDLE, wintypes.DWORD, ctypes.POINTER(wintypes.HANDLE)]
    security.GetTokenInformation.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(wintypes.DWORD)]
    token = wintypes.HANDLE()
    if not security.OpenProcessToken(kernel.GetCurrentProcess(), 8, ctypes.byref(token)):
        return None
    try:
        value, length = wintypes.DWORD(), wintypes.DWORD()
        if security.GetTokenInformation(token, 29, ctypes.byref(value), 4, ctypes.byref(length)):
            return bool(value.value)
    finally:
        kernel.CloseHandle(token)
    return None


class BufferedHandler(QueueHandler):
    dropped = 0

    def enqueue(self, record):
        try:
            if self.dropped:
                warning = logging.LogRecord('formix', logging.WARNING, '', 0,
                    f'log_overflow dropped={self.dropped}', (), None)
                self.queue.put_nowait(warning)
                self.dropped = 0
            self.queue.put_nowait(record)
        except queue.Full:
            self.dropped += 1


def setup(directory=None):
    global _listener, _handler, log_path, _cleanup_stop, _cleanup_thread
    if _listener is not None:
        return log_path
    if __package__:
        from .runtime_paths import ROOT
    else:
        from runtime_paths import ROOT
    candidates = [Path(directory)] if directory else [ROOT/'logs',
        Path(os.environ.get('LOCALAPPDATA', Path.home()/'.local/share'))/'Formix/logs',
        Path(tempfile.gettempdir())/'Formix/logs']
    failures = []
    for folder in candidates:
        try:
            folder.mkdir(parents=True, exist_ok=True)
            path = folder/f'formix-{time.strftime("%Y%m%d-%H%M%S")}-{os.getpid()}.log'
            handler = RotatingFileHandler(path, maxBytes=5*1024*1024, backupCount=3,
                                          encoding='utf-8')
            break
        except OSError as exc:
            failures.append(str(exc))
    else:
        return None  # Diagnostics must not prevent the application from starting.
    handler.setFormatter(logging.Formatter('%(asctime)s %(levelname)s pid=%(process)d thread=%(threadName)s %(message)s'))
    _handler = BufferedHandler(queue.Queue(maxsize=10000))
    logger.addHandler(_handler)
    logger.setLevel(logging.INFO)
    _listener = QueueListener(_handler.queue, handler)
    _listener.start()
    log_path = path
    _cleanup_stop = threading.Event()
    _cleanup_thread = threading.Thread(target=_maintain_logs,
        args=(folder, path, _cleanup_stop), name='formix-log-cleanup', daemon=True)
    _cleanup_thread.start()
    event('application_start', python=sys.version, executable=sys.executable,
          log_file=str(path), fallback_errors=failures, windows_appcontainer=windows_appcontainer())
    return path


def event(action, **fields):
    logger.info('%s %s', action, json.dumps(fields, ensure_ascii=False, default=str))


def install_exception_hooks():
    original = sys.excepthook
    def uncaught(kind, value, traceback):
        logger.critical('uncaught_exception', exc_info=(kind, value, traceback))
        original(kind, value, traceback)
    sys.excepthook = uncaught
    original_thread = threading.excepthook
    def thread_uncaught(args):
        logger.critical('uncaught_thread_exception', exc_info=(args.exc_type, args.exc_value, args.exc_traceback))
        original_thread(args)
    threading.excepthook = thread_uncaught


def shutdown():
    global _listener, _handler, _cleanup_stop, _cleanup_thread
    if _listener is None:
        return
    if _cleanup_stop is not None:
        _cleanup_stop.set()
        _cleanup_thread.join(timeout=2)
        _cleanup_stop = _cleanup_thread = None
    event('application_stop')
    logger.removeHandler(_handler)
    # Blocking here is intentional only at process exit, never during conversion.
    _listener.queue.put(_listener._sentinel)
    _listener._thread.join()
    for handler in _listener.handlers:
        handler.close()
    _listener = _handler = None


atexit.register(shutdown)
