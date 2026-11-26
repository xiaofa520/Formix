"""Bounded Qt background work with results delivered on the owning GUI thread."""
import shutil
import time
import os
import stat
import sys
import subprocess
from pathlib import Path
from PySide6.QtCore import QObject, QRunnable, QThreadPool, Qt, Signal, Slot

_pending = set()

if __package__:
    from .diagnostics import logger, event
else:
    from diagnostics import logger, event


class _Runner(QRunnable):
    def __init__(self, task):
        super().__init__()
        self.task = task

    def run(self):
        try:
            result, error = self.task.function(), None
        except Exception as exc:
            logger.exception('background_operation_failed')
            result, error = None, exc
        self.task.finished.emit(result, error)


class BackgroundWork(QObject):
    finished = Signal(object, object)

    def __init__(self, function, callback):
        super().__init__()
        self.function = function
        self.callback = callback
        self.finished.connect(self.deliver, Qt.ConnectionType.QueuedConnection)

    @Slot(object, object)
    def deliver(self, result, error):
        try:
            if self.callback:
                self.callback(result, error)
        finally:
            _pending.discard(self)
            self.deleteLater()


def run_background(function, callback=None):
    task = BackgroundWork(function, callback)
    _pending.add(task)
    QThreadPool.globalInstance().start(_Runner(task))
    return task


def remove_tree(path):
    path = Path(path)
    if os.name == "nt":
        absolute = str(path.absolute())
        if not absolute.startswith("\\\\?\\"):
            path = Path("\\\\?\\UNC\\" + absolute[2:] if absolute.startswith("\\\\") else "\\\\?\\" + absolute)

    def writable_retry(function, filename, info):
        error = info[1]
        if not isinstance(error, PermissionError):
            raise error
        os.chmod(filename, stat.S_IREAD | stat.S_IWRITE)
        function(filename)

    for attempt in range(11):
        try:
            if path.is_symlink():
                path.unlink(missing_ok=True)
            else:
                shutil.rmtree(path, onerror=writable_retry)
            return
        except FileNotFoundError:
            if not path.exists():
                return
            raise
        except OSError as error:
            if (not isinstance(error, PermissionError) and getattr(error, "winerror", None) != 145) or attempt == 10:
                raise
            # Office and antivirus processes can briefly retain file handles.
            time.sleep(min(1, .05 * 2**attempt))


def cleanup_path(path, callback=None):
    event('cleanup_requested', path=path)
    return run_background(lambda: remove_tree(path), callback)

_opening_folders = set()


def open_folder_async(path, on_error=None):
    """Open a folder without waiting for the filesystem or desktop on the GUI thread."""
    raw = str(path).strip()
    folder = Path(raw).expanduser().absolute()
    event('folder_open_requested', path=raw)
    if folder in _opening_folders:
        return
    _opening_folders.add(folder)

    def launch():
        if not raw:
            raise ValueError('未指定文件夹路径')
        if not folder.is_dir():
            raise NotADirectoryError(str(folder))
        if sys.platform == "win32":
            # ShellExecute reports dispatch errors; spawning explorer.exe can
            # succeed even when Explorer never opens the requested location.
            os.startfile(str(folder), 'open')
        else:
            launcher = "/usr/bin/open" if sys.platform == "darwin" else "xdg-open"
            subprocess.run([launcher, str(folder)], check=True, timeout=30,
                           stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                           stderr=subprocess.DEVNULL)

    def finished(_, error):
        _opening_folders.discard(folder)
        event('folder_open_failed' if error else 'folder_open_dispatched',
              path=folder, error=str(error) if error else None)
        if error and on_error:
            on_error(folder)

    run_background(launch, finished)

BROWSERS = {
    "chrome": ("Google Chrome", "chrome.exe", "Google/Chrome/Application", "google-chrome"),
    "firefox": ("Firefox", "firefox.exe", "Mozilla Firefox", "firefox"),
    "edge": ("Microsoft Edge", "msedge.exe", "Microsoft/Edge/Application", "microsoft-edge"),
    "chromium": ("Chromium", "chrome.exe", "Chromium/Application", "chromium"),
    "brave": ("Brave Browser", "brave.exe", "BraveSoftware/Brave-Browser/Application", "brave-browser"),
    "safari": ("Safari", "", "", ""),
}


