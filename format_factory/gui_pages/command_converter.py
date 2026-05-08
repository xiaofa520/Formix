import os
import platform
import re
import shlex

from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QColor, QFont, QKeySequence, QTextCharFormat, QTextCursor
from PyQt6.QtWidgets import QTextEdit, QVBoxLayout, QWidget, QProgressBar

from ..i18n import resolve_language, tr


TXT_INVALID = "Please enter an FFmpeg/FFplay/FFprobe command."
TXT_ONLY_FFMPEG = "Only ffmpeg/ffplay/ffprobe commands are allowed."
TXT_BAD_PARSE = "Failed to parse command."
TXT_BLOCKED = "Shell control characters are blocked. Use a single ffmpeg/ffplay/ffprobe command."
TXT_MISSING_FFMPEG = "FFmpeg not found. Please download it from Settings."
TXT_MISSING_FFPROBE = "FFprobe not found. Please download it from Settings."
TXT_MISSING_FFPLAY = "FFplay not found. Please download it from Settings."
TXT_CANCELLED = "Cancelled."
TXT_READY = (
    "Formix 命令台\n"
    "仅支持 ffmpeg / ffplay / ffprobe 命令。\n"
    "回车执行，Ctrl+C 中断运行。\n"
    "Ctrl+Enter 换行。\n"
)
BLOCKED_CHARS = {"|", "&", ";", ">", "<", "`"}
_NO_VALUE_OPTIONS = {
    "-y", "-n", "-an", "-vn", "-sn", "-dn",
    "-shortest", "-nostdin", "-hide_banner",
    "-stats", "-nostats", "-re", "-copyts",
    "-ignore_unknown", "-benchmark", "-benchmark_all",
}

COMMAND_DESCRIPTIONS = {
    "ffmpeg": "Start FFmpeg. You can type any FFmpeg option supported by your build.",
    "ffplay": "Start FFplay. Use it to preview media playback directly.",
    "ffprobe": "Start FFprobe. Use it to inspect media metadata or stream details.",
    "-h": "Show FFmpeg help.",
    "-help": "Show help.",
    "-version": "Show FFmpeg version information.",
    "-hide_banner": "Hide the version banner.",
    "-loglevel": "Set logging detail level.",
    "-stats": "Show live progress stats.",
    "-progress": "Write progress information to a target.",
    "-show_format": "Show container format details.",
    "-show_streams": "Show stream details.",
    "-show_packets": "Show packet details.",
    "-show_frames": "Show frame details.",
    "-show_entries": "Choose which fields to print.",
    "-print_format": "Set the output print format.",
    "-of": "Alias for -print_format.",
    "-select_streams": "Select specific streams.",
    "-count_frames": "Count decoded frames.",
    "-count_packets": "Count packets.",
    "-i": "Set the input file or input stream.",
    "-c:v": "Set the video codec, such as libx264, libx265, or copy.",
    "-c:a": "Set the audio codec, such as aac, libmp3lame, or copy.",
    "-b:v": "Set the video bitrate, for example 2500k.",
    "-b:a": "Set the audio bitrate, for example 192k.",
    "-crf": "Common video quality control value. Lower usually means higher quality.",
    "-preset": "Balance encoding speed and compression ratio.",
    "-vf": "Set a video filter, for example scale or fps.",
    "-ss": "Seek to a start time.",
    "-to": "Stop at a target time.",
    "-t": "Limit the output duration.",
    "-r": "Set the output frame rate.",
    "-an": "Remove audio streams.",
    "-vn": "Remove video streams.",
    "-sn": "Remove subtitle streams.",
    "-dn": "Remove data streams.",
    "-map": "Manually select which streams to use.",
    "-map_metadata": "Copy or choose metadata mapping.",
    "-map_chapters": "Copy or choose chapter mapping.",
    "-metadata": "Write output metadata.",
    "-y": "Overwrite the output file if it already exists.",
    "-f": "Force the container or output format.",
    "-shortest": "Stop when the shortest stream ends.",
    "-movflags": "Set MOV or MP4 container flags.",
    "-pix_fmt": "Set the pixel format.",
    "-q:v": "Set video quality.",
    "-q:a": "Set audio quality.",
    "-ar": "Set the audio sample rate.",
    "-ac": "Set the number of audio channels.",
    "-af": "Set an audio filter.",
    "-filter_complex": "Set a complex filter graph.",
    "copy": "Copy the stream without re-encoding.",
    "libx264": "H.264 video codec with strong compatibility.",
    "libx265": "H.265 video codec with better compression and slower encoding.",
    "h264_nvenc": "NVIDIA GPU H.264 encoder.",
    "aac": "AAC audio codec, common in MP4 files.",
    "libmp3lame": "MP3 audio codec.",
    "flac": "FLAC lossless audio codec.",
    "scale=1920:1080": "Scale the video to 1920x1080.",
    "fps=30": "Set the output frame rate to 30 fps.",
    "slow": "Slower encoding with better compression.",
    "medium": "Default speed and compression balance.",
    "fast": "Faster encoding, often with larger output.",
}

