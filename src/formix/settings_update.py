import json
import os
import shutil
import sys
from pathlib import Path
from PySide6.QtCore import QProcess, QSize, Signal, Qt, QUrl
from PySide6.QtGui import QIcon, QDesktopServices
from PySide6.QtWidgets import (QCheckBox, QDialog, QHBoxLayout, QLabel, QProgressBar, QPushButton,
                               QTextBrowser, QVBoxLayout, QWidget)
if __package__:
    from .runtime_paths import ROOT, SYSTEM, script_path, downloaded_engine_present
    from .background_work import open_folder_async
    from .button_input import connect_action
    from .engine_update import bundled_versions, active_engine
else:
    from runtime_paths import ROOT, SYSTEM, script_path, downloaded_engine_present
    from background_work import open_folder_async
    from button_input import connect_action
    from engine_update import bundled_versions, active_engine

PROJECTS = {
    "app": ("Formix", "https://formix.xiaofa520.cn/"),
    "ffmpeg": ("FFmpeg", "https://ffmpeg.org/"),
    "libvips": ("libvips", "https://www.libvips.org/"),
    "libreoffice": ("LibreOffice", "https://www.libreoffice.org/"),
}


def progress_bar():
    bar = QProgressBar()
    bar.setObjectName("taskProgress")
    bar.setTextVisible(False)
    bar.hide()
    return bar


class UpdateDialog(QDialog):
    def __init__(self, row):
        super().__init__(row.window())
        self.setWindowTitle(row.language.t("app_updates" if row.component == "app" else "engine_updates"))
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(12)
        layout.addWidget(QLabel(PROJECTS[row.component][0]))
        self.status = QLabel()
        self.status.setTextFormat(Qt.TextFormat.PlainText)
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        self.notes = None
        self.versions = None
        if row.component == "app":
            layout.addWidget(QLabel(row.language.t("release_notes")))
            self.notes = QTextBrowser()
            self.notes.setObjectName("updateNotes")
            self.notes.setReadOnly(True)
            self.notes.setOpenLinks(False)
            self.notes.anchorClicked.connect(lambda link: row.webLinkRequested.emit(link.toString()))
            self.notes.setAccessibleName(row.language.t("release_notes"))
            self.notes.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
            text = self.palette().color(self.foregroundRole())
            text_color = text.name()
            dark = text.lightness() > 128
            heading_color = "#aacfff" if dark else "#345a7b"
            code_background = "#273444" if dark else "#e8edf5"
            self.notes.document().setDefaultStyleSheet(
                f"body {{ color: {text_color}; }} h1, h2, h3 {{ color: {heading_color}; }}"
                f"code, pre {{ background-color: {code_background}; }}"
                "a { text-decoration: none; }"
            )
            layout.addWidget(self.notes, 1)
            self.resize(490, 360)
        else:
            self.versions = QLabel()
            self.versions.setTextFormat(Qt.TextFormat.PlainText)
            self.versions.setWordWrap(True)
            layout.insertWidget(1, self.versions)
            self.resize(430, 170)
        self.progress = progress_bar()
        layout.addWidget(self.progress)
        if self.notes is None:
            layout.addStretch()
        startup = QCheckBox(row.language.t("update_on_startup"))
        startup.setObjectName("startupCheckBox")
        startup.setCursor(Qt.CursorShape.PointingHandCursor)
        startup.setChecked(row.check_on_startup())
        startup.toggled.connect(lambda checked: row.language.settings.setValue(row.startup_key, checked))
        actions = QHBoxLayout()
        actions.addWidget(startup, 0, Qt.AlignmentFlag.AlignVCenter)
        actions.addStretch()
        later = QPushButton(row.language.t("update_later"))
        self.later = later
        later.setObjectName("secondary")
        later.clicked.connect(self.reject)
        self.now = QPushButton(row.language.t("update_now"))
        self.now.setObjectName("primary")
        # Keep the radius below half of the compact dialog button height.
        self.now.setStyleSheet("QPushButton#primary { border-radius: 10px; }")
        self.now.clicked.connect(self.accept if row.component == "app" else row.start_download)
        for button in (later, self.now):
            button.setMinimumHeight(34)
            actions.addWidget(button)
        layout.addLayout(actions)


