"""Exercise the interactive Inno wizard on a clean Windows Actions runner."""
import os
import subprocess
import sys
import time
from pathlib import Path

import psutil
from pywinauto import Desktop
from win32com.client import Dispatch


def wait_for(read, timeout=300):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        result = read()
        if result:
            return result
        time.sleep(0.25)
    raise TimeoutError(f"Timed out waiting for {read}")


def installed_processes(folder):
    result = []
    for process in psutil.process_iter(["exe"]):
        exe = process.info["exe"]
        if exe and Path(exe).is_relative_to(folder):
            result.append(process)
    return result


def click_choice(window, enabled):
    lists = [c for c in window.descendants(class_name="TNewCheckListBox") if c.is_visible()]
    assert len(lists) == 1, lists
    if not enabled:
        lists[0].set_focus()
        lists[0].type_keys("{HOME}{SPACE}")


def main(version):
    assert os.name == "nt" and os.environ.get("GITHUB_ACTIONS") == "true"
    setup = Path(f"dist/formix-win-64-v{version}.exe").resolve(strict=True)
    shell = Dispatch("WScript.Shell")
    desktops = [Path(shell.SpecialFolders(k)) for k in ("AllUsersDesktop", "Desktop")]
    menus = [Path(shell.SpecialFolders(k)) for k in ("AllUsersPrograms", "Programs")]
    desktop = Desktop(backend="win32")
    for shortcut, launch in ((True, True), (False, False), (True, False), (False, True)):
        folder = Path(os.environ["RUNNER_TEMP"]).resolve() / f"Formix wizard {int(shortcut)}-{int(launch)}"
        assert not folder.exists()
        log = Path("build/native-update-test-logs").resolve() / (folder.name + ".log")
        log.parent.mkdir(parents=True, exist_ok=True)
        assert not any((p / "Formix.lnk").exists() for p in desktops)
        subprocess.Popen([str(setup), "/SP-", "/LANG=en", "/NORESTART", f"/DIR={folder}", f"/LOG={log}"])
        window = desktop.window(class_name="TWizardForm", title_re=".*Formix.*")
        window.wait("visible", timeout=90)
        tasks_seen = False
        def advance():
            nonlocal tasks_seen
            buttons = {b.window_text().replace("&", ""): b for b in window.descendants(class_name="TNewButton")
                       if b.is_visible() and b.is_enabled()}
            if "Finish" in buttons:
                return buttons["Finish"]
            if "Next" in buttons or "Install" in buttons:
                if any(c.is_visible() for c in window.descendants(class_name="TNewCheckListBox")) and not tasks_seen:
                    click_choice(window, shortcut)
                    tasks_seen = True
                (buttons.get("Next") or buttons["Install"]).click()
            return None
        finish = wait_for(advance, 900)
        assert tasks_seen
        assert not installed_processes(folder)
        click_choice(window, launch)
        finish.click()
        window.wait_not("visible", timeout=60)
        links = [p / "Formix.lnk" for p in desktops if (p / "Formix.lnk").exists()]
        assert bool(links) == shortcut, links
        for link in links:
            assert Path(shell.CreateShortcut(str(link)).TargetPath) == folder / "Formix.exe"
        for menu in menus:
            for link in menu.rglob("*.lnk"):
                target = shell.CreateShortcut(str(link)).TargetPath
                assert not (target and Path(target).is_relative_to(folder)), link
        if launch:
            def visible_app():
                pids = {p.pid for p in installed_processes(folder)}
                return any(w.process_id() in pids for w in desktop.windows(visible_only=True))
            wait_for(visible_app, 120)
        else:
            for _ in range(40):
                assert not installed_processes(folder)
                time.sleep(.25)
        for process in installed_processes(folder):
            try:
                process.kill()
                process.wait(30)
            except psutil.NoSuchProcess:
                pass
        subprocess.run([str(folder / "unins000.exe"), "/VERYSILENT", "/NORESTART"], check=True, timeout=300)
        wait_for(lambda: not (folder / "Formix.exe").exists())
        print(f"PASS desktop={shortcut} run_after_finish={launch}", flush=True)


if __name__ == "__main__":
    main(sys.argv[1])