OPTION_COMPLETIONS = [
    "ffmpeg",
    "ffplay",
    "ffprobe",
    "-h",
    "-help",
    "-version",
    "-hide_banner",
    "-loglevel",
    "-stats",
    "-progress",
    "-i",
    "-show_format",
    "-show_streams",
    "-show_packets",
    "-show_frames",
    "-show_entries",
    "-print_format",
    "-of",
    "-select_streams",
    "-count_frames",
    "-count_packets",
    "-c:v",
    "-c:a",
    "-b:v",
    "-b:a",
    "-crf",
    "-preset",
    "-vf",
    "-ss",
    "-to",
    "-t",
    "-r",
    "-an",
    "-vn",
    "-sn",
    "-dn",
    "-map",
    "-map_metadata",
    "-map_chapters",
    "-metadata",
    "-f",
    "-y",
    "-shortest",
    "-movflags",
    "-pix_fmt",
    "-q:v",
    "-q:a",
    "-ar",
    "-ac",
    "-af",
    "-filter_complex",
]

VALUE_COMPLETIONS = {
    "-c:v": ["copy", "libx264", "libx265", "h264_nvenc"],
    "-c:a": ["copy", "aac", "libmp3lame", "flac"],
    "-preset": ["ultrafast", "fast", "medium", "slow", "veryslow"],
    "-vf": ["scale=1920:1080", "fps=30"],
    "-af": ["loudnorm", "volume=1.5", "aresample=48000"],
    "-filter_complex": ["[0:v]scale=1280:-2[v]", "[0:a]aresample=48000[a]"],
    "-movflags": ["+faststart", "+frag_keyframe+empty_moov"],
    "-f": ["mp4", "mp3", "wav", "flac", "image2", "hls"],
    "-loglevel": ["quiet", "panic", "fatal", "error", "warning", "info", "verbose", "debug"],
    "-pix_fmt": ["yuv420p", "yuv444p", "nv12"],
    "-metadata": ["title=\"My Video\"", "artist=\"Formix\""],
    "-print_format": ["json", "ini", "xml", "flat"],
    "-of": ["json", "ini", "xml", "flat"],
    "-select_streams": ["v", "a", "s", "d", "v:0", "a:0"],
    "-show_entries": ["stream=index,codec_name,codec_type", "format=duration,size,bit_rate"],
}

FORMAT_OUTPUT_EXTENSIONS = {
    "mp4": ".mp4",
    "mp3": ".mp3",
    "wav": ".wav",
    "flac": ".flac",
    "hls": ".m3u8",
}

TEMPLATE_COMPLETIONS = [
    'ffmpeg -i "D:/input/video.mp4" "D:/output/video.mp4"',
    'ffmpeg -i "D:/input/video.mp4" -c:v libx264 -crf 23 "D:/output/video_h264.mp4"',
    'ffmpeg -i "D:/input/video.mp4" -vn -c:a libmp3lame "D:/output/audio.mp3"',
    'ffmpeg -i "D:/input/video.mp4" -ss 00:00:10 -t 00:00:20 "D:/output/clip.mp4"',
]

TERMINAL_SKINS = {
    "Windows": {
        "title": "Formix 命令台",
        "badge": "FFmpeg",
        "prompt": "formix ❯ ",
        "font": "Cascadia Mono",
        "bg": "rgba(10,16,28,0.30)",
        "text_dark": "#FFE3B0",
        "text_light": "#2B2926",
        "muted_dark": "#E0BFA1",
        "muted_light": "#5C544A",
        "accent_dark": "#FBBF24",
        "accent_light": "#4B5563",
        "green": "#34D399",
        "red": "#F87171",
        "selection": "rgba(96,165,250,0.35)",
    },
    "Darwin": {
        "title": "Formix 命令台",
        "badge": "FFmpeg",
        "prompt": "formix ❯ ",
        "font": "Menlo",
        "bg": "rgba(18,18,18,0.30)",
        "text_dark": "#FFE7C2",
        "text_light": "#2B2926",
        "muted_dark": "#E7C9AA",
        "muted_light": "#5C544A",
        "accent_dark": "#FDBA74",
        "accent_light": "#4B5563",
        "green": "#4ADE80",
        "red": "#FB7185",
        "selection": "rgba(167,139,250,0.28)",
    },
    "Linux": {
        "title": "Formix 命令台",
        "badge": "FFmpeg",
        "prompt": "formix ❯ ",
        "font": "DejaVu Sans Mono",
        "bg": "rgba(17,24,39,0.30)",
        "text_dark": "#FFE4B5",
        "text_light": "#2B2926",
        "muted_dark": "#E0C8AA",
        "muted_light": "#5C544A",
        "accent_dark": "#FDE047",
        "accent_light": "#4B5563",
        "green": "#4ADE80",
        "red": "#F87171",
        "selection": "rgba(34,197,94,0.24)",
    },
}


