"""Apply a verified Formix app update after the GUI process has exited.

This module intentionally uses only the Python standard library so it can run
from the bundled interpreter before or during replacement of the app files.
"""
import argparse
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import subprocess
import sys
import tarfile
import tempfile
import time


MANAGED = ("Formix", "main.py", "formix", "python", "vendor", "release.txt",
           "engine-versions.json", "README.md")


def log_path(platform_name):
    if platform_name == "windows":
        base = Path(os.environ.get("LOCALAPPDATA") or Path.home() / "AppData/Local")
    elif platform_name == "darwin":
        base = Path.home() / "Library/Logs"
    else:
        base = Path(os.environ.get("XDG_STATE_HOME") or Path.home() / ".local/state")
    folder = base / "Formix" / "logs"
    folder.mkdir(parents=True, exist_ok=True)
    return folder / "updater.log"


def log(path, message):
    try:
        # Rotate before the next entry, keeping each message intact even when
        # that entry takes the file slightly over the limit.
        if path.exists() and path.stat().st_size > 5 * 1024 * 1024:
            path.unlink()
        with path.open("a", encoding="utf-8") as stream:
            stream.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} {message}\n")
    except OSError:
        pass


def wait_for_parent(pid, platform_name, log_file):
    if pid <= 0:
        raise ValueError("Invalid parent process id")
    log(log_file, f"Waiting for Formix process {pid} to exit")
    if platform_name == "windows":
        import ctypes
        from ctypes import wintypes
        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel.OpenProcess.argtypes = (wintypes.DWORD, wintypes.BOOL, wintypes.DWORD)
        kernel.OpenProcess.restype = wintypes.HANDLE
        kernel.WaitForSingleObject.argtypes = (wintypes.HANDLE, wintypes.DWORD)
        kernel.WaitForSingleObject.restype = wintypes.DWORD
        kernel.CloseHandle.argtypes = (wintypes.HANDLE,)
        handle = kernel.OpenProcess(0x00100000, False, pid)  # SYNCHRONIZE
        if not handle:
            error = ctypes.get_last_error()
            if error == 87:  # The parent already exited.
                return
            raise OSError(error, "Unable to wait for Formix to exit")
        try:
            result = kernel.WaitForSingleObject(handle, 30 * 60 * 1000)
            if result != 0:
                raise TimeoutError("Timed out waiting for Formix to exit")
        finally:
            kernel.CloseHandle(handle)
        return

    deadline = time.monotonic() + 30 * 60
    while time.monotonic() < deadline:
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return
        except PermissionError:
            pass
        time.sleep(0.25)
    raise TimeoutError("Timed out waiting for Formix to exit")


def safe_extract(archive_path, destination):
    seen = set()
    roots = set()
    with tarfile.open(archive_path, "r:gz") as archive:
        members = archive.getmembers()
        for member in members:
            name = PurePosixPath(member.name)
            if name.is_absolute() or not name.parts or any(part in {"", ".", ".."} for part in name.parts):
                raise ValueError(f"Unsafe path in Linux update archive: {member.name}")
            if len(name.parts) < 2 and not member.isdir():
                raise ValueError("Linux update archive has no application root directory")
            roots.add(name.parts[0])
            if len(roots) > 1 or member.name in seen:
                raise ValueError("Unexpected or duplicate path in Linux update archive")
            seen.add(member.name)
            if not (member.isdir() or member.isfile()):
                raise ValueError(f"Unsupported link or special file in update archive: {member.name}")

        if len(roots) != 1:
            raise ValueError("Linux update archive must contain one app directory")
        for member in members:
            relative = PurePosixPath(member.name)
            output = destination.joinpath(*relative.parts)
            if member.isdir():
                output.mkdir(parents=True, exist_ok=True)
                continue
            output.parent.mkdir(parents=True, exist_ok=True)
            source = archive.extractfile(member)
            if source is None:
                raise ValueError(f"Cannot read update file: {member.name}")
            with source, output.open("xb") as target:
                shutil.copyfileobj(source, target)
            os.chmod(output, member.mode & 0o777)
        app = destination / next(iter(roots))
    required = ("Formix", "main.py", "formix", "python", "vendor", "release.txt")
    if any(not (app / name).exists() for name in required):
        raise ValueError("The downloaded Linux package is missing required application files")
    return app


def apply_linux_update(archive, root, log_file):
    root = root.resolve()
    if not root.is_dir() or not os.access(root, os.W_OK | os.X_OK):
        raise PermissionError(f"The Formix install folder is not writable: {root}")
    work = Path(tempfile.mkdtemp(prefix=".formix-update-", dir=root))
    staged = work / "unpacked"
    backup = work / "backup"
    staged.mkdir()
    backup.mkdir()
    moved_old = []
    moved_new = []
    try:
        new_app = safe_extract(archive, staged)
        log(log_file, f"Validated Linux archive; applying update to {root}")
        try:
            for name in MANAGED:
                old = root / name
                if old.exists() or old.is_symlink():
                    shutil.move(str(old), str(backup / name))
                    moved_old.append(name)
            for name in MANAGED:
                new = new_app / name
                if new.exists() or new.is_symlink():
                    shutil.move(str(new), str(root / name))
                    moved_new.append(name)
        except Exception:
            for name in reversed(moved_new):
                current = root / name
                if current.is_dir() and not current.is_symlink():
                    shutil.rmtree(current)
                else:
                    current.unlink(missing_ok=True)
            for name in reversed(moved_old):
                old = backup / name
                if old.exists() or old.is_symlink():
                    shutil.move(str(old), str(root / name))
            raise
        log(log_file, "Linux app files replaced; user cache, models, logs, and output were preserved")
    finally:
        shutil.rmtree(work, ignore_errors=True)