class UpdateRow(QWidget):
    webLinkRequested = Signal(str)
    startupFinished = Signal()
    availabilityChanged = Signal(bool)
    installed = Signal()

    def __init__(self,language,component,parent=None):
        super().__init__(parent)
        self.language=language
        self.component = component
        self.startup_key = f"updates/checkOnStartup/{component}"
        self.dialog = None
        self.available = None
        self.startup = False
        layout=QHBoxLayout(self)
        layout.setContentsMargins(0,0,0,0)
        layout.setSpacing(14)
        title, url = PROJECTS[component]
        self.project_link = QPushButton(title)
        self.project_link.setObjectName("projectLink")
        self.project_link.setCursor(Qt.CursorShape.PointingHandCursor)
        connect_action(self.project_link, lambda: self.webLinkRequested.emit(url))
        layout.addWidget(self.project_link)
        self.note=QLabel()
        self.note.setWordWrap(True)
        self.note.setObjectName("muted")
        status_layout = QVBoxLayout()
        status_layout.addWidget(self.note)
        layout.addLayout(status_layout,1)
        self.button=QPushButton()
        self.button.setObjectName("secondary")
        self.button.setProperty("glyph", "refresh-cw.svg")
        self.button.setIcon(QIcon(str(Path(__file__).with_name("assets")/"icons"/"refresh-cw.svg")))
        self.button.setIconSize(QSize(16,16))
        self.button.setMinimumHeight(40)
        layout.addWidget(self.button)
        connect_action(self.button, self.check)
        self.remove_button = QPushButton()
        self.remove_button.setObjectName("secondary")
        self.remove_button.setProperty("glyph", "trash-2.svg")
        self.remove_button.setMinimumHeight(40)
        self.remove_button.setVisible(component != "app")
        layout.addWidget(self.remove_button)
        connect_action(self.remove_button, self.remove_engine)
        self.removing = False
        self.process=QProcess(self)
        self.process.readyReadStandardError.connect(self.read_messages)
        self.process.finished.connect(self.finished)
        self.process.errorOccurred.connect(self.failed_start)
        self.downloading=False
        self.note_state=None
        self.retranslate()
        active = active_engine(component) if component != "app" else None
        if active:
            self.set_note("installed_version", version=active[0])
        elif local := bundled_versions().get(component):
            self.set_note("bundled_engine_version", version=local)
        elif component != "app":
            self.set_note("engine_not_downloaded")

    def set_note(self,key,**values):
        self.note_state=(key,values)
        self.note.setText(self.language.t(key,**values))
        if self.dialog:
            self.dialog.status.setText(self.note.text())

    def retranslate(self,*_):
        if __package__:
            from .runtime_paths import optional_engine_missing
        else:
            from runtime_paths import optional_engine_missing
        self.button.setText(self.language.t("runtime_download" if optional_engine_missing(self.component) else "check_engine"))
        self.remove_button.setText(self.language.t("remove_engine"))
        self.remove_button.setEnabled(downloaded_engine_present(self.component)
                                      and self.process.state() == QProcess.ProcessState.NotRunning)
        self.project_link.setToolTip(self.language.t("visit_project_website", name=self.project_link.text()))
        if self.note_state:
            key,values=self.note_state
            self.note.setText(self.language.t(key,**values))

    def remove_engine(self):
        tasks = getattr(self.window(), "tasks", None)
        if (self.dialog or self.process.state() != QProcess.ProcessState.NotRunning
                or getattr(self.window(), "task_busy", False)
                or (tasks and self.component in tasks.checking_engines)):
            self.set_note("engine_busy")
            return
        if not downloaded_engine_present(self.component):
            return
        self.removing = True
        if tasks:
            tasks.checking_engines.add(self.component)
        self.run(["remove", self.component])

    def finish_removal(self):
        self.removing = False
        tasks = getattr(self.window(), "tasks", None)
        if tasks:
            tasks.checking_engines.discard(self.component)
            tasks.next_job()
        self.retranslate()

    def failed_start(self, error):
        if error == QProcess.ProcessError.FailedToStart:
            self.note_state=None
            self.note.setText(self.process.errorString())
            self.button.setEnabled(True)
            if self.removing:
                self.finish_removal()
            if self.downloading and self.component != "app":
                self.install_failed(self.process.errorString())
            self.check_failed()

    def run(self,args):
        self.button.setEnabled(False)
        self.remove_button.setEnabled(False)
        self.stderr_tail = b""
        self.error_text = ""
        script=script_path("engine_update.py")
        self.process.start(sys.executable,["-X","utf8",script,*args])

    def read_messages(self, final=False):
        data = self.stderr_tail + bytes(self.process.readAllStandardError())
        lines = data.split(b"\n")
        self.stderr_tail = b"" if final else lines.pop()
        for raw in lines:
            line = raw.decode("utf8", "replace").strip()
            if line.startswith("FORMIX_UPDATE ") and self.downloading:
                phase, percent = json.loads(line[14:])
                self.show_progress(phase, percent)
            elif line:
                self.error_text = (self.error_text + "\n" + line)[-600:].strip()

    def show_progress(self, phase, percent=None):
        if self.dialog:
            bar = self.dialog.progress
            bar.setRange(0, 100 if percent is not None else 0)
            if percent is not None:
                bar.setValue(percent)
            bar.show()
            if phase == "download":
                self.dialog.status.setText(self.language.t("engine_percent", percent=percent))
        if phase != "download":
            self.set_note("engine_" + phase)

    def end_progress(self):
        if self.dialog:
            self.dialog.progress.hide()
        self.downloading = False

    def install_failed(self, reason):
        self.end_progress()
        self.set_note("engine_kept", reason=reason)

    def check_on_startup(self):
        return self.language.settings.value(self.startup_key, self.component == "app", type=bool)

    def check(self, startup=False):
        if self.process.state() != QProcess.ProcessState.NotRunning or self.dialog:
            if startup:
                self.startupFinished.emit()
            return
        self.startup = startup
        self.available = None
        self.downloading=False
        self.note.setToolTip("")
        self.set_note("checking_version")
        self.run(["app-check"] if self.component == "app" else ["check", self.component])

    def finished(self,code,*_):
        if getattr(self.window(), "closing", False):
            return
        self.button.setEnabled(True)
        self.read_messages(final=True)
        if self.removing:
            self.finish_removal()
            if code:
                self.set_note("runtime_failed", reason=self.error_text)
            elif local := bundled_versions().get(self.component):
                self.set_note("bundled_engine_version", version=local)
            else:
                self.set_note("engine_not_downloaded")
            return
        self.retranslate()
        if code:
            self.note_state=None
            error=self.error_text
            if error in {"发行版本已变更，请重新检查更新","The release changed. Check for updates again."}:
                self.set_note("update_changed")
            elif error=="安装包完整性检查失败":
                self.set_note("update_bad_hash")
            else:
                self.note.setText(error or self.language.t("update_changed"))
            if self.downloading and self.component != "app":
                self.install_failed(self.note.text())
            self.check_failed()
            return
        data=json.loads(bytes(self.process.readAllStandardOutput()))
        if self.downloading:
            if self.component == "app":
                path = Path(data)
                self.launch_app_update(path)
            else:
                self.end_progress()
                self.set_note("installed_version", version=data["version"])
                self.installed.emit()
                self.retranslate()
                if self.dialog:
                    self.dialog.versions.hide()
            if not self.dialog:
                self.finish_startup()
        elif self.component != "app":
            if not data["available"]:
                self.set_note("component_current", local=data["local"])
            else:
                self.set_note("engine_update_available", version=data["version"])
                self.available = data
            self.present_result()
        else:
            self.language.settings.setValue("updates/releaseNotes", [data["tag"], data["notes"].strip()])
            update = data.get("update")
            if data.get("unavailable"):
                self.set_note("app_package_unavailable")
                self.availabilityChanged.emit(False)
            elif update is None:
                self.set_note("app_current")
                self.availabilityChanged.emit(False)
            else:
                self.set_note("engine_update_available",version=update["version"])
                self.available = update
                self.availabilityChanged.emit(True)
            self.present_result()

    def launch_app_update(self, archive):
        """Hand a verified release to a detached, platform-specific installer."""
        if SYSTEM == 'Windows' and (ROOT / 'release.txt').is_file():
            try:
                from formix.app_updater import prepare_windows_update
                script = prepare_windows_update(archive, ROOT, os.getpid())
                powershell = str(Path(os.environ['SystemRoot']) / 'System32/WindowsPowerShell/v1.0/powershell.exe')
                started = QProcess.startDetached(powershell, ['-NoProfile', '-NonInteractive', '-WindowStyle', 'Hidden', '-ExecutionPolicy', 'Bypass', '-File', str(script)], str(script.parent))
                if isinstance(started, tuple):
                    started = started[0]
                if not started:
                    raise RuntimeError('Cannot start installer helper')
            except (OSError, RuntimeError, KeyError) as error:
                self.set_note('app_update_launch_failed')
                self.note.setToolTip(str(error))
                return False
            self.set_note('app_update_installing')
            self.window().close()
            return True
        if SYSTEM == 'Linux' and archive.suffix.lower() in {'.deb', '.appimage'}:
            try:
                if __package__:
                    from .app_updater import prepare_linux_package_update
                else:
                    from app_updater import prepare_linux_package_update
                script = prepare_linux_package_update(archive, ROOT, os.getpid(), os.environ.get('APPIMAGE'))
                started = QProcess.startDetached('/bin/sh', [str(script)], str(script.parent))
                if isinstance(started, tuple):
                    started = started[0]
                if not started:
                    raise RuntimeError('Could not start package updater')
            except (OSError, RuntimeError, ValueError) as error:
                self.end_progress()
                self.set_note('app_update_launch_failed')
                self.note.setToolTip(str(error))
                return False
            self.set_note('app_update_installing')
            self.window().close()
            return True
        if not (ROOT / "release.txt").is_file():
            self.set_note("app_update_packaged_only")
            self.note.setToolTip(str(archive))
            open_folder_async(archive.parent)
            return False
        helper = script_path("app_updater.py")
        args = ["-I", helper, "--archive", str(archive), "--root", str(ROOT),
                "--platform", SYSTEM.lower(), "--pid", str(os.getpid())]
        if SYSTEM == "Windows":
            runtime = ROOT / "runtime"
            interpreter = runtime / "格式转换通.exe"
            if not interpreter.is_file():
                interpreter = runtime / "Formix.exe"
            launcher = ROOT / "Formix.exe"
            if not interpreter.is_file() or not launcher.is_file():
                self.set_note("app_update_launch_failed")
                return False
            args.extend(["--interpreter", str(interpreter), "--launcher", str(launcher)])
            program = str(interpreter)
        else:
            program = sys.executable
            args.extend(["--interpreter", program])
            if SYSTEM == "Darwin":
                args.extend(["--bundle", "/Applications/Formix.app"])
            else:
                args.extend(["--launcher", str(ROOT / "Formix")])
                if not os.access(ROOT, os.W_OK | os.X_OK):
                    pkexec = shutil.which("pkexec")
                    if not pkexec:
                        self.set_note("app_update_linux_permissions")
                        return False
                    env_file = archive.with_name(".formix-update-session.json")
                    session = {key: os.environ[key] for key in (
                        "DISPLAY", "WAYLAND_DISPLAY", "XDG_RUNTIME_DIR", "DBUS_SESSION_BUS_ADDRESS",
                        "XAUTHORITY", "LANG", "LC_ALL", "XDG_CURRENT_DESKTOP", "PATH") if key in os.environ}
                    env_file.write_text(json.dumps({"uid": os.getuid(), "gid": os.getgid(),
                                                    "home": str(Path.home()), "env": session}),
                                        encoding="utf-8")
                    env_file.chmod(0o600)
                    args.extend(["--user-session", str(env_file), "--elevate"])
        try:
            started = QProcess.startDetached(program, args, str(ROOT))
        except (OSError, RuntimeError, TypeError):
            started = False
        if isinstance(started, tuple):
            started = started[0]
        if not started:
            if SYSTEM == "Linux" and "env_file" in locals():
                try:
                    env_file.unlink(missing_ok=True)
                except OSError:
                    pass
            self.set_note("app_update_launch_failed")
            return False
        self.set_note("app_update_installing")
        self.note.setToolTip(str(archive))
        self.window().close()
        return True

    def present_result(self):
        if not self.available:
            self.finish_startup()
            return
        self.dialog = UpdateDialog(self)
        size = f"{self.available['size'] / 1024**2:.1f} MiB"
        if self.dialog.versions is not None:
            local = self.available.get("local") or self.language.t("update_unknown")
            self.dialog.versions.setText(self.language.t("update_versions", local=local, version=self.available["version"]))
            self.dialog.status.setText(size)
        else:
            self.dialog.status.setText(f"{self.note.text()}  ·  {size}")
            self.refresh_dialog_notes("release_notes_empty")
        self.dialog.finished.connect(self.dialog_closed)
        self.dialog.open()

    def refresh_dialog_notes(self, fallback):
        if self.dialog and self.dialog.notes:
            cached = self.language.settings.value("updates/releaseNotes")
            if isinstance(cached, list) and len(cached) == 2:
                tag, body = cached
                text = f"{tag}\n\n{body or self.language.t('release_notes_empty')}"
            else:
                text = self.language.t(fallback)
            self.dialog.notes.setMarkdown(text)

    def check_failed(self):
        if self.dialog:
            self.dialog.status.setText(self.note.text())
            self.refresh_dialog_notes("release_notes_unavailable")
        self.finish_startup()

    def dialog_closed(self, result):
        self.dialog = None
        if result == QDialog.DialogCode.Accepted and self.available:
            self.start_download()
        elif not self.downloading:
            self.finish_startup()

    def start_download(self):
        if not self.available or self.downloading:
            return
        self.downloading = True
        self.download_version = self.available["version"]
        self.available = None
        if self.dialog:
            self.dialog.now.hide()
            self.dialog.later.setText(self.language.t("close_dialog"))
        if self.component == "app":
            self.set_note("engine_download_status")
            args = ["app-download"]
        else:
            self.show_progress("download", 0)
            args = ["download", self.component]
        self.run([*args, self.download_version])

    def finish_startup(self):
        if self.startup:
            self.startup = False
            self.startupFinished.emit()