class TerminalEdit(QTextEdit):
    enter_pressed = pyqtSignal()
    interrupt_pressed = pyqtSignal()
    history_prev_requested = pyqtSignal()
    history_next_requested = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._prompt_pos_getter = None
        self._running_getter = None
        self._mouse_dragging = False

    def set_prompt_pos_getter(self, getter):
        self._prompt_pos_getter = getter

    def set_running_getter(self, getter):
        self._running_getter = getter

    def _prompt_pos(self) -> int:
        return self._prompt_pos_getter() if self._prompt_pos_getter else 0

    def _force_cursor_into_input(self):
        prompt_pos = self._prompt_pos()
        cursor = self.textCursor()
        if cursor.selectionStart() < prompt_pos or cursor.position() < prompt_pos:
            cursor.clearSelection()
            cursor.setPosition(max(prompt_pos, len(self.toPlainText())))
            self.setTextCursor(cursor)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_C and event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            if self._running_getter and self._running_getter():
                self.interrupt_pressed.emit()
                return
        if event.key() == Qt.Key.Key_Up and not (event.modifiers() & (Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.AltModifier | Qt.KeyboardModifier.MetaModifier | Qt.KeyboardModifier.ShiftModifier)):
            if self._running_getter and self._running_getter():
                return
            self.history_prev_requested.emit()
            return
        if event.key() == Qt.Key.Key_Down and not (event.modifiers() & (Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.AltModifier | Qt.KeyboardModifier.MetaModifier | Qt.KeyboardModifier.ShiftModifier)):
            if self._running_getter and self._running_getter():
                return
            self.history_next_requested.emit()
            return
        if event.matches(QKeySequence.StandardKey.Copy):
            super().keyPressEvent(event)
            return
        if event.matches(QKeySequence.StandardKey.SelectAll):
            super().keyPressEvent(event)
            return
        if event.matches(QKeySequence.StandardKey.Paste):
            self._force_cursor_into_input()
            super().keyPressEvent(event)
            return
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
                self._force_cursor_into_input()
                super().keyPressEvent(event)
                return
            self.enter_pressed.emit()
            return
        prompt_pos = self._prompt_pos()
        cursor = self.textCursor()
        if event.key() == Qt.Key.Key_Home:
            cursor.clearSelection()
            cursor.setPosition(prompt_pos)
            self.setTextCursor(cursor)
            return
        if event.key() == Qt.Key.Key_Backspace:
            if cursor.selectionStart() < prompt_pos or cursor.position() <= prompt_pos:
                return
        if event.key() == Qt.Key.Key_Delete:
            if cursor.selectionStart() < prompt_pos or cursor.position() < prompt_pos:
                return
        if event.key() == Qt.Key.Key_Left and not cursor.hasSelection() and cursor.position() <= prompt_pos:
            return
        if event.text():
            self._force_cursor_into_input()
        super().keyPressEvent(event)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.setFocus(Qt.FocusReason.MouseFocusReason)
            self._mouse_dragging = False
        super().mousePressEvent(event)
        if event.button() == Qt.MouseButton.LeftButton and not self._mouse_dragging:
            if not (event.modifiers() & Qt.KeyboardModifier.ShiftModifier):
                cursor = self.cursorForPosition(event.position().toPoint())
                cursor.clearSelection()
                self.setTextCursor(cursor)

    def mouseMoveEvent(self, event):
        if event.buttons() & Qt.MouseButton.LeftButton:
            self._mouse_dragging = True
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        super().mouseReleaseEvent(event)
        if event.button() == Qt.MouseButton.LeftButton:
            self.setFocus(Qt.FocusReason.MouseFocusReason)
            self._mouse_dragging = False