def run_macos_installer(archive, bundle, log_file):
    script = '''on run argv
set packagePath to POSIX path of (item 1 of argv)
do shell script "/usr/sbin/installer -pkg " & quoted form of packagePath & " -target /" with administrator privileges
end run'''
    result = subprocess.run(["/usr/bin/osascript", "-e", script, str(archive)], check=False)
    if result.returncode:
        raise RuntimeError(f"macOS installer exited with status {result.returncode}")
    log(log_file, f"macOS package installed at {bundle}")


def start_app(platform_name, launcher, bundle, log_file, user_session=None):
    try:
        environment = None
        drop_privileges = None
        if user_session and platform_name == "linux" and os.geteuid() == 0:
            session = json.loads(Path(user_session).read_text(encoding="utf-8"))
            uid, gid = int(session["uid"]), int(session["gid"])
            import pwd
            account = pwd.getpwuid(uid)
            environment = os.environ.copy()
            environment.update({str(key): str(value) for key, value in session.get("env", {}).items()})
            environment.update({"HOME": str(session.get("home") or account.pw_dir),
                                "USER": account.pw_name, "LOGNAME": account.pw_name})

            def drop_privileges():
                os.setgroups(os.getgrouplist(account.pw_name, gid))
                os.setgid(gid)
                os.setuid(uid)

        if platform_name == "darwin":
            subprocess.Popen(["/usr/bin/open", "-a", str(bundle)], close_fds=True)
        elif launcher and Path(launcher).is_file():
            subprocess.Popen([str(launcher)], cwd=str(Path(launcher).parent), close_fds=True,
                             env=environment, preexec_fn=drop_privileges)
        log(log_file, "Started Formix after update")
    except OSError as error:
        log(log_file, f"Could not restart Formix: {error}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--archive", required=True)
    parser.add_argument("--root", required=True)
    parser.add_argument("--platform", required=True, choices=("windows", "darwin", "linux"))
    parser.add_argument("--pid", required=True, type=int)
    parser.add_argument("--interpreter", required=True)
    parser.add_argument("--launcher", default="")
    parser.add_argument("--bundle", default="")
    parser.add_argument("--user-session", default="")
    parser.add_argument("--elevate", action="store_true")
    parser.add_argument("--skip-wait", action="store_true")
    args = parser.parse_args()
    archive = Path(args.archive).resolve()
    root = Path(args.root).resolve()
    log_file = log_path(args.platform)
    log(log_file, f"Updater started for {args.platform}; archive={archive}; install_root={root}")
    try:
        if not archive.is_file():
            raise FileNotFoundError(f"Update package does not exist: {archive}")
        if not args.skip_wait:
            wait_for_parent(args.pid, args.platform, log_file)
        if args.platform == "windows":
            command = [str(archive), "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART",
                       "/SP-", "/CLOSEAPPLICATIONS"]
            completed = subprocess.run(command, check=False)
            log(log_file, f"Windows installer exited with status {completed.returncode}")
            if completed.returncode not in (0, 3010):
                raise RuntimeError(f"Windows installer exited with status {completed.returncode}")
        elif args.platform == "darwin":
            run_macos_installer(archive, args.bundle, log_file)
        elif args.elevate:
            pkexec = shutil.which("pkexec")
            if not pkexec or not args.user_session:
                raise RuntimeError("Administrator authorization is unavailable for this Linux install")
            command = [pkexec, args.interpreter, "-I", str(Path(__file__).resolve()),
                       "--archive", str(archive), "--root", str(root), "--platform", "linux",
                       "--pid", "0", "--interpreter", args.interpreter,
                       "--launcher", args.launcher, "--user-session", args.user_session,
                       "--skip-wait"]
            completed = subprocess.run(command, check=False)
            if completed.returncode:
                raise RuntimeError(f"Linux administrator update exited with status {completed.returncode}")
            return
        else:
            apply_linux_update(archive, root, log_file)
        start_app(args.platform, args.launcher, args.bundle, log_file, args.user_session or None)
    except Exception as error:
        log(log_file, f"Update failed: {type(error).__name__}: {error}")
        start_app(args.platform, args.launcher, args.bundle, log_file, args.user_session or None)
        raise
    finally:
        if args.user_session:
            Path(args.user_session).unlink(missing_ok=True)


if __name__ == "__main__":
    main()