def browser_path(key):
    name, exe, directory, command = BROWSERS[key]
    if sys.platform == "darwin":
        for base in (Path("/Applications"), Path.home() / "Applications", Path("/System/Applications")):
            bundle = base / (name + ".app")
            if bundle.is_dir():
                return str(bundle)
    elif sys.platform == "win32" and exe:
        import winreg
        if key != "chromium":
            for hive in (winreg.HKEY_CURRENT_USER, winreg.HKEY_LOCAL_MACHINE):
                try:
                    with winreg.OpenKey(hive, r"Software\Microsoft\Windows\CurrentVersion\App Paths" + "\\" + exe) as entry:
                        path = Path(winreg.QueryValueEx(entry, None)[0].strip('"'))
                        if path.is_file():
                            return str(path)
                except OSError:
                    pass
        for variable in ("ProgramFiles", "ProgramFiles(x86)", "LOCALAPPDATA"):
            base = os.environ.get(variable)
            if base and (Path(base) / directory / exe).is_file():
                return str(Path(base) / directory / exe)
    elif sys.platform.startswith("linux") and command:
        return shutil.which(command) or shutil.which(command + "-stable")
    return None


def dispatch_web_url(url, browser="system"):
    """Delegate HTTP(S) links to the configured desktop browser."""
    from PySide6.QtCore import QUrl
    from PySide6.QtGui import QDesktopServices
    link = QUrl(url, QUrl.ParsingMode.StrictMode)
    if not link.isValid() or link.scheme() not in {"http", "https"} or not link.host():
        return False
    if browser != "system":
        program = browser_path(browser) if browser in BROWSERS else None
        if not program:
            return False
        if sys.platform == "win32" and browser in {"edge", "chrome"}:
            scheme = "google-chrome:" if browser == "chrome" else "microsoft-edge:"
            url = scheme + url
        else:
            if sys.platform == "darwin":
                command = ["/usr/bin/open", "-a", program, url]
            else:
                command = [program, "-new-tab", url] if browser == "firefox" else [program, url]
            try:
                subprocess.Popen(command, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                                 stderr=subprocess.DEVNULL)
                return True
            except OSError:
                return False
    if sys.platform != "win32":
        return QDesktopServices.openUrl(link)

    # Let the Windows URI broker activate the browser outside Formix's process job.
    # The URL is data in the child environment, never PowerShell source.
    command = (
        "Add-Type -AssemblyName System.Runtime.WindowsRuntime;"
        "$op=[Windows.System.Launcher,Windows.System,ContentType=WindowsRuntime]"
        "::LaunchUriAsync([uri]$env:FORMIX_WEB_URL);"
        "$method=[System.WindowsRuntimeSystemExtensions].GetMethods() | "
        "Where-Object { $_.Name -eq 'AsTask' -and $_.IsGenericMethodDefinition "
        "-and $_.GetGenericArguments().Count -eq 1 -and $_.GetParameters().Count -eq 1 "
        "-and $_.GetParameters()[0].ParameterType.Name -eq 'IAsyncOperation`1' } | "
        "Select-Object -First 1;"
        "$task=$method.MakeGenericMethod([bool]).Invoke($null,@($op));"
        "if (-not $task.GetAwaiter().GetResult()) {exit 1}"
    )
    shell = Path(os.environ["SystemRoot"]) / "System32/WindowsPowerShell/v1.0/powershell.exe"
    try:
        result = subprocess.run([str(shell), "-NoProfile", "-NonInteractive", "-Command",
                                 "$ErrorActionPreference='Stop';" + command],
                                env=dict(os.environ, FORMIX_WEB_URL=url), timeout=15,
                                creationflags=subprocess.CREATE_NO_WINDOW, capture_output=True)
        return result.returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False