class CommandConverterPage(QWidget):
    conversion_requested = pyqtSignal(int, str, list, str)
    cancel_conversion_signal = pyqtSignal()

    def __init__(self, ffmpeg_handler=None, parent=None):
        super().__init__(parent)
        self.ffmpeg_handler = ffmpeg_handler
        self._language = "auto"
        self.input_files = []
        self.output_dir = ""
        self.output_format_combo = None
        self._is_dark = False
        self._bg_colors = {}
        self._output_path = ""
        self._active = False
        self._current_tool = "ffmpeg"
        self._platform = platform.system()
        self._skin = TERMINAL_SKINS.get(self._platform, TERMINAL_SKINS["Linux"])
        self._prompt_prefix = f"{self._skin['title']}  -  {self._skin['badge']}\n{self._skin['prompt']}"
        self._prompt_pos = 0
        self._terminal_history = []
        self._record_history = True
        self._pending_command = ""
        self._command_history = []
        self._history_index = None
        self._history_draft = ""
        self._theme_text_color = "#151514"
        self._theme_muted_color = "#4A4A49"
        self._theme_accent_color = "#2563EB"
        self._theme_info_color = "#1D4ED8"
        self._theme_warn_color = "#B45309"
        self._theme_error_color = "#B91C1C"
        self._theme_success_color = "#15803D"
        self._theme_cmd_color = "#0F766E"
        self._theme_meta_color = "#6D28D9"
        self._theme_banner_color = "#111827"
        self._init_ui()
        self._connect_handler_signals()
        self._apply_terminal_style()
        self._reset_terminal()

    def _init_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        self.terminal = TerminalEdit()
        self.terminal.setObjectName("full_terminal")
        self.terminal.setFrameShape(QTextEdit.Shape.NoFrame)
        self.terminal.setLineWrapMode(QTextEdit.LineWrapMode.WidgetWidth)
        self.terminal.setTabChangesFocus(False)
        self.terminal.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.terminal.setTextInteractionFlags(Qt.TextInteractionFlag.TextEditorInteraction)
        mono = QFont(self._skin["font"], 11)
        mono.setStyleHint(QFont.StyleHint.Monospace)
        self.terminal.setFont(mono)
        self.terminal.setAcceptRichText(False)
        self.terminal.set_prompt_pos_getter(lambda: self._prompt_pos)
        self.terminal.set_running_getter(lambda: self._active)
        self.terminal.enter_pressed.connect(self._on_enter_pressed)
        self.terminal.interrupt_pressed.connect(self._on_interrupt_pressed)
        self.terminal.history_prev_requested.connect(self._on_history_prev_requested)
        self.terminal.history_next_requested.connect(self._on_history_next_requested)

        root.addWidget(self.terminal)

        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setTextVisible(True)
        self.progress_bar.setFormat("0%")
        self.progress_bar.setFixedHeight(10)
        self.progress_bar.hide()
        root.addWidget(self.progress_bar)

        self.setFocusProxy(self.terminal)

        self.start_conversion_button = self.terminal
        self.cancel_conversion_button = self.terminal
        self.overall_progress_bar = None
        QTimer.singleShot(0, self.focus_terminal)

    def _command_ready_lines(self):
        lang = resolve_language(self._language)
        if lang == "zh_TW":
            return ["Formix 命令列", "僅支援 ffmpeg / ffplay / ffprobe 命令。", "按 Enter 執行，Ctrl+C 中斷執行。", "Ctrl+Enter 換行。"]
        if lang == "en":
            return ["Formix Command", "Only ffmpeg / ffplay / ffprobe commands are supported.", "Press Enter to run, Ctrl+C to stop.", "Ctrl+Enter for a new line."]
        if lang == "ja":
            return ["Formix コマンド", "ffmpeg / ffplay / ffprobe コマンドのみ使用できます。", "Enter で実行、Ctrl+C で停止。", "Ctrl+Enter で改行。"]
        if lang == "ko":
            return ["Formix 명령", "ffmpeg / ffplay / ffprobe 명령만 사용할 수 있습니다.", "Enter로 실행, Ctrl+C로 중단.", "Ctrl+Enter로 줄바꿈."]
        return ["Formix 命令行", "仅支持 ffmpeg / ffplay / ffprobe 命令。", "回车执行，Ctrl+C 中断运行。", "Ctrl+Enter 换行。"]

    def _make_format(self, color: str, bold: bool = False):
        fmt = QTextCharFormat()
        fmt.setForeground(QColor(color))
        if bold:
            fmt.setFontWeight(QFont.Weight.Bold)
        return fmt

    def _kind_format(self, kind: str):
        return {
            "text": self._make_format(self._theme_text_color),
            "prompt": self._make_format(self._theme_accent_color, bold=True),
            "banner": self._make_format(self._theme_banner_color, bold=True),
            "info": self._make_format(self._theme_info_color),
            "warn": self._make_format(self._theme_warn_color),
            "warning": self._make_format(self._theme_warn_color),
            "error": self._make_format(self._theme_error_color, bold=True),
            "success": self._make_format(self._theme_success_color),
            "cmd": self._make_format(self._theme_cmd_color, bold=True),
            "meta": self._make_format(self._theme_meta_color),
            "encoder": self._make_format(self._theme_meta_color, bold=True),
            "progress": self._make_format(self._theme_info_color),
        }.get(kind, self._make_format(self._theme_text_color))

    def _apply_terminal_style(self):
        skin = self._skin
        if self._is_dark:
            text = "#F7D9B3"
            muted = "#E5C7A7"
            accent = "#FBBF24"
            terminal_bg = "rgba(12,10,8,0.20)"
            selection_bg = "rgba(251,191,36,0.24)"
            self._theme_text_color = text
            self._theme_muted_color = muted
            self._theme_accent_color = accent
            self._theme_info_color = "#FDBA74"
            self._theme_warn_color = "#FCD34D"
            self._theme_error_color = "#FB7185"
            self._theme_success_color = "#86EFAC"
            self._theme_cmd_color = "#F9A8D4"
            self._theme_meta_color = "#C4B5FD"
            self._theme_banner_color = "#FFE08A"
        else:
            text = "#111111"
            muted = "#2F2A24"
            accent = "#1F2937"
            terminal_bg = "rgba(255,255,255,0.30)"
            selection_bg = "rgba(31,41,55,0.18)"
            self._theme_text_color = text
            self._theme_muted_color = muted
            self._theme_accent_color = accent
            self._theme_info_color = "#111827"
            self._theme_warn_color = "#7C2D12"
            self._theme_error_color = "#7F1D1D"
            self._theme_success_color = "#14532D"
            self._theme_cmd_color = "#111827"
            self._theme_meta_color = "#374151"
            self._theme_banner_color = "#0F172A"
        self.setStyleSheet(
            f"""
QWidget {{
    background: transparent;
}}
QTextEdit#full_terminal {{
    background: {terminal_bg};
    color: {text};
    border: none;
    padding: 18px 22px;
    selection-background-color: {selection_bg};
    selection-color: {text};
    font-family: "{skin['font']}","Consolas","JetBrains Mono","SF Mono","Menlo",monospace;
}}
QProgressBar {{
    background: rgba(148,163,184,0.12);
    border: none;
    border-radius: 0;
    color: {text};
}}
QProgressBar::chunk {{
    background: {accent};
}}
QScrollBar:vertical {{
    background: transparent;
    width: 10px;
    margin: 4px 2px 4px 0;
}}
QScrollBar::handle:vertical {{
    background: rgba(148,163,184,0.25);
    border-radius: 5px;
    min-height: 24px;
}}
QScrollBar::handle:vertical:hover {{
    background: rgba(148,163,184,0.45);
}}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
    height: 0;
}}
"""
        )
        pal = self.terminal.palette()
        pal.setColor(self.terminal.viewport().backgroundRole(), QColor(0, 0, 0, 0))
        pal.setColor(self.terminal.foregroundRole(), QColor(text))
        self.terminal.setPalette(pal)

    def _connect_handler_signals(self):
        if not self.ffmpeg_handler:
            return
        try:
            self.ffmpeg_handler.conversion_started.connect(self._on_started)
        except Exception:
            pass
        try:
            self.ffmpeg_handler.progress_update.connect(self._on_progress)
        except Exception:
            pass
        try:
            self.ffmpeg_handler.conversion_finished.connect(self._on_finished)
        except Exception:
            pass
        try:
            self.ffmpeg_handler.log_line.connect(self._on_log_line)
        except Exception:
            pass

    def attach_ffmpeg_handler(self, handler):
        self.ffmpeg_handler = handler
        self._connect_handler_signals()

    def set_language(self, language: str):
        self._language = resolve_language(language or "auto")
        self._skin = TERMINAL_SKINS.get(self._platform, TERMINAL_SKINS["Linux"])
        label = tr(self._language, "tab_command")
        self._prompt_prefix = f"{label}  -  FFmpeg\nformix > "
        self._reset_terminal()

    def set_theme(self, mode: str, bg_colors: dict = None):
        self._is_dark = mode == "dark"
        self._bg_colors = bg_colors or {}
        self._apply_terminal_style()
        self._rebuild_terminal_view()

    def _reset_terminal(self):
        self._terminal_history = []
        self._pending_command = ""
        self._history_index = None
        self._history_draft = ""
        self._current_tool = "ffmpeg"
        self.progress_bar.setValue(0)
        self.progress_bar.setFormat("0%")
        self.progress_bar.hide()
        self.terminal.clear()
        ready_lines = self._command_ready_lines()
        kinds = ["banner", "meta", "info", "info"]
        for line, kind in zip(ready_lines, kinds):
            self._append_terminal_text(line, kind=kind)
        self._append_terminal_text("")
        self._append_prompt()
        self._prompt_pos = len(self.terminal.toPlainText())
        self._move_cursor_to_end()

    def _rebuild_terminal_view(self):
        current_command = self._pending_command if self._active else self._current_command()
        history = list(self._terminal_history)
        self._record_history = False
        try:
            self.terminal.clear()
            for event in history:
                if event["type"] == "text":
                    self._append_terminal_text(
                        event["text"],
                        ensure_newline=event["ensure_newline"],
                        kind=event["kind"],
                    )
                elif event["type"] == "prompt":
                    self._append_prompt()
            self._prompt_pos = len(self.terminal.toPlainText())
            if current_command:
                cursor = self.terminal.textCursor()
                cursor.movePosition(QTextCursor.MoveOperation.End)
                self.terminal.setTextCursor(cursor)
                cursor = self.terminal.textCursor()
                cursor.setCharFormat(self._kind_format("text"))
                cursor.insertText(current_command)
                self.terminal.setTextCursor(cursor)
                self._move_cursor_to_end()
        finally:
            self._record_history = True

    def _move_cursor_to_end(self):
        cursor = self.terminal.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        self.terminal.setTextCursor(cursor)
        self.terminal.ensureCursorVisible()

    def focus_terminal(self):
        if not hasattr(self, "terminal") or self.terminal is None:
            return
        self.terminal.setFocus(Qt.FocusReason.OtherFocusReason)
        self._move_cursor_to_end()

    def _append_terminal_text(self, text: str, ensure_newline: bool = True, kind: str = "text"):
        cursor = self.terminal.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        self.terminal.setTextCursor(cursor)
        cursor = self.terminal.textCursor()
        cursor.setCharFormat(self._kind_format(kind))
        suffix = "\n" if ensure_newline and not text.endswith("\n") else ""
        cursor.insertText(text + suffix)
        cursor.setCharFormat(self._kind_format("text"))
        self.terminal.setTextCursor(cursor)
        if self._record_history:
            self._terminal_history.append(
                {
                    "type": "text",
                    "text": text,
                    "ensure_newline": ensure_newline,
                    "kind": kind,
                }
            )
        self._move_cursor_to_end()

    def _append_prompt(self):
        cursor = self.terminal.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        self.terminal.setTextCursor(cursor)
        cursor = self.terminal.textCursor()
        cursor.setCharFormat(self._kind_format("prompt"))
        cursor.insertText(self._prompt_prefix)
        cursor.setCharFormat(self._kind_format("text"))
        self.terminal.setTextCursor(cursor)
        if self._record_history:
            self._terminal_history.append({"type": "prompt"})
        self._history_index = None
        self._history_draft = ""

    def _set_current_command(self, command: str):
        command = command or ""
        cursor = self.terminal.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        cursor.setPosition(min(self._prompt_pos, len(self.terminal.toPlainText())), QTextCursor.MoveMode.KeepAnchor)
        cursor.removeSelectedText()
        cursor.insertText(command)
        self.terminal.setTextCursor(cursor)
        self._move_cursor_to_end()

    def _push_history_command(self, command: str):
        command = (command or "").strip()
        if not command:
            return
        if self._command_history and self._command_history[-1] == command:
            return
        self._command_history.append(command)
        self._history_index = None
        self._history_draft = ""

    def _on_history_prev_requested(self):
        if self._active or not self._command_history:
            return
        current = self._current_command()
        if self._history_index is None:
            self._history_draft = current
            self._history_index = len(self._command_history) - 1
        elif self._history_index > 0:
            self._history_index -= 1
        self._set_current_command(self._command_history[self._history_index])

    def _on_history_next_requested(self):
        if self._active or self._history_index is None:
            return
        if self._history_index < len(self._command_history) - 1:
            self._history_index += 1
            self._set_current_command(self._command_history[self._history_index])
            return
        self._history_index = None
        self._set_current_command(self._history_draft)

    def _current_command(self) -> str:
        text = self.terminal.toPlainText()
        if self._prompt_pos < 0 or self._prompt_pos > len(text):
            return ""
        return text[self._prompt_pos:].strip()

    def _current_command_for_cursor(self):
        text = self.terminal.toPlainText()
        cursor_pos = self.terminal.textCursor().position()
        if cursor_pos < self._prompt_pos:
            cursor_pos = len(text)
        return text[self._prompt_pos:cursor_pos]

    def _soft_tokens(self, raw: str):
        if not raw:
            return []
        try:
            return self._parse_command_tokens(raw)
        except ValueError:
            return self._normalize_tokens(raw.replace("\n", " ").split())

    def _tokenize_command(self, raw: str):
        if not raw:
            return [], TXT_INVALID
        try:
            tokens = self._parse_command_tokens(raw)
        except ValueError:
            return [], TXT_BAD_PARSE
        return tokens, ""

    @staticmethod
    def _normalize_tokens(tokens):
        normalized = []
        for token in tokens:
            if len(token) >= 2 and token[0] == token[-1] and token[0] in {'"', "'"}:
                normalized.append(token[1:-1])
            else:
                normalized.append(token)
        return normalized

    @staticmethod
    def _is_quoted_token(token: str) -> bool:
        return len(token) >= 2 and token[0] == token[-1] and token[0] in {'"', "'"}

    @staticmethod
    def _strip_token(token: str) -> str:
        if len(token) >= 2 and token[0] == token[-1] and token[0] in {'"', "'"}:
            return token[1:-1]
        return token

    @classmethod
    def _is_option_token(cls, token: str) -> bool:
        if not token:
            return False
        if cls._is_quoted_token(token):
            return False
        if token in {"-", "--"}:
            return True
        if token.startswith("-") and not re.fullmatch(r"-\d+(\.\d+)?", token):
            return True
        return False

    def _parse_command_tokens(self, raw: str):
        raw_tokens = shlex.split(raw, posix=False)
        if not raw_tokens:
            raise ValueError("empty command")

        parsed = [self._strip_token(raw_tokens[0])]
        i = 1
        while i < len(raw_tokens):
            token = raw_tokens[i]
            if self._is_option_token(token):
                parsed.append(self._strip_token(token))
                if token in _NO_VALUE_OPTIONS:
                    i += 1
                    continue

                if token == "-i":
                    j = i + 1
                    while j < len(raw_tokens) and not self._is_option_token(raw_tokens[j]):
                        j += 1
                    if j <= i + 1:
                        raise ValueError("missing input path")
                    parsed.append(" ".join(self._strip_token(t) for t in raw_tokens[i + 1:j]))
                    i = j
                    continue

                if i + 1 < len(raw_tokens) and not self._is_option_token(raw_tokens[i + 1]):
                    parsed.append(self._strip_token(raw_tokens[i + 1]))
                    i += 2
                else:
                    i += 1
                continue

            parsed.append(" ".join(self._strip_token(t) for t in raw_tokens[i:]))
            break

        return parsed

    def _validate_command(self, raw: str):
        if not raw:
            return False, TXT_INVALID
        if any(ch in raw for ch in BLOCKED_CHARS) or "$(" in raw:
            return False, TXT_BLOCKED
        tokens, err = self._tokenize_command(raw)
        if err:
            return False, err
        if not tokens:
            return False, TXT_INVALID
        exe = os.path.basename(tokens[0]).lower()
        if exe not in {"ffmpeg", "ffmpeg.exe", "ffplay", "ffplay.exe", "ffprobe", "ffprobe.exe"}:
            return False, TXT_ONLY_FFMPEG
        return True, ""

    def _value_after(self, tokens, option):
        for idx, tok in enumerate(tokens[:-1]):
            if tok == option:
                return tokens[idx + 1]
        return ""

    def _guess_intent(self, tokens):
        if "-vn" in tokens:
            return "audio_extract"
        if "-an" in tokens:
            return "video_only"
        if "-ss" in tokens or "-to" in tokens or "-t" in tokens:
            return "clip"
        if "-vf" in tokens or "-r" in tokens:
            return "video_filter"
        if "-c:v" in tokens or "-crf" in tokens or "-preset" in tokens:
            return "video_encode"
        if "-c:a" in tokens or "-b:a" in tokens:
            return "audio_encode"
        return "general"

    def _extract_paths(self, tokens):
        input_hint = ""
        output_hint = ""
        for idx, tok in enumerate(tokens[:-1]):
            if tok == "-i" and idx + 1 < len(tokens):
                input_hint = tokens[idx + 1]
                break
        if tokens and not self._is_option_token(tokens[-1]):
            output_hint = tokens[-1]
        return input_hint, output_hint

    def _on_enter_pressed(self):
        if self._active:
            self._append_terminal_text("\n" + TXT_CANCELLED, kind="warning")
            self.cancel_conversion_signal.emit()
            return

        raw = self._current_command()
        ok, err = self._validate_command(raw)
        if not ok:
            self._pending_command = ""
            self._append_terminal_text("\n" + err, kind="error")
            self._append_prompt()
            self._prompt_pos = len(self.terminal.toPlainText())
            return

        if not self.ffmpeg_handler:
            self._pending_command = ""
            self._append_terminal_text("\n" + TXT_MISSING_FFMPEG, kind="error")
            self._append_prompt()
            self._prompt_pos = len(self.terminal.toPlainText())
            return

        self._active = True
        self._pending_command = raw
        self._push_history_command(raw)
        self._append_terminal_text("", kind="text")
        self._start_conversion_process(raw)

    def _start_conversion_process(self, raw: str):
        tokens, err = self._tokenize_command(raw)
        if err:
            self._active = False
            self._pending_command = ""
            self._append_terminal_text(err, kind="error")
            self._append_prompt()
            self._prompt_pos = len(self.terminal.toPlainText())
            return

        tool = os.path.basename(tokens[0]).lower()
        self._current_tool = "ffplay" if tool in {"ffplay", "ffplay.exe"} else (
            "ffprobe" if tool in {"ffprobe", "ffprobe.exe"} else "ffmpeg"
        )
        args = tokens[1:]
        input_hint, output_hint = self._extract_paths(tokens)
        if tool in {"ffprobe", "ffprobe.exe", "ffplay", "ffplay.exe"} and not input_hint:
            for tok in reversed(args):
                if tok and not tok.startswith("-"):
                    input_hint = tok
                    break
            if tool in {"ffplay", "ffplay.exe"}:
                output_hint = ""
        self.input_files = [input_hint] if input_hint else [f"{tool}-command"]
        self.output_dir = os.path.dirname(output_hint) if output_hint else ""
        self._output_path = output_hint
        if tool in {"ffprobe", "ffprobe.exe"} and not getattr(self.ffmpeg_handler, "ffprobe_path", ""):
            self._active = False
            self._pending_command = ""
            self._append_terminal_text("\n" + TXT_MISSING_FFPROBE, kind="error")
            self._append_prompt()
            self._prompt_pos = len(self.terminal.toPlainText())
            return
        if tool in {"ffplay", "ffplay.exe"} and not getattr(self.ffmpeg_handler, "ffplay_path", ""):
            self._active = False
            self._pending_command = ""
            self._append_terminal_text("\n" + TXT_MISSING_FFPLAY, kind="error")
            self._append_prompt()
            self._prompt_pos = len(self.terminal.toPlainText())
            return
        if tool in {"ffprobe", "ffprobe.exe"}:
            self.ffmpeg_handler.run_tool_command("ffprobe", 0, args, input_hint=input_hint, output_hint=output_hint)
        elif tool in {"ffplay", "ffplay.exe"}:
            self.ffmpeg_handler.run_tool_command("ffplay", 0, args, input_hint=input_hint, output_hint=output_hint)
        else:
            self.ffmpeg_handler.run_ffmpeg_command(0, args, input_hint=input_hint, output_hint=output_hint)

    def log_message(self, msg: str, kind: str = "info"):
        self._append_terminal_text(msg, kind=kind)

    def log_ffmpeg_line(self, idx: int, kind: str, text: str):
        if kind == "progress":
            return
        self._append_terminal_text(text, kind=kind)

    def update_overall_progress(self, *_):
        return

    def _on_log_line(self, idx, kind, text):
        if self._active and idx == 0:
            self.log_ffmpeg_line(idx, kind, text)

    def _on_started(self, idx, path):
        if self._active and idx == 0:
            self._append_terminal_text(f"running {self._current_tool} ...", kind="info")
            if self._current_tool == "ffmpeg":
                self.progress_bar.setValue(0)
                self.progress_bar.setFormat("0%")
                self.progress_bar.show()
            else:
                self.progress_bar.hide()

    def _on_progress(self, idx, msg, pct):
        if self._active and idx == 0 and self._current_tool == "ffmpeg":
            self.progress_bar.setValue(max(0, min(100, int(pct))))
            self.progress_bar.setFormat(f"{int(pct)}%")

    def _on_finished(self, idx, status, msg):
        if not self._active or idx != 0:
            return
        self._active = False
        self._pending_command = ""
        if self._current_tool == "ffmpeg" and status == "success":
            self.progress_bar.setValue(100)
            self.progress_bar.setFormat("100%")
        else:
            self.progress_bar.setValue(0)
            self.progress_bar.setFormat("0%")
        self.progress_bar.hide()
        kind = {"success": "success", "cancelled": "warning", "failure": "error"}.get(status, "info")
        self._append_terminal_text(msg, kind=kind)
        self._append_prompt()
        self._prompt_pos = len(self.terminal.toPlainText())

    def _on_interrupt_pressed(self):
        if not self._active:
            return
        self._append_terminal_text("^C", kind="warning")
        self.cancel_conversion_signal.emit()

    def showEvent(self, event):
        super().showEvent(event)
        QTimer.singleShot(0, self.focus_terminal)
