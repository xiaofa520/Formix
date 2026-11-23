import os
import json
import sys
import platform
import re
import tempfile
import shutil
import time
from collections import Counter
from pathlib import Path

if __name__ == "__main__":
    if __package__:
        from .launcher import main as launch
    else:
        from launcher import main as launch
    raise SystemExit(launch())

from PySide6.QtCore import QAbstractTableModel, QModelIndex, QDir, Qt, QSize, QRectF, QProcess, QStandardPaths, QUrl, QDateTime, QEvent, QPropertyAnimation, QTimer, QEasingCurve, QRunnable, QThreadPool, QObject, Signal, QVariantAnimation
from PySide6.QtGui import QColor, QFont, QFontDatabase, QFontMetricsF, QPalette, QIcon, QImage, QImageReader, QPainter, QPainterPath, QIntValidator
from PySide6.QtWidgets import (
    QApplication, QFileDialog, QFrame, QHBoxLayout, QLabel, QComboBox,
    QLineEdit, QTreeView, QHeaderView, QButtonGroup, QGridLayout, QMainWindow,
    QMessageBox, QPushButton, QProgressBar, QPlainTextEdit, QStackedWidget, QVBoxLayout,
    QWidget, QGraphicsOpacityEffect, QGraphicsDropShadowEffect, QSizePolicy, QStyledItemDelegate, QStyle,
)

if __package__:
    from .numbered_text import NumberedTextEdit
    from .diagnostics import event as diagnostic_event
    from .runtime_paths import ROOT, app_version, group_windows_processes
    from .button_input import connect_action, connect_navigation
    from .engines import AUDIO, INPUT_TYPES, MODEL_PROFILES, MODEL_REPOS, PAGES, WORKER, compression_options_for_sources, compression_profile, document_targets_for_sources, executable
    from .localization import LANGUAGE_CODES, LANGUAGE_NAMES, LanguageManager
    from .navigation_glass import BACKGROUND_DEFAULTS, BackgroundCanvas, GlassFrame, RadialReveal, SidebarGlass, contrast_icon
    from .dropdown import Dropdown, SearchDropdown, SettingsScrollArea, SettingsSlider
    from .settings_update import UpdateRow
    from .system_fonts import interface_families
    from .hardware_info import cuda_driver_version, hardware_names
    from .tasks import TaskService, kill_process_tree
    from .file_import import FileScanTask
    from .background_work import BROWSERS, browser_path, cleanup_path, open_folder_async, dispatch_web_url, run_background
else:
    from numbered_text import NumberedTextEdit
    from diagnostics import event as diagnostic_event
    from runtime_paths import ROOT, app_version, group_windows_processes
    from button_input import connect_action, connect_navigation
    from engines import AUDIO, INPUT_TYPES, MODEL_PROFILES, MODEL_REPOS, PAGES, WORKER, compression_options_for_sources, compression_profile, document_targets_for_sources, executable
    from localization import LANGUAGE_CODES, LANGUAGE_NAMES, LanguageManager
    from navigation_glass import BACKGROUND_DEFAULTS, BackgroundCanvas, GlassFrame, RadialReveal, SidebarGlass, contrast_icon
    from dropdown import Dropdown, SearchDropdown, SettingsScrollArea, SettingsSlider
    from settings_update import UpdateRow
    from system_fonts import interface_families
    from hardware_info import cuda_driver_version, hardware_names
    from tasks import TaskService, kill_process_tree
    from file_import import FileScanTask
    from background_work import BROWSERS, browser_path, cleanup_path, open_folder_async, dispatch_web_url, run_background

PAGE_INFO = {
    "图片提取文字": ("page_image_ocr", "output_format"),
    "音频转换": ("audio_convert", "output_format"),
    "视频转换": ("video_convert", "output_format"),
    "M3U8 合成": ("page_m3u8_merge", "output_format"),
    "音频压缩": ("audio_compress", "compression_method"),
    "视频压缩": ("video_compress", "compression_method"),
    "图片压缩": ("image_compress", "compression_method"),
    "音视频合并": ("page_merge", "output_format"),
    "音视频分离": ("page_split", "extract_content"),
    "图片转换": ("page_image", "output_format"),
    "文档转换": ("page_document", "output_format"),
    "PDF 转换": ("page_pdf", "output_format"),
}
PAGE_ICON = {
    "图片提取文字": "document.svg",
    "音频转换": "music.svg", "视频转换": "format.svg",
    "M3U8 合成": "playlist.svg",
    "音频压缩": "compress.svg", "视频压缩": "compress.svg", "图片压缩": "compress.svg",
    "音视频合并": "merge.svg", "音视频分离": "split.svg",
    "图片转换": "image.svg", "文档转换": "document.svg",
    "PDF 转换": "pdf.svg", "设置": "settings.svg",
}
ERROR_LOG_PATTERN = re.compile(
    r"(?i)(?:\b(?:error|failed|failure|fatal|exception|traceback|invalid|unsupported|not found|"
    r"could not|cannot|unable|non-zero exit status|no such file|access denied)\b|"
    r"错误|失败|异常|无效|不支持|找不到|未找到|无法|缺少|拒绝访问|"
    r"エラー|失敗|無効|見つかりません|오류|실패|잘못된|찾을 수 없|"
    r"ошиб|не удалось|не найден|неподдерж|erreur|échec|introuvable|impossible|invalide)"
)


def recommended_pdf_model(available_ram_gib):
    """Prefer layout-aware OCR while staying within the machine's free RAM."""
    if available_ram_gib < 3:
        return "pp-ocrv5-mobile"
    if platform.system() == "Darwin" and platform.machine().lower() in {"x86_64", "amd64"}:
        return "granite-docling-258m"
    if available_ram_gib >= 16 and "dots-ocr" in MODEL_PROFILES:
        return "dots-ocr"
    if available_ram_gib >= 6 and "paddleocr-vl-1.6" in MODEL_PROFILES:
        return "paddleocr-vl-1.6"
    if available_ram_gib >= 3 and "granite-docling-258m" in MODEL_PROFILES:
        return "granite-docling-258m"
    return "granite-docling-258m"


def available_system_memory_gib():
    try:
        import psutil
        return psutil.virtual_memory().available / 1024**3
    except (ImportError, OSError, AttributeError):
        return 4.0


class TaskProgressBar(QProgressBar):
    """Keep the accessible value exact while animating only the painted fill."""
    def __init__(self):
        super().__init__()
        self.fill_percent = 0.0
        self.transition = QVariantAnimation(self)
        self.transition.setDuration(130)
        self.transition.setEasingCurve(QEasingCurve.Type.OutCubic)
        self.transition.valueChanged.connect(self._paint_percent)
        self.valueChanged.connect(self._follow_progress)

    def _paint_percent(self, percent):
        self.fill_percent = percent
        self.update()

    def _follow_progress(self, percent):
        self.transition.stop()
        if percent <= self.fill_percent or percent in (0, 100):
            self._paint_percent(float(percent))
            return
        start = max(self.fill_percent, percent - 3.0)
        self._paint_percent(start)
        self.transition.setStartValue(start)
        self.transition.setEndValue(float(percent))
        self.transition.start()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(Qt.PenStyle.NoPen)
        dark = self.window().canvas.dark
        track = QRectF(self.contentsRect())
        radius = track.height() / 2
        painter.setBrush(QColor(238, 244, 252, 64) if dark else QColor(207, 218, 229, 185))
        painter.drawRoundedRect(track, radius, radius)
        if self.fill_percent > 0:
            track.setWidth(track.width() * self.fill_percent / self.maximum())
            painter.setBrush(QColor("#95bfe5" if dark else "#618db6"))
            painter.drawRoundedRect(track, min(radius, track.width() / 2), radius)


class QueueStatusLabel(QLabel):
    def __init__(self, status):
        super().__init__()
        self.setObjectName("queueStatus")
        self._fitting_font = False
        self._status_base_font = QFont(self.font())
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        self.set_status(status)

    def set_status(self, status, preserve=False):
        self.setAccessibleName(status)
        self.full_status = status
        self.preserve_text = preserve
        self.refresh_text()

    def refresh_text(self):
        if self._fitting_font:
            return
        self._fitting_font = True
        try:
            available = self.contentsRect()
            font = QFont(self._status_base_font)
            base_size = font.pixelSize()
            if base_size <= 0:
                base_size = max(10, round(font.pointSizeF() * self.logicalDpiY() / 72))
            minimum_size = max(9, round(base_size * .82))
            for size in range(base_size, minimum_size - 1, -1):
                font.setPixelSize(size)
                metrics = QFontMetricsF(font)
                if (metrics.horizontalAdvance(self.full_status) <= available.width()
                        and metrics.height() <= available.height()):
                    break
            self.setFont(font)
            text = (self.full_status if self.preserve_text or available.width() <= 0 else
                    self.fontMetrics().elidedText(
                        self.full_status, Qt.ElideMiddle, available.width()))
            self.setText(text)
            self.setToolTip(self.full_status if text != self.full_status else "")
        finally:
            self._fitting_font = False

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.refresh_text()

    def changeEvent(self, event):
        super().changeEvent(event)
        if (event.type() == QEvent.FontChange and hasattr(self, "full_status")
                and not self._fitting_font):
            self._status_base_font = QFont(self.font())
            self.refresh_text()


def make_button(language, key, callback=None, role="secondary", icon=None):
    button = language.bind(QPushButton(), key)
    button.setObjectName(role)
    button.setMinimumHeight(40)
    if icon:
        button.setProperty("glyph", icon)
        button.setIcon(QIcon(str(Path(__file__).with_name("assets") / "icons" / icon)))
        button.setIconSize(QSize(16, 16))
    if callback:
        connect_action(button, callback)
    return button


class OutputPathEdit(QLineEdit):
    def paintEvent(self, event):
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        bounds = QRectF(self.rect())
        for inset, alpha in enumerate((48, 29, 15, 6)):
            offset = inset + 0.5
            painter.setPen(QColor(0, 0, 0, alpha))
            painter.drawRoundedRect(bounds.adjusted(offset, offset, -offset, -offset),
                                    11 - offset, 11 - offset)
        painter.end()


class InputDropdown(Dropdown):
    """Editable dropdown for numeric settings with reusable preset choices."""
    def __init__(self, minimum, maximum, parent=None):
        super().__init__(parent)
        self.setEditable(True)
        self.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        self.setCompleter(None)
        editor = self.lineEdit()
        editor.setObjectName("inputDropdownEditor")
        editor.setValidator(QIntValidator(minimum, maximum, editor))


class ResolutionDropdown(Dropdown):
    """Editable width × height selector for video compression."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setEditable(True)
        self.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        self.setCompleter(None)
        editor = self.lineEdit()
        editor.setObjectName("inputDropdownEditor")
        editor.installEventFilter(self)

    def eventFilter(self, watched, event):
        if watched is self.lineEdit() and event.type() == QEvent.Type.FocusIn:
            QTimer.singleShot(0, self.clear_selected_resolution_text)
        return super().eventFilter(watched, event)

    def clear_selected_resolution_text(self):
        index = self.currentIndex()
        if index >= 0 and self.lineEdit().text() == self.itemText(index):
            self.lineEdit().clear()


def input_dropdown_value(combo, default):
    index = combo.currentIndex()
    text = combo.currentText().strip()
    if index >= 0 and text == combo.itemText(index):
        return combo.currentData()
    try:
        return int(text)
    except ValueError:
        return default


def nav_icon(name):
    path = Path(__file__).with_name("assets") / "icons" / PAGE_ICON[name]
    return QIcon(str(path))


def file_filter(label, extensions):
    patterns = " ".join("*" + suffix for suffix in sorted(extensions))
    return f"{label} ({patterns})"


class FileRowDelegate(QStyledItemDelegate):
    def __init__(self, view):
        super().__init__(view)
        self.view = view

    def paint(self, painter, option, index):
        selected = bool(option.state & QStyle.StateFlag.State_Selected)
        if selected:
            if index.column() == 0:
                row_rect = QRectF(0, option.rect.top() + 2,
                                 self.view.viewport().width(), max(0, option.rect.height() - 4))
                path = QPainterPath()
                path.addRoundedRect(row_rect, 9, 9)
                painter.save()
                painter.setRenderHint(QPainter.RenderHint.Antialiasing)
                painter.fillPath(path, QColor("#dce8f5" if not self.view.window().canvas.dark else "#35516e"))
                painter.restore()
            option.palette.setColor(
                QPalette.ColorRole.Text,
                QColor("#244461" if not self.view.window().canvas.dark else "#f4f8ff"),
            )
            option.state &= ~QStyle.StateFlag.State_Selected
        super().paint(painter, option, index)


def card(language, title, description=""):
    frame = GlassFrame(19)
    frame.setObjectName("card")
    layout = QVBoxLayout(frame)
    layout.setContentsMargins(20, 18, 20, 18)
    layout.setSpacing(12)
    heading = language.bind(QLabel(), title)
    heading.setObjectName("cardTitle")
    layout.addWidget(heading)
    if description:
        note = language.bind(QLabel(), description)
        note.setObjectName("muted")
        note.setWordWrap(True)
        layout.addWidget(note)
    return frame, layout


class FileListModel(QAbstractTableModel):
    def __init__(self, parent):
        super().__init__(parent)
        self.sources = []
        self.details = {}
        self.states = {}
        self.in_flight = set()
        self.pending = set()
        self.suffixes = Counter()

    def rowCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self.sources)

    def columnCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else 2

    def stringList(self):
        return self.sources.copy()

    def setStringList(self, sources):
        details = {}
        for source in sources:
            if source in self.details:
                details[source] = self.details[source]
            elif source.lower().startswith(("http://", "https://")):
                details[source] = (QUrl(source).fileName() or "M3U8", "—")
            else:
                details[source] = (Path(source).name, "—")
        self.beginResetModel()
        self.sources = list(sources)
        self.details = details
        self.states = {p: state for p, state in self.states.items() if p in details}
        self.in_flight.intersection_update(details)
        self.pending = {p for p in sources if p not in self.in_flight and self.states.get(p) != 'file_done'}
        self.suffixes = Counter(Path(p).suffix.lower() for p in sources)
        self.endResetModel()

    def append_batch(self, entries):
        entries = [entry for entry in entries if entry[0] not in self.details]
        if not entries:
            return 0
        start = len(self.sources)
        self.beginInsertRows(QModelIndex(), start, start + len(entries) - 1)
        for source, name, size in entries:
            self.sources.append(source)
            self.details[source] = (name, size)
            self.pending.add(source)
            self.suffixes[Path(source).suffix.lower()] += 1
        self.endInsertRows()
        return len(entries)

    def set_state(self, source, key):
        if source not in self.details:
            return
        self.states[source] = key
        if key in ("file_queued", "queue_processing", "file_paused"):
            self.in_flight.add(source)
        else:
            self.in_flight.discard(source)
        if source in self.in_flight or key == 'file_done':
            self.pending.discard(source)
        else:
            self.pending.add(source)

    def pending_sources(self):
        return [p for p in self.sources if p in self.pending]

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid():
            return None
        if role == Qt.ItemDataRole.DisplayRole:
            source = self.sources[index.row()]
            return self.details[source][index.column()]
        if role == Qt.ItemDataRole.TextAlignmentRole and index.column() == 1:
            return Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        return None


class ToolPage(QWidget):
    def __init__(self, name, window):
        super().__init__()
        self.name = name
        self.window = window
        self._folder_scans = set()
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(14)
        self.page_key, option_label = PAGE_INFO[name]

        columns = QHBoxLayout()
        columns.setSpacing(16)
        root.addLayout(columns, 1)

        import_card = GlassFrame(19)
        import_card.setObjectName("card")
        import_layout = QVBoxLayout(import_card)
        import_layout.setContentsMargins(18, 15, 18, 16)
        import_layout.setSpacing(11)
        import_card.setMinimumWidth(360)
        self.files = FileListModel(self)
        header = QHBoxLayout()
        header.setSpacing(8)
        title = self.window.language.bind(QLabel(), "file_list")
        title.setObjectName("cardTitle")
        header.addWidget(title)
        self.file_count = self.window.language.bind(QLabel(), "file_count_short")
        self.file_count.setObjectName("fileCount")
        header.addWidget(self.file_count)
        header.addStretch(1)
        self.add_files_button = make_button(self.window.language, "add_files", self.pick, icon="plus.svg")
        self.add_files_button.setObjectName("importAction")
        self.add_files_button.setFixedHeight(32)
        self.add_files_button.setIconSize(QSize(14, 14))
        header.addWidget(self.add_files_button)
        self.add_folder_button = QPushButton()
        self.add_folder_button.setObjectName("importIconAction")
        self.add_folder_button.setProperty("glyph", "folder.svg")
        self.add_folder_button.setIcon(QIcon(str(Path(__file__).with_name("assets") / "icons" / "folder.svg")))
        self.add_folder_button.setIconSize(QSize(14, 14))
        self.add_folder_button.setFixedSize(32, 32)
        connect_action(self.add_folder_button, self.pick_input_folder)
        header.addWidget(self.add_folder_button)
        self.remove_button = QPushButton()
        self.remove_button.setObjectName("importIconAction")
        self.remove_button.setProperty("contentAction", True)
        self.remove_button.setProperty("glyph", "trash.svg")
        self.remove_button.setIcon(QIcon(str(Path(__file__).with_name("assets") / "icons" / "trash.svg")))
        self.remove_button.setIconSize(QSize(14, 14))
        self.remove_button.setFixedSize(32, 32)
        connect_action(self.remove_button, self.remove_selected)
        header.addWidget(self.remove_button)
        self.clear_button = QPushButton()
        self.clear_button.setObjectName("importIconAction")
        self.clear_button.setProperty("contentAction", True)
        self.clear_button.setProperty("glyph", "x.svg")
        self.clear_button.setIcon(QIcon(str(Path(__file__).with_name("assets") / "icons" / "x.svg")))
        self.clear_button.setIconSize(QSize(14, 14))
        self.clear_button.setFixedSize(32, 32)
        connect_action(self.clear_button, self.clear_files)
        header.addWidget(self.clear_button)
        import_layout.addLayout(header)
        self.m3u8_url = None
        if name == "M3U8 合成":
            url_row = QHBoxLayout()
            url_row.setSpacing(8)
            self.m3u8_url = QLineEdit()
            self.window.language.bind(self.m3u8_url, "m3u8_url_placeholder", "placeholder")
            self.m3u8_url.setClearButtonEnabled(True)
            self.m3u8_url.setMinimumHeight(34)
            url_row.addWidget(self.m3u8_url, 1)
            add_url = make_button(self.window.language, "add_m3u8_link", self.add_m3u8_link, icon="globe.svg")
            add_url.setFixedHeight(32)
            add_url.setIconSize(QSize(14, 14))
            url_row.addWidget(add_url)
            self.m3u8_url.returnPressed.connect(self.add_m3u8_link)
            import_layout.addLayout(url_row)

        self.view = QTreeView()
        self.view.setModel(self.files)
        self.view.setItemDelegate(FileRowDelegate(self.view))
        self.view.setObjectName("fileList")
        self.view.setRootIsDecorated(False)
        self.view.setItemsExpandable(False)
        self.view.setHeaderHidden(True)
        self.view.header().setStretchLastSection(False)
        self.view.header().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.view.header().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.view.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.view.setTextElideMode(Qt.TextElideMode.ElideMiddle)
        self.view.setEditTriggers(QTreeView.EditTrigger.NoEditTriggers)
        self.view.setSelectionMode(QTreeView.SelectionMode.ExtendedSelection)
        self.view.setSelectionBehavior(QTreeView.SelectionBehavior.SelectRows)
        self.view.setUniformRowHeights(True)
        self.view.selectionModel().selectionChanged.connect(self.update_remove_state)
        self.file_stack = QStackedWidget()
        self.file_stack.setObjectName("fileStack")
        self.empty_state = QFrame()
        self.empty_state.setObjectName("fileEmpty")
        empty_layout = QVBoxLayout(self.empty_state)
        empty_layout.addStretch(1)
        empty_icon = QLabel()
        empty_icon.setObjectName("emptyIcon")
        empty_icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        empty_icon.setProperty("glyph", "plus.svg")
        empty_icon.setPixmap(QIcon(str(Path(__file__).with_name("assets") / "icons" / "plus.svg")).pixmap(QSize(30, 30)))
        empty_layout.addWidget(empty_icon)
        self.empty_title = self.window.language.bind(QLabel(), "empty_files_title")
        self.empty_title.setObjectName("emptyTitle")
        self.empty_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        empty_layout.addWidget(self.empty_title)
        self.empty_hint = self.window.language.bind(QLabel(), "drop_files")
        self.empty_hint.setObjectName("emptyHint")
        self.empty_hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.empty_hint.setWordWrap(True)
        empty_layout.addWidget(self.empty_hint)
        empty_layout.addStretch(1)
        self.file_stack.addWidget(self.empty_state)
        self.file_stack.addWidget(self.view)
        import_layout.addWidget(self.file_stack, 1)
        content_column = QVBoxLayout()
        content_column.setSpacing(14)
        content_column.addWidget(import_card, 1)
        columns.addLayout(content_column, 3)

        settings_card, settings_layout = card(self.window.language, "output_settings")
        settings_card.setMaximumWidth(330)
        self.audio = None
        if name == "音视频合并":
            self.audio = QLineEdit()
            self.window.language.bind(self.audio, "track_placeholder", "placeholder")
            self.audio.setMinimumHeight(42)
            settings_layout.addWidget(self.window.language.bind(QLabel(), "audio_track"))
            settings_layout.addWidget(self.audio)
            settings_layout.addWidget(make_button(self.window.language, "choose_audio", self.pick_audio, icon="music.svg"))
        self.option = Dropdown()
        option_keys = {
            "balanced": "compression_balanced", "quality": "compression_quality", "small": "compression_small",
            "提取音频 · m4a": "option.audio", "提取视频 · mkv": "option.video",
            "xlsx": "format_xlsx", "copy": "image_ocr_only_copy",
        }
        for value in PAGES[name]:
            key = option_keys.get(value)
            index = self.option.count()
            self.option.addItem(self.window.t(key) if key else value, value)
            if key:
                self.option.setItemData(index, key, Qt.ItemDataRole.UserRole + 3)
        self.option.setMinimumHeight(42)
        settings_layout.addWidget(self.window.language.bind(QLabel(), option_label))
        settings_layout.addWidget(self.option)
        if name == "音视频分离":
            self.option.clear()
            for value in ("audio", "video", "both"):
                self.option.addItem(window.t("split_" + value), value)
                self.option.setItemData(self.option.count() - 1, "split_" + value, Qt.ItemDataRole.UserRole + 3)
            self.split_format = Dropdown()
            self.split_format.setMinimumHeight(42)
            settings_layout.addWidget(window.language.bind(QLabel(), "output_format"))
            settings_layout.addWidget(self.split_format)
            def update_split_formats():
                self.split_format.clear()
                mode = self.option.currentData()
                formats = {"audio": ["m4a", "mp3", "wav", "flac", "aac", "ogg", "opus"],
                           "video": ["mp4", "mkv", "mov", "avi", "webm"],
                           "both": ["m4a+mp4", "mp3+mp4", "wav+mp4", "flac+mkv", "opus+webm"]}[mode]
                for fmt in formats:
                    self.split_format.addItem(fmt.upper().replace("+", " + "), fmt)
            self.option.currentIndexChanged.connect(update_split_formats)
            update_split_formats()
        if name == "图片提取文字":
            settings_layout.addWidget(window.language.bind(QLabel(), "image_ocr_model"))
            self.ocr_model_combo = Dropdown()
            self.ocr_model_combo.setMinimumHeight(42)
            for key, profile in MODEL_PROFILES.items():
                self.ocr_model_combo.addItem(profile.get("label", MODEL_REPOS[key].split('/')[-1]), key)
            saved = window.language.settings.value("imageOcr/model", "pp-ocrv5-mobile", type=str)
            index = self.ocr_model_combo.findData(saved)
            self.ocr_model_combo.setCurrentIndex(index if index >= 0 else self.ocr_model_combo.findData("pp-ocrv5-mobile"))
            self.ocr_model_combo.currentIndexChanged.connect(self.ocr_model_changed)
            settings_layout.addWidget(self.ocr_model_combo)
            hint = window.language.bind(QLabel(), "image_ocr_model_hint")
            hint.setWordWrap(True)
            hint.setOpenExternalLinks(False)
            hint.linkActivated.connect(lambda _: window.open_ocr_model_settings(self.ocr_model_combo.currentData()))
            hint.setObjectName("hint")
            settings_layout.addWidget(hint)
        self.icon_sizes_label = None
        self.icon_sizes = None
        if name == "图片转换":
            self.icon_sizes_label = self.window.language.bind(QLabel(), "image_icon_sizes")
            self.icon_sizes = Dropdown()
            for key, values in (("image_icon_all", [32, 64, 128]), ("image_icon_32", [32]),
                                ("image_icon_64", [64]), ("image_icon_128", [128])):
                index = self.icon_sizes.count()
                self.icon_sizes.addItem(self.window.t(key), values)
                self.icon_sizes.setItemData(index, key, Qt.ItemDataRole.UserRole + 3)
            self.icon_sizes.setCurrentIndex(0)
            self.icon_sizes.setMinimumHeight(42)
            self.icon_sizes_label.setVisible(False)
            self.icon_sizes.setVisible(False)
            settings_layout.addWidget(self.icon_sizes_label)
            settings_layout.addWidget(self.icon_sizes)
            self.option.currentIndexChanged.connect(self.update_icon_size_visibility)
        self.compression_parameter_label = None
        self.compression_parameter = None
        self.audio_bitrate = None
        if name in {"音频压缩", "视频压缩", "图片压缩"}:
            self.compression_parameter_label = self.window.language.bind(QLabel(), {
                "音频压缩": "compression_channels",
                "视频压缩": "compression_max_dimensions",
                "图片压缩": "compression_dimensions",
            }[name])
            settings_layout.addWidget(self.compression_parameter_label)
            self.compression_parameter = ResolutionDropdown() if name == "视频压缩" else Dropdown()
            self.compression_parameter.setMinimumHeight(42)
            if name == "视频压缩":
                index = self.compression_parameter.count()
                self.compression_parameter.addItem(self.window.t("compression_original_resolution"), "original")
                self.compression_parameter.setItemData(index, "compression_original_resolution", Qt.ItemDataRole.UserRole + 3)
                for resolution in ("3840×2160", "2560×1440", "1920×1080", "1080×1920",
                                   "1280×720", "720×1280", "854×480", "640×480"):
                    self.compression_parameter.addItem(resolution, resolution)
                self.compression_parameter.setCurrentIndex(0)
                self.compression_parameter.setPlaceholderText(self.window.t("compression_resolution_placeholder"))
                self.compression_parameter.setObjectName("resolutionInput")
                self.compression_parameter.setProperty("popupWidth", 292)
                settings_layout.addWidget(self.compression_parameter)
                self.window.language.bind(self.compression_parameter, "compression_height_hint", "toolTip")
                self.window.language.bind(self.compression_parameter.lineEdit(), "compression_resolution_placeholder", "placeholder")
            else:
                settings_layout.addWidget(self.compression_parameter)
            if name == "音频压缩":
                self.audio_bitrate = InputDropdown(32, 512)
                self.audio_bitrate.setMinimumHeight(42)
                index = self.audio_bitrate.count()
                self.audio_bitrate.addItem(self.window.t("compression_profile_bitrate"), 0)
                self.audio_bitrate.setItemData(index, "compression_profile_bitrate", Qt.ItemDataRole.UserRole + 3)
                for bitrate in (32, 48, 64, 96, 128, 160, 192, 256, 320, 512):
                    self.audio_bitrate.addItem(f"{bitrate} kb/s", bitrate)
                self.audio_bitrate.setCurrentIndex(0)
                self.window.language.bind(self.audio_bitrate, "compression_bitrate_hint", "toolTip")
                self.window.language.bind(self.audio_bitrate.lineEdit(), "compression_bitrate_placeholder", "placeholder")
                settings_layout.addWidget(self.window.language.bind(QLabel(), "compression_bitrate"))
                settings_layout.addWidget(self.audio_bitrate)
        settings_layout.addSpacing(8)
        settings_layout.addWidget(self.window.language.bind(QLabel(), "save_to"))
        self.destination = OutputPathEdit(str(self.window.default_output))
        self.destination.setObjectName("outputPath")
        self.destination.setReadOnly(True)
        self.destination.setMinimumHeight(42)
        settings_layout.addWidget(self.destination)
        folder_actions = QHBoxLayout()
        folder_actions.addWidget(make_button(self.window.language, "choose_folder", self.pick_folder, icon="folder.svg"))
        folder_actions.addWidget(make_button(self.window.language, "open_folder", self.open_folder, icon="external-link.svg"))
        settings_layout.addLayout(folder_actions)
        settings_layout.addStretch(1)
        actions = QHBoxLayout()
        actions.setSpacing(8)
        self.submit = make_button(self.window.language, "start", self.enqueue, "primary", "play.svg")
        self.submit.setMinimumWidth(140)
        self.submit.setEnabled(False)
        self.pause = make_button(self.window.language, "pause", role="primary", icon="pause.svg")
        self.window.language.bind(self.pause, "pause_hold_hint", "toolTip")
        self.pause_hold_fired = False
        self.pause_hold_timer = QTimer(self)
        self.pause_hold_timer.setSingleShot(True)
        self.pause_hold_timer.setInterval(800)
        self.pause_hold_timer.timeout.connect(self.cancel_with_pause_hold)
        self.pause.pressed.connect(self.begin_pause_hold)
        self.pause.released.connect(self.pause_hold_timer.stop)
        connect_action(self.pause, self.activate_pause)
        self.pause.setMinimumWidth(96)
        self.pause.setEnabled(False)
        actions.addWidget(self.submit, 1)
        actions.addWidget(self.pause)
        settings_layout.addLayout(actions)
        columns.addWidget(settings_card, 2)
        if name == "图片提取文字":
            result_card = GlassFrame(16)
            result_card.setObjectName("logPanel")
            layout = QVBoxLayout(result_card)
            layout.setContentsMargins(15, 10, 15, 11)
            header = QHBoxLayout()
            title = window.language.bind(QLabel(), "image_ocr_result")
            title.setObjectName("logTitle")
            header.addWidget(title)
            header.addStretch()
            self.ocr_result = NumberedTextEdit()
            self.ocr_result.setObjectName("logView")
            window.language.bind(self.ocr_result, "image_ocr_hint", "placeholder")
            self.ocr_result.setMinimumHeight(85)
            self.ocr_result.setMaximumHeight(140)
            copy = make_button(window.language, "image_ocr_copy", lambda: QApplication.clipboard().setText(self.ocr_result.toPlainText()), icon="copy.svg")
            copy.setObjectName("logAction")
            copy.setMinimumHeight(30)
            copy.setEnabled(False)
            self.ocr_result.textChanged.connect(lambda: copy.setEnabled(bool(self.ocr_result.toPlainText())))
            header.addWidget(copy)
            layout.addLayout(header)
            layout.addWidget(self.ocr_result)
            content_column.addWidget(result_card)
            window.tasks.output_ready.connect(self.receive_ocr_result)
            window.tasks.ocr_text_ready.connect(lambda text: self.ocr_result.setPlainText(text))
            def update_ocr_output_mode():
                copy_only = self.option.currentData() == "copy"
                result_card.setVisible(copy_only)
                self.destination.setEnabled(not copy_only)
            self.option.currentIndexChanged.connect(update_ocr_output_mode)
            update_ocr_output_mode()
        self.files.modelReset.connect(self.update_file_state)
        self.files.rowsInserted.connect(self.update_file_state)
        self.update_import_tooltips()
        self.update_file_state()

    def begin_pause_hold(self):
        self.pause_hold_fired = False
        self.pause_hold_timer.start()

    def cancel_with_pause_hold(self):
        self.pause_hold_fired = True
        self.window.tasks.stop()

    def activate_pause(self):
        if self.pause_hold_fired:
            self.pause_hold_fired = False
            return
        self.window.tasks.toggle_pause()

    def pick(self):
        paths, _ = QFileDialog.getOpenFileNames(
            self, self.window.t("dialog_select_files"), str(Path.home()),
            file_filter(self.window.t(self.page_key), INPUT_TYPES[self.name])
        )
        count = self.add_files(paths)
        if count:
            self.window.show_drop_toast(count)

    def pick_input_folder(self):
        folder = QFileDialog.getExistingDirectory(self, self.window.t("add_folder"), str(Path.home()))
        if not folder:
            return
        self.add_files([folder])

    def on_import_batch(self, task, entries):
        try:
            if not self.window.closing and not task.cancelled.is_set():
                task.added_count += self.files.append_batch(entries)
        finally:
            task.slots.release()

    def on_folder_scan_finished(self, task, skipped, error):
        self._folder_scans.discard(task)
        if self.window.closing:
            return
        self.add_folder_button.setEnabled(not self._folder_scans)
        if task.added_count:
            self.window.show_drop_toast(task.added_count)
        if skipped:
            self.window.append_log(self.name, self.window.t("skipped_type", count=skipped, page=self.window.t(self.page_key)))
        if error:
            self.window.append_log(self.name, error)

    def add_files(self, paths):
        diagnostic_event('import_requested', page=self.name, paths=paths)
        if paths:
            task = FileScanTask(paths, INPUT_TYPES[self.name])
            task.signals.batch.connect(self.on_import_batch, Qt.ConnectionType.QueuedConnection)
            task.signals.finished.connect(self.on_folder_scan_finished, Qt.ConnectionType.QueuedConnection)
            self._folder_scans.add(task)
            self.add_folder_button.setEnabled(False)
            QThreadPool.globalInstance().start(task)
        return 0  # The completion handler reports the asynchronously imported count.

    def add_m3u8_link(self):
        if self.m3u8_url is None:
            return
        link = QUrl(self.m3u8_url.text().strip(), QUrl.ParsingMode.StrictMode)
        if not link.isValid() or link.scheme().lower() not in {"http", "https"} or not link.host():
            QMessageBox.information(self, self.window.t("page_m3u8_merge"),
                                    self.window.t("invalid_m3u8_url"))
            return
        value = link.toString(QUrl.ComponentFormattingOption.FullyEncoded)
        current = self.files.stringList()
        if value not in current:
            self.files.setStringList(current + [value])
            self.window.show_drop_toast(1)
        self.m3u8_url.clear()

    def update_import_tooltips(self):
        self.add_folder_button.setToolTip(self.window.t("add_folder"))
        self.add_folder_button.setAccessibleName(self.window.t("add_folder"))
        self.remove_button.setToolTip(self.window.t("remove_selected"))
        self.remove_button.setAccessibleName(self.window.t("remove_selected"))
        self.clear_button.setToolTip(self.window.t("clear"))
        self.clear_button.setAccessibleName(self.window.t("clear"))

    def update_remove_state(self, *_):
        self.remove_button.setEnabled(not self.files.in_flight and bool(self.view.selectionModel().selectedRows()))

    def update_file_actions(self):
        self.submit.setEnabled(bool(self.files.pending) and self.option.currentData() is not None)
        self.clear_button.setEnabled(bool(self.files.sources) and not self.files.in_flight)
        self.update_remove_state()

    def update_file_state(self):
        self.file_count.setText(self.window.t("file_count_short", count=len(self.files.sources)))
        self.file_stack.setCurrentWidget(self.view if self.files.sources else self.empty_state)
        paths = ['source' + suffix for suffix in self.files.suffixes]
        if self.name == "图片转换":
            self.update_image_targets(paths)
        elif self.name == "文档转换":
            self.update_document_targets(paths)
        elif self.name in {"音频压缩", "视频压缩", "图片压缩"}:
            self.update_compression_options(paths)
        self.update_file_actions()

    def update_image_targets(self, paths):
        current = self.option.currentData()
        suffixes = {Path(path).suffix.lower() for path in paths}
        available = getattr(self.window, "image_formats", set(PAGES["图片转换"]) - {"heic", "avif"})
        targets = [target for target in PAGES["图片转换"] if target in available]
        if suffixes and not suffixes <= {".ai", ".svg"}:
            targets = [target for target in targets if target != "svg"]
        vector_pdf = suffixes == {".ai"}
        blocked = self.option.blockSignals(True)
        self.option.clear()
        for target in targets:
            index = self.option.count()
            self.option.addItem(self.window.t("image_vector_" + target) if target in {"pdf", "svg"} and vector_pdf else target.upper(), target)
            if target == "pdf" and vector_pdf:
                self.option.setItemData(index, "image_vector_pdf", Qt.ItemDataRole.UserRole + 3)
            elif target == "svg" and vector_pdf:
                self.option.setItemData(index, "image_vector_svg", Qt.ItemDataRole.UserRole + 3)
        selected = self.option.findData(current)
        self.option.setCurrentIndex(selected if selected >= 0 else (0 if targets else -1))
        self.option.blockSignals(blocked)
        self.update_icon_size_visibility()

    def update_icon_size_visibility(self, *_):
        if self.icon_sizes is not None:
            visible = self.option.currentData() == "ico"
            self.icon_sizes_label.setVisible(visible)
            self.icon_sizes.setVisible(visible)

    def update_document_targets(self, paths):
        targets = document_targets_for_sources(paths)
        current = self.option.currentData()
        blocked = self.option.blockSignals(True)
        self.option.clear()
        for target in targets:
            self.option.addItem(target.upper(), target)
        selected = self.option.findData(current)
        self.option.setCurrentIndex(selected if selected >= 0 else (0 if targets else -1))
        self.option.blockSignals(blocked)

    def update_compression_options(self, paths):
        current = self.option.currentData()
        choices = compression_options_for_sources(self.name, paths)
        suffixes = {Path(path).suffix.lower() for path in paths}
        profiles = {compression_profile(self.name, suffix) for suffix in suffixes}
        lossless_mode = profiles == {"audio_lossless"} or profiles == {"image_png"}
        if self.audio_bitrate is not None:
            self.audio_bitrate.setEnabled(not (self.name == "音频压缩" and profiles == {"audio_lossless"}))
        blocked = self.option.blockSignals(True)
        self.option.clear()
        for mode, detail in choices:
            if lossless_mode:
                key = "compression_fast" if mode == "quality" else "compression_lossless_" + mode
            else:
                key = "compression_" + mode
            index = self.option.count()
            self.option.addItem(self.window.t(key) + (f" · {detail}" if detail else ""), mode)
            self.option.setItemData(index, key, Qt.ItemDataRole.UserRole + 3)
            if detail:
                self.option.setItemData(index, detail, Qt.ItemDataRole.UserRole + 4)
        selected = self.option.findData(current)
        self.option.setCurrentIndex(selected if selected >= 0 else (0 if choices else -1))
        self.option.blockSignals(blocked)
        if self.name != "视频压缩":
            parameter_choices = {
                "音频压缩": [("original", "compression_original_channels"), ("mono", "compression_mono")],
                "图片压缩": [("original", "compression_original_dimensions"), ("75", "compression_75_percent"),
                             ("50", "compression_50_percent")],
            }[self.name]
            current_parameter = self.compression_parameter.currentData()
            blocked = self.compression_parameter.blockSignals(True)
            self.compression_parameter.clear()
            for value, key in parameter_choices:
                index = self.compression_parameter.count()
                self.compression_parameter.addItem(self.window.t(key), value)
                self.compression_parameter.setItemData(index, key, Qt.ItemDataRole.UserRole + 3)
            selected_parameter = self.compression_parameter.findData(current_parameter)
            self.compression_parameter.setCurrentIndex(selected_parameter if selected_parameter >= 0 else 0)
            self.compression_parameter.blockSignals(blocked)

    def remove_selected(self):
        chosen = {index.row() for index in self.view.selectionModel().selectedRows()}
        self.files.setStringList([p for row, p in enumerate(self.files.stringList()) if row not in chosen])

    def clear_files(self):
        for routes in self.window.drop_scans.values():
            for ext in [ext for ext, page in routes.items() if page is self]:
                del routes[ext]
        for task in self._folder_scans:
            task.cancelled.set()
        self.files.setStringList([])
        if self.m3u8_url is not None:
            self.m3u8_url.clear()

    def pick_audio(self):
        path, _ = QFileDialog.getOpenFileName(
            self, self.window.t("dialog_select_audio"), str(Path.home()), file_filter(self.window.t("group_audio"), AUDIO)
        )
        if path:
            self.audio.setText(path)

    def pick_folder(self):
        folder = QFileDialog.getExistingDirectory(
            self, self.window.t("choose_folder"), self.destination.text() or str(self.window.default_output)
        )
        if folder:
            self.destination.setText(folder)
            diagnostic_event('output_directory_selected', page=self.name, path=folder)

    def enqueue(self):
        files = self.files.pending_sources()
        audio = self.audio.text().strip() if self.audio else ""
        if self.name == "音视频合并" and not Path(audio).is_file():
            QMessageBox.information(self, self.window.t("need_audio_title"), self.window.t("need_audio_message"))
            return
        folder = Path(self.destination.text()).expanduser().absolute()
        for path in files:
            link = QUrl(path)
            is_remote = self.name == "M3U8 合成" and link.scheme().lower() in {"http", "https"}
            source = path if is_remote else Path(path)
            acceleration = self.window.video_acceleration_combo.currentData()
            job = (self.name, source, self.option.currentData(), audio, folder, acceleration)
            if self.name == "音视频分离":
                job += ({"split_format": self.split_format.currentData()},)
            elif self.name in {"图片提取文字", "PDF 转换"}:
                model = self.ocr_model_combo.currentData() if self.name == "图片提取文字" else self.window.models.name
                job += ({"recognition_model": model},)
            elif self.name == "视频压缩":
                field = self.compression_parameter
                text = field.currentText().strip()
                if field.currentIndex() >= 0 and text == field.itemText(field.currentIndex()):
                    selected_value = field.currentData()
                else:
                    selected_value = text
                if selected_value in (None, "", "original"):
                    width = height = "original"
                else:
                    match = re.fullmatch(r"(\d{3,5})(?:\s*[xX×*]\s*|\s+)(\d{3,5})", str(selected_value))
                    if not match:
                        QMessageBox.information(self, self.window.t("compression_max_dimensions"),
                                                self.window.t("compression_resolution_invalid"))
                        return
                    width, height = map(int, match.groups())
                    if not (144 <= width <= 7680 and 144 <= height <= 4320):
                        QMessageBox.information(self, self.window.t("compression_max_dimensions"),
                                                self.window.t("compression_resolution_invalid"))
                        return
                params = {"width": width, "height": height,
                          "detail": height if isinstance(height, int) else "original"}
                job += (params,)
            elif self.compression_parameter is not None:
                detail = input_dropdown_value(self.compression_parameter, "original") or "original"
                params = {"detail": detail}
                if self.audio_bitrate is not None:
                    bitrate = input_dropdown_value(self.audio_bitrate, 0)
                    params["bitrate"] = 0 if bitrate == 0 else max(32, bitrate)
                job += (params,)
            elif self.icon_sizes is not None and self.option.currentData() == "ico":
                job += ({"icon_sizes": self.icon_sizes.currentData() or [32, 64, 128]},)
            self.window.tasks.queue.append(job)
            self.files.set_state(path, "file_queued")
        if files:
            self.window.append_log(self.name, self.window.t('log_queued_count', count=len(files)))
        self.update_file_actions()
        self.window.tasks.next_job()
        self.window.update_queue_label()
        self.window.save_recovery_state()

    def ocr_model_changed(self):
        key = self.ocr_model_combo.currentData()
        self.window.language.settings.setValue("imageOcr/model", key)
        if not (self.window.model_root / key / "READY").is_file():
            self.window.open_ocr_model_settings(key)

    def receive_ocr_result(self, page, path):
        if page != self.name:
            return
        def received(text, error):
            if error:
                self.window.append_log(self.name, str(error))
            else:
                self.ocr_result.setPlainText(text)
        run_background(lambda: Path(path).read_text(encoding='utf-8-sig'), received)

    def open_folder(self):
        self.window.open_folder_path(self.destination.text(), "open_folder")

    def retranslate(self):
        self.update_import_tooltips()
        self.update_file_state()


class HardwareSignals(QObject):
    finished = Signal(str, list)


class RuntimeLinkSignals(QObject):
    resolved = Signal(str)


class RuntimeLink(QRunnable):
    def __init__(self, dependency):
        super().__init__()
        self.dependency = dependency
        self.signals = RuntimeLinkSignals()

    def run(self):
        if __package__:
            from . import engine_update as updates
        else:
            import engine_update as updates
        urls = {"vc": f"https://aka.ms/vs/17/release/vc_redist.{updates.SLUG.split('-')[-1]}.exe",
                "office": "https://www.libreoffice.org/download/download-libreoffice/",
                "ffmpeg": "https://ffmpeg.org/download.html",
                "repair": "https://github.com/xiaofa520/Formix/releases/latest"}
        url = urls[self.dependency]
        try:
            if self.dependency == "office" and not sys.platform.startswith("linux"):
                url = updates.office_release()["url"]
            elif self.dependency == "repair":
                url = updates.latest(for_repair=True)["url"]
        except Exception:
            pass  # A platform-specific installer may not be published yet.
        self.signals.resolved.emit(url)


class HardwareRead(QRunnable):
    def __init__(self):
        super().__init__()
        self.signals = HardwareSignals()

    def run(self):
        self.signals.finished.emit(*hardware_names())


class BackgroundSignals(QObject):
    loaded = Signal(QImage)


class BackgroundLoad(QRunnable):
    def __init__(self, path, cache_dir):
        super().__init__()
        self.path = path
        self.cache_dir = Path(cache_dir)
        self.cached_path = ""
        self.cache_error = None
        self.signals = BackgroundSignals()

    def run(self):
        reader = QImageReader(self.path)
        reader.setAutoTransform(True)
        size = reader.size()
        if max(size.width(), size.height()) > 2560:
            reader.setScaledSize(size.scaled(2560, 2560, Qt.AspectRatioMode.KeepAspectRatio))
        image = reader.read()
        if not image.isNull():
            extension = Path(self.path).suffix.lower()
            destination = self.cache_dir / ("wallpaper" + extension)
            temporary = self.cache_dir / (".wallpaper" + extension + ".tmp")
            try:
                self.cache_dir.mkdir(parents=True, exist_ok=True)
                if Path(self.path).resolve() == destination.resolve():
                    self.cached_path = str(destination)
                else:
                    shutil.copyfile(self.path, temporary)
                    os.replace(temporary, destination)
                    self.cached_path = str(destination)
                for old in self.cache_dir.glob("wallpaper*"):
                    if old != destination and old.is_file():
                        old.unlink(missing_ok=True)
            except OSError as error:
                self.cache_error = error
                try:
                    temporary.unlink(missing_ok=True)
                except OSError:
                    pass
        self.signals.loaded.emit(image)


class Window(QMainWindow):
    def __init__(self, language=None, *, startup_checks=True):
        super().__init__()
        self.language = language or LanguageManager()
        self._ocr_model_download_context = False
        self.hardware_video_encoders = {}
        self.hardware_ffmpeg = None
        self.hardware_probe = None
        self.hardware_probe_timeout = QTimer(self)
        self.hardware_probe_timeout.setSingleShot(True)
        self.hardware_probe_timeout.setInterval(3000)
        self.hardware_probe_timeout.timeout.connect(self.stop_hardware_probe)
        self.hardware_candidates = []
        self.hardware_candidate_index = 0
        self.setWindowTitle(self.t("app_name"))
        self.resize(1180, 780)
        self.setMinimumSize(920, 620)
        app_data = QStandardPaths.writableLocation(QStandardPaths.StandardLocation.AppLocalDataLocation)
        active = self.language.settings.value("pdf/model", "", type=str)
        available_model_ram = available_system_memory_gib()
        recommended_model = recommended_pdf_model(available_model_ram)
        preferred_model_root = ROOT / "models"
        legacy_model_root = Path(app_data) / "models"
        try:
            preferred_model_root.mkdir(parents=True, exist_ok=True)
            probe = preferred_model_root / f".write-check-{os.getpid()}"
            probe.write_bytes(b"")
            probe.unlink()
            has_legacy_model = any((legacy_model_root / key / "READY").is_file() for key in MODEL_REPOS)
            has_root_model = any((preferred_model_root / key / "READY").is_file() for key in MODEL_REPOS)
            self.model_root = legacy_model_root if has_legacy_model and not has_root_model else preferred_model_root
        except OSError:
            self.model_root = legacy_model_root
        if active not in MODEL_REPOS:
            layout_priority = (
                "dots-ocr", "paddleocr-vl-1.6", "glm-ocr",
                "granite-docling-258m", "smoldocling", "smolvlm-500m", "pp-ocrv5-mobile",
            )
            active = next((key for key in layout_priority
                           if key in MODEL_PROFILES
                           and MODEL_PROFILES[key]["min_available_ram_gib"] <= available_model_ram
                           and (self.model_root / key / "READY").is_file()), recommended_model)
        self.models = self.model_root / active
        self.tasks = TaskService(self.models, self)
        self.tasks.runtime_missing.connect(self.prompt_runtime)
        settings = self.language.settings
        saved_pending = settings.value("tasks/pending", "", type=str)
        try:
            pending_rows = json.loads(saved_pending)
            self.has_recovery_snapshot = isinstance(pending_rows, list) and bool(pending_rows)
        except (TypeError, ValueError):
            self.has_recovery_snapshot = False
        saved_results = settings.value("tasks/results", "", type=str) if self.has_recovery_snapshot else ""
        if not self.has_recovery_snapshot:
            settings.remove("tasks/results")
        if saved_results:
            try:
                restored_results = json.loads(saved_results)
                if isinstance(restored_results, dict):
                    self.tasks.results.update({key: int(value) for key, value in restored_results.items()
                                               if key in {"file_done", "conversion_failed", "task_cancelled"}
                                               and isinstance(value, int) and value > 0})
            except (ValueError, TypeError):
                pass
        self.recovery_timer = QTimer(self)
        self.recovery_timer.setSingleShot(True)
        self.recovery_timer.setInterval(700)
        self.recovery_timer.timeout.connect(self.save_recovery_state)
        self.closing = False
        self.task_busy = False
        self.default_output = self.make_default_output_directory()

        canvas = BackgroundCanvas()
        self.canvas = canvas
        self.contrast_timer = QTimer(self)
        self.contrast_timer.setSingleShot(True)
        self.contrast_timer.setInterval(35)
        self.contrast_timer.timeout.connect(self.refresh_contrast)
        canvas.changed.connect(self.contrast_timer.start)
        canvas.setObjectName("canvas")
        self.setCentralWidget(canvas)
        shell = QHBoxLayout(canvas)
        shell.setContentsMargins(0, 0, 0, 0)
        shell.setSpacing(0)

        sidebar = SidebarGlass()
        self.sidebar = sidebar
        sidebar.setObjectName("sidebar")
        sidebar.setFixedWidth(224)
        side = QVBoxLayout(sidebar)
        side.setContentsMargins(18, 18, 16, 16)
        side.setSpacing(7)
        brand = QHBoxLayout()
        logo = QLabel()
        logo.setObjectName("brandLogo")
        logo.setFixedSize(42, 42)
        logo_path = Path(__file__).with_name("assets") / "logo1.png"
        logo.setPixmap(QIcon(str(logo_path)).pixmap(QSize(42, 42)))
        wordmark = QVBoxLayout()
        wordmark.setSpacing(1)
        name = self.language.bind(QLabel(), "app_name")
        name.setObjectName("brand")
        wordmark.addWidget(name)
        self.app_update_available = False
        self.brand_version = QLabel(f"v{app_version()}")
        self.brand_version.setObjectName("brandVersion")
        wordmark.addWidget(self.brand_version)
        brand.addWidget(logo)
        brand.addLayout(wordmark)
        brand.addStretch()
        side.addLayout(brand)
        side.addSpacing(15)
        categories = QGridLayout()
        categories.setSpacing(4)
        categories.setColumnStretch(0, 1)
        categories.setColumnStretch(1, 1)
        side.addLayout(categories)
        side.addSpacing(4)
        self.category_buttons = QButtonGroup(self)
        self.category_tools = QStackedWidget()
        side.addWidget(self.category_tools)
        self.page_buttons = QButtonGroup(self)
        self.stack = QStackedWidget()
        self.pages = []
        groups = [
            ("group_video", ["视频转换", "M3U8 合成", "视频压缩", "音视频合并", "音视频分离"]),
            ("group_audio", ["音频转换", "音频压缩"]),
            ("group_images", ["图片转换", "图片压缩"]),
            ("group_documents", ["文档转换", "PDF 转换", "图片提取文字"]),
        ]
        self.drop_routes = {}
        self.page_categories = {}
        for category_index, (group, names) in enumerate(groups):
            button = self.language.bind(QPushButton(), group)
            button.setObjectName("navCategory")
            button.setCheckable(True)
            self.category_buttons.addButton(button, category_index)
            categories.addWidget(button, category_index // 2, category_index % 2)

            tools_panel = QWidget()
            items = QVBoxLayout(tools_panel)
            items.setContentsMargins(0, 0, 0, 0)
            items.setSpacing(2)
            for label in names:
                page = ToolPage(label, self)
                self.pages.append(page)
                self.page_categories[page] = category_index
                for extension in INPUT_TYPES[label]:
                    self.drop_routes.setdefault(extension, page)
                index = self.stack.addWidget(page)
                items.addWidget(self.make_page_button(label, index))
            items.addStretch(1)
            self.category_tools.addWidget(tools_panel)
        self.category_timer = connect_navigation(self.category_buttons, self.category_tools)
        self.category_tools.currentChanged.connect(lambda _: self.contrast_timer.start())
        self.category_buttons.button(0).setChecked(True)
        side.addStretch(1)
        side.addWidget(self.make_page_button("设置", self.stack.count()))
        shell.addWidget(sidebar)

        main = QVBoxLayout()
        main.setContentsMargins(22, 16, 22, 16)
        main.setSpacing(12)
        shell.addLayout(main, 1)
        self.top_bar = QFrame()
        self.top_bar.setObjectName("topBar")
        top = QHBoxLayout(self.top_bar)
        top.setContentsMargins(12, 6, 8, 6)
        self.page_title = QLabel()
        self.page_title.setObjectName("pageTitle")
        top.addWidget(self.page_title)
        top.addStretch()
        self.task_badge = GlassFrame(9)
        self.task_badge.setObjectName("taskBadge")
        self.task_badge.setFixedWidth(70)
        self.task_badge.setFixedHeight(36)
        self.task_badge_width = 70
        self.queue_summary_expired = False
        self.queue_result_timer = QTimer(self)
        self.queue_result_timer.setSingleShot(True)
        self.queue_result_timer.setInterval(30_000)
        self.queue_result_timer.timeout.connect(self.expire_queue_summary)
        self.repeat_conversion_timer = QTimer(self)
        self.repeat_conversion_timer.setSingleShot(True)
        self.repeat_conversion_timer.setInterval(3_000)
        self.repeat_conversion_timer.timeout.connect(self.enable_completed_files_for_repeat)
        self.task_badge_animation = QVariantAnimation(self)
        self.task_badge_animation.setDuration(360)
        self.task_badge_animation.setEasingCurve(QEasingCurve.Type.InOutCubic)
        self.task_badge_animation.valueChanged.connect(
            lambda width: self.task_badge.setFixedWidth(int(width))
        )
        self.task_badge_layout = QHBoxLayout(self.task_badge)
        self.task_badge_layout.setContentsMargins(8, 5, 8, 5)
        self.task_badge_layout.setSpacing(8)
        self.task_status_group = QWidget(self.task_badge)
        status_layout = QHBoxLayout(self.task_status_group)
        status_layout.setContentsMargins(0, 0, 0, 0)
        status_layout.setSpacing(6)
        task_icon = QLabel()
        task_icon.setObjectName("taskIndicator")
        status_icon = Path(__file__).with_name("assets") / "icons" / "status.svg"
        task_icon.setPixmap(QIcon(str(status_icon)).pixmap(QSize(10, 10)))
        task_icon.setFixedWidth(10)
        status_layout.addWidget(task_icon)
        self.queue_label = QueueStatusLabel(self.t("queue_empty"))
        self.queue_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        status_layout.addWidget(self.queue_label, 1)
        self.task_badge_layout.addWidget(self.task_status_group)
        self.progress_detail = ""
        self.progress = TaskProgressBar()
        self.progress.setObjectName("taskProgress")
        self.progress.setRange(0, 100)
        self.progress.setTextVisible(False)
        self.progress.setFixedWidth(76)
        self.progress.setFixedHeight(5)
        self.progress.hide()
        self.task_badge_layout.addWidget(self.progress)
        self.cancel = QPushButton()
        self.cancel.setObjectName("taskCancel")
        self.cancel.setProperty("glyph", "x.svg")
        self.cancel.setIcon(QIcon(str(Path(__file__).with_name("assets") / "icons" / "x.svg")))
        self.cancel.setIconSize(QSize(13, 13))
        self.cancel.setFixedSize(26, 26)
        connect_action(self.cancel, self.tasks.stop)
        self.cancel.setToolTip(self.t("cancel"))
        self.cancel.setAccessibleName(self.t("cancel"))
        self.cancel.hide()
        self.task_badge_layout.addWidget(self.cancel)
        top.addWidget(self.task_badge)

        self.platform_badge = GlassFrame(9)
        self.platform_badge.setObjectName("platformBadge")
        self.platform_badge.setFixedHeight(36)
        badge_layout = QHBoxLayout(self.platform_badge)
        badge_layout.setContentsMargins(10, 5, 11, 5)
        badge_layout.setSpacing(7)
        platform_icon = QLabel()
        platform_icon.setProperty("glyph", "monitor.svg")
        platform_icon.setPixmap(QIcon(str(Path(__file__).with_name("assets") / "icons" / "monitor.svg")).pixmap(QSize(14, 14)))
        badge_layout.addWidget(platform_icon)
        platform_label = QLabel(self.platform_name())
        platform_label.setObjectName("platformLabel")
        badge_layout.addWidget(platform_label)
        top.addWidget(self.platform_badge)
        appearance_glass = GlassFrame(10)
        appearance_glass.setFixedSize(36, 36)
        appearance_layout = QHBoxLayout(appearance_glass)
        appearance_layout.setContentsMargins(0, 0, 0, 0)
        self.appearance_button = QPushButton()
        self.appearance_button.setObjectName("appearance")
        self.appearance_button.setFocusPolicy(Qt.FocusPolicy.TabFocus)
        self.appearance_button.setFixedSize(32, 32)
        self.appearance_button.setIconSize(QSize(15, 15))
        self.icon_transition = QPropertyAnimation(self.appearance_button, b"iconSize", self)
        self.icon_transition.setDuration(220)
        self.icon_transition.setStartValue(QSize(11, 11))
        self.icon_transition.setEndValue(self.appearance_button.iconSize())
        self.icon_transition.setEasingCurve(QEasingCurve.Type.OutCubic)
        self.appearance_button.clicked.connect(self.cycle_appearance)
        appearance_layout.addWidget(self.appearance_button)
        top.addWidget(appearance_glass)
        self.header_shadows = []
        for badge in (self.task_badge, self.platform_badge, appearance_glass):
            shadow = QGraphicsDropShadowEffect(badge)
            shadow.setBlurRadius(8)
            shadow.setOffset(0, 2)
            badge.setGraphicsEffect(shadow)
            self.header_shadows.append(shadow)
        self.make_header_toast()
        self.build_drop_feedback()
        self.drop_scans = {}
        self.pending_drop_navigation = None
        self.setAcceptDrops(True)
        self.installEventFilter(self)
        for child in self.canvas.findChildren(QWidget):
            if child.acceptDrops():
                child.installEventFilter(self)
        main.addWidget(self.top_bar)
        self.workspace = QWidget()
        workspace_layout = QVBoxLayout(self.workspace)
        workspace_layout.setContentsMargins(0, 0, 0, 0)
        workspace_layout.setSpacing(main.spacing())
        main.addWidget(self.workspace, 1)
        workspace_layout.addWidget(self.stack, 1)
        self.settings_page = self.make_settings_page()
        self.background_task = None
        saved_image = self.language.settings.value("interface/background", "", type=str)
        if saved_image:
            self.load_background(saved_image, restoring=True)
        settings_scroll = SettingsScrollArea()
        self.settings_scroll = settings_scroll
        settings_scroll.setObjectName("settingsScroll")
        settings_scroll.setWidgetResizable(True)
        settings_scroll.verticalScrollBar().valueChanged.connect(lambda _: self.contrast_timer.start())
        settings_scroll.setWidget(self.settings_page)
        for combo in self.settings_page.findChildren(Dropdown):
            combo.setProperty("pageScroll", True)
        self.stack.addWidget(settings_scroll)
        self.stack.currentChanged.connect(self.restore_pdf_model_selection)
        self.settings_index = self.stack.count() - 1
        self.log_panel = self.make_log_panel()
        self.log_views["__model_download__"] = self.model_download_log
        workspace_layout.addWidget(self.log_panel)
        self.restore_logs()
        self.theme_overlay = RadialReveal(canvas, 760)
        self.pending_system_scheme = None
        self.icon_transition.finished.connect(self.finish_appearance_transition)
        self.theme_overlay.animation.finished.connect(self.finish_appearance_transition)
        self.notes_open_timer = QTimer(self)
        self.notes_open_timer.setSingleShot(True)
        self.notes_open_timer.setInterval(200)
        self.notes_open_timer.timeout.connect(self.load_release_notes)
        self.stack.currentChanged.connect(self.on_page_changed)
        self.navigation_timer = connect_navigation(self.page_buttons, self.stack)
        self.page_buttons.button(self.stack.currentIndex()).setChecked(True)

        self.tasks.message.connect(self.task_badge.setToolTip)
        self.tasks.log.connect(self.append_log)
        self.tasks.live_log.connect(self.update_live_log)
        self.model_stage = None
        self.tasks.model_stage_changed.connect(self.show_model_stage)
        self.tasks.progress.connect(self.on_task_progress)
        self.tasks.progress_time.connect(self.on_progress_time)
        self.tasks.file_status.connect(self.on_file_status)
        self.tasks.paused_changed.connect(self.on_paused_changed)
        self.tasks.busy.connect(self.on_busy_changed)
        self.tasks.busy.connect(self.on_task_busy_changed)
        self.tasks.stopped.connect(self.close, Qt.ConnectionType.QueuedConnection)
        self.close_poll = QTimer(self)
        self.close_poll.setInterval(30)
        self.close_poll.timeout.connect(self.close)
        self.language.changed.connect(self.retranslate)
        self.appearance = self.language.settings.value("interface/appearance", "auto", type=str)
        if self.appearance not in ("auto", "light", "dark"):
            self.appearance = "auto"
        QApplication.styleHints().colorSchemeChanged.connect(self.refresh_appearance)
        self.refresh_appearance()
        self.update_appearance_icon()
        self.refresh_model_state()
        self.retranslate()
        if startup_checks:
            self.tasks.checking_engines.update(("ffmpeg", "libvips", "pdf", "libreoffice"))
        self.runtime_manual = set()
        self.runtime_errors = []
        self.runtime_check = QProcess(self)
        self.runtime_check.setProgram(sys.executable)
        self.runtime_check.setArguments(["-X", "utf8", str(Path(__file__).with_name("runtime_check.py"))])
        self.runtime_check.readyReadStandardOutput.connect(self.read_runtime_check)
        self.runtime_check.finished.connect(self.finish_runtime_check)
        self.runtime_check.errorOccurred.connect(self.runtime_check_error)
        if startup_checks:
            QTimer.singleShot(0, self, self.runtime_check.start)
        self.startup_updates = [row for row in self.update_rows
                                if row.component != "app" and row.check_on_startup()]
        if startup_checks and self.can_auto_check_app_update():
            self.startup_updates.append(self.app_update_row)
        QTimer.singleShot(0, self, self.restore_pending_jobs)

    def can_auto_check_app_update(self):
        settings = self.language.settings
        now = QDateTime.currentDateTime()
        today = now.date().toString(Qt.DateFormat.ISODate)
        saved_day = settings.value("updates/appAutoCheck/day", "", type=str)
        count = settings.value("updates/appAutoCheck/count", 0, type=int) if saved_day == today else 0
        last = settings.value("updates/appAutoCheck/last", 0, type=int)
        return count < 5 and now.toSecsSinceEpoch() - last >= 3600

    def record_auto_app_check(self):
        if not self.can_auto_check_app_update():
            return False
        settings = self.language.settings
        now = QDateTime.currentDateTime()
        today = now.date().toString(Qt.DateFormat.ISODate)
        saved_day = settings.value("updates/appAutoCheck/day", "", type=str)
        count = settings.value("updates/appAutoCheck/count", 0, type=int) if saved_day == today else 0
        settings.setValue("updates/appAutoCheck/day", today)
        settings.setValue("updates/appAutoCheck/count", count + 1)
        settings.setValue("updates/appAutoCheck/last", now.toSecsSinceEpoch())
        settings.sync()
        return True

    def update_brand_version_status(self, available):
        self.app_update_available = bool(available)
        version = f"v{app_version()}"
        if self.app_update_available:
            version += f" · {self.t('update_available_short')}"
        self.brand_version.setText(version)
        self.brand_version.setProperty("updateAvailable", self.app_update_available)
        self.brand_version.style().unpolish(self.brand_version)
        self.brand_version.style().polish(self.brand_version)

    def read_runtime_check(self):
        while self.runtime_check.canReadLine():
            record = json.loads(bytes(self.runtime_check.readLine()))
            name = record["component"]
            row = next((r for r in self.update_rows if r.component == name), None)
            if record.get("preparing"):
                if row:
                    row.set_note("runtime_preparing")
                continue
            self.tasks.checking_engines.discard(name)
            if self.closing:
                continue
            if record.get("manual"):
                if record["manual"] not in self.runtime_manual:
                    self.runtime_manual.add(record["manual"])
                    self.prompt_runtime(record["manual"])
            elif record.get("error"):
                self.runtime_errors.append(f"{name}: {record['error']}")
                if row:
                    row.set_note("runtime_failed", reason=record["error"])
            elif name == "ffmpeg":
                self.probe_video_hardware()
            elif name == "libvips":
                self.set_image_formats(record.get("image_formats", []))
            if row and row.note_state and row.note_state[0] == "runtime_preparing":
                row.set_note("runtime_ready" if not record.get("manual") else "runtime_title")
            self.tasks.next_job()

    def set_image_formats(self, formats):
        self.image_formats = set(formats)
        for page in self.pages:
            if page.name == "图片转换":
                page.update_file_state()

    def refresh_image_formats(self):
        if __package__:
            from .runtime_check import check
        else:
            from runtime_check import check

        def finished(result, error):
            if not self.closing:
                self.set_image_formats(result.get("image_formats", []) if not error else
                                       set(PAGES["图片转换"]) - {"heic", "avif"})

        run_background(lambda: check("libvips"), finished)

    def runtime_check_error(self, error):
        if error == QProcess.ProcessError.FailedToStart:
            self.finish_runtime_check(1)

    def finish_runtime_check(self, code, *_):
        self.read_runtime_check()
        self.tasks.checking_engines.clear()
        if self.closing:
            return
        if code:
            detail = bytes(self.runtime_check.readAllStandardError()).decode(errors="replace").strip()
            self.runtime_errors.append(detail[-600:] or self.runtime_check.errorString())
        if self.runtime_errors:
            box = QMessageBox(QMessageBox.Warning, self.t("runtime_title"),
                              self.t("runtime_failed", reason="\n".join(self.runtime_errors)), parent=self)
            box.setAttribute(Qt.WA_DeleteOnClose)
            box.open()
        self.tasks.next_job()

    def probe_video_hardware(self):
        try:
            ffmpeg = executable("ffmpeg")
        except (OSError, RuntimeError):
            return
        if not ffmpeg:
            return
        self.hardware_ffmpeg = ffmpeg
        self.hardware_probe = QProcess(self)
        self.hardware_probe.finished.connect(self.video_encoder_list_finished)
        self.hardware_probe.errorOccurred.connect(
            lambda error: self.video_encoder_list_finished(1)
            if error == QProcess.ProcessError.FailedToStart else None
        )
        self.hardware_probe.start(ffmpeg, ["-hide_banner", "-encoders"])
        self.hardware_probe_timeout.start()

    def stop_hardware_probe(self):
        if self.hardware_probe and self.hardware_probe.state() != QProcess.ProcessState.NotRunning:
            self.hardware_probe.kill()

    def video_encoder_list_finished(self, code, *_):
        process = self.hardware_probe
        self.hardware_probe = None
        self.hardware_probe_timeout.stop()
        if process is None:
            return
        output = bytes(process.readAllStandardOutput()).decode("utf-8", "replace")
        output += bytes(process.readAllStandardError()).decode("utf-8", "replace")
        process.deleteLater()
        if code or self.closing:
            return
        available = set(re.findall(r"\b(?:h264_(?:nvenc|qsv|amf|videotoolbox|vaapi)|vp9_(?:qsv|vaapi))\b", output))
        priority = {
            "Windows": ("h264_nvenc", "h264_qsv", "h264_amf", "vp9_qsv"),
            "Darwin": ("h264_videotoolbox", "h264_qsv", "vp9_qsv"),
            "Linux": ("h264_nvenc", "h264_qsv", "h264_amf", "h264_vaapi", "vp9_qsv", "vp9_vaapi"),
        }.get(platform.system(), ())
        self.hardware_candidates = []
        for encoder in priority:
            if encoder not in available:
                continue
            if encoder.endswith("_vaapi"):
                self.hardware_candidates.extend((encoder, str(device))
                                                 for device in sorted(Path("/dev/dri").glob("renderD*")))
            else:
                self.hardware_candidates.append((encoder, None))
        self.hardware_candidate_index = 0
        self.probe_next_video_encoder()

    def probe_next_video_encoder(self):
        while self.hardware_candidate_index < len(self.hardware_candidates):
            candidate = self.hardware_candidates[self.hardware_candidate_index][0]
            codec = "vp9" if candidate.startswith("vp9_") else "h264"
            if codec not in self.hardware_video_encoders:
                break
            self.hardware_candidate_index += 1
        if self.closing or self.hardware_candidate_index >= len(self.hardware_candidates):
            return
        encoder, device = self.hardware_candidates[self.hardware_candidate_index]
        process = QProcess(self)
        self.hardware_probe = process
        process.finished.connect(lambda code, *_: self.video_encoder_probe_finished(encoder, device, code))
        process.errorOccurred.connect(
            lambda error: self.video_encoder_probe_finished(encoder, device, 1)
            if error == QProcess.ProcessError.FailedToStart else None
        )
        args = ["-hide_banner", "-loglevel", "error"]
        if encoder.endswith("_vaapi"):
            args += ["-vaapi_device", device]
        args += ["-f", "lavfi", "-i", "color=c=black:s=64x64:d=0.1"]
        if encoder.endswith("_vaapi"):
            args += ["-vf", "format=nv12,hwupload"]
        args += ["-frames:v", "1", "-an", "-c:v", encoder, "-f", "null", "-"]
        process.start(self.hardware_ffmpeg, args)
        self.hardware_probe_timeout.start()

    def video_encoder_probe_finished(self, encoder, device, code):
        process = self.hardware_probe
        self.hardware_probe = None
        self.hardware_probe_timeout.stop()
        if process is None:
            return
        process.readAllStandardOutput()
        process.readAllStandardError()
        process.deleteLater()
        if code == 0 and not self.closing:
            codec = "vp9" if encoder.startswith("vp9_") else "h264"
            self.hardware_video_encoders[codec] = (encoder, device)
        self.hardware_candidate_index += 1
        self.probe_next_video_encoder()

    def check_next_startup_update(self):
        while not self.closing and self.startup_updates:
            row = self.startup_updates.pop(0)
            if row.component == "app" and not self.record_auto_app_check():
                continue
            row.check(startup=True)
            return

    def build_drop_feedback(self):
        self.drop_overlay = QFrame(self.canvas)
        self.drop_overlay.setObjectName("dragOverlay")
        self.drop_overlay.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        overlay_layout = QVBoxLayout(self.drop_overlay)
        overlay_layout.setContentsMargins(24, 24, 24, 24)
        overlay_layout.addStretch(1)
        prompt = QFrame()
        prompt.setObjectName("dragPrompt")
        prompt_layout = QVBoxLayout(prompt)
        prompt_layout.setContentsMargins(30, 24, 30, 24)
        prompt_layout.setSpacing(8)
        icon = QLabel()
        icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon.setPixmap(QIcon(str(Path(__file__).with_name("assets") / "icons" / "plus.svg")).pixmap(QSize(32, 32)))
        prompt_layout.addWidget(icon)
        self.drop_ready = self.language.bind(QLabel(), "drop_ready")
        self.drop_ready.setObjectName("dropReady")
        self.drop_ready.setAlignment(Qt.AlignmentFlag.AlignCenter)
        prompt_layout.addWidget(self.drop_ready)
        self.drop_ready_hint = self.language.bind(QLabel(), "drop_ready_hint")
        self.drop_ready_hint.setObjectName("emptyHint")
        self.drop_ready_hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        prompt_layout.addWidget(self.drop_ready_hint)
        overlay_layout.addWidget(prompt, 0, Qt.AlignmentFlag.AlignCenter)
        overlay_layout.addStretch(1)
        self.drop_effect = QGraphicsOpacityEffect(self.drop_overlay)
        self.drop_effect.setOpacity(0)
        self.drop_overlay.setGraphicsEffect(self.drop_effect)
        self.drop_animation = QPropertyAnimation(self.drop_effect, b"opacity", self)
        self.drop_animation.setDuration(180)
        self.drop_animation.setEasingCurve(QEasingCurve.Type.OutCubic)
        self.drop_animation.finished.connect(self.hide_faded_feedback)
        self.drop_overlay.hide()

        self.drag_leave_timer = QTimer(self)
        self.drag_leave_timer.setSingleShot(True)
        self.drag_leave_timer.setInterval(120)
        self.drag_leave_timer.timeout.connect(self.hide_drop_overlay)

    def show_drop_overlay(self):
        self.drag_leave_timer.stop()
        self.drop_overlay.setGeometry(self.canvas.rect())
        if self.drop_overlay.isVisible() and self.drop_animation.endValue() == 1.0:
            return
        self.drop_overlay.show()
        self.drop_overlay.raise_()
        self.drop_animation.stop()
        self.drop_animation.setStartValue(self.drop_effect.opacity())
        self.drop_animation.setEndValue(1.0)
        self.drop_animation.start()

    def hide_drop_overlay(self):
        self.drop_animation.stop()
        self.drop_animation.setStartValue(self.drop_effect.opacity())
        self.drop_animation.setEndValue(0.0)
        self.drop_animation.start()

    def hide_faded_feedback(self):
        if self.drop_effect.opacity() <= 0.01:
            self.drop_overlay.hide()

    def import_drop(self, paths):
        routes = self.drop_routes.copy()
        current = self.stack.currentWidget()
        if current in self.page_categories:
            routes.update(dict.fromkeys(INPUT_TYPES[current.name], current))
        task = FileScanTask(paths, frozenset(routes))
        self.drop_scans[task] = routes
        self.pending_drop_navigation = task
        task.signals.batch.connect(self.route_drop_batch, Qt.ConnectionType.QueuedConnection)
        task.signals.finished.connect(self.finish_drop, Qt.ConnectionType.QueuedConnection)
        QThreadPool.globalInstance().start(task)

    def route_drop_batch(self, task, entries):
        try:
            if self.closing or task.cancelled.is_set():
                return
            grouped = {}
            for entry in entries:
                page = self.drop_scans[task].get(Path(entry[1]).suffix.lower())
                if page is not None:
                    grouped.setdefault(page, []).append(entry)
            for page, files in grouped.items():
                task.added_count += page.files.append_batch(files)
                if task is self.pending_drop_navigation:
                    self.pending_drop_navigation = None
                    category = self.page_categories[page]
                    self.category_buttons.button(category).setChecked(True)
                    self.category_tools.setCurrentIndex(category)
                    self.page_buttons.button(self.stack.indexOf(page)).setChecked(True)
                    self.stack.setCurrentWidget(page)
        finally:
            task.slots.release()

    def finish_drop(self, task, skipped, error):
        self.drop_scans.pop(task, None)
        if task is self.pending_drop_navigation:
            self.pending_drop_navigation = None
        if self.closing:
            return
        if error:
            QMessageBox.warning(self, self.t("add_files"), error)
        if skipped:
            self.show_header_message(self.t("drop_summary", count=task.added_count, skipped=skipped))
        elif task.added_count:
            self.show_drop_toast(task.added_count)

    def make_header_toast(self):
        self.drop_toast = QFrame(self.top_bar)
        self.drop_toast.setObjectName("dropToast")
        self.drop_toast.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        toast_layout = QHBoxLayout(self.drop_toast)
        toast_layout.setContentsMargins(10, 2, 10, 2)
        toast_layout.setSpacing(9)
        toast_icon = QLabel()
        toast_icon.setPixmap(QIcon(str(Path(__file__).with_name("assets") / "icons" / "circle-check.svg")).pixmap(QSize(18, 18)))
        toast_layout.addWidget(toast_icon)
        self.drop_toast_text = QLabel()
        self.drop_toast_text.setObjectName("dropToastText")
        toast_layout.addWidget(self.drop_toast_text)
        self.drop_toast.setFixedHeight(30)
        self.toast_effect = QGraphicsOpacityEffect(self.drop_toast)
        self.toast_effect.setOpacity(0)
        self.drop_toast.setGraphicsEffect(self.toast_effect)
        self.toast_animation = QPropertyAnimation(self.toast_effect, b"opacity", self)
        self.toast_animation.setDuration(180)
        self.toast_animation.setEasingCurve(QEasingCurve.Type.OutCubic)
        self.toast_animation.finished.connect(self.hide_faded_toast)
        self.toast_timer = QTimer(self)
        self.toast_timer.setSingleShot(True)
        self.toast_timer.setInterval(1500)
        self.toast_timer.timeout.connect(self.fade_out_toast)
        self.drop_toast.hide()
        self.toast_message = ""
        self.top_bar.installEventFilter(self)

    def position_header_toast(self):
        bar = self.top_bar
        left = self.page_title.geometry().right() + 8
        right = self.task_badge.geometry().left() - 8
        available = max(0, right - left)
        metrics = self.drop_toast_text.fontMetrics()
        chrome = 47  # horizontal margins, icon, and spacing
        width = min(available, metrics.horizontalAdvance(self.toast_message) + chrome + 4)
        self.drop_toast_text.setText(metrics.elidedText(self.toast_message, Qt.ElideRight, max(0, width - chrome)))
        x = max(left, min((bar.width() - width) // 2, right - width))
        self.drop_toast.setGeometry(x, (bar.height() - 30) // 2, width, 30)

    def eventFilter(self, watched, event):
        kind = event.type()
        if kind in (QEvent.DragEnter, QEvent.DragMove, QEvent.Drop):
            urls = event.mimeData().urls()
            if any(url.isLocalFile() for url in urls):
                if kind == QEvent.Drop:
                    self.drag_leave_timer.stop()
                    self.hide_drop_overlay()
                    self.import_drop([url.toLocalFile() for url in urls if url.isLocalFile()])
                elif kind == QEvent.DragEnter:
                    self.show_drop_overlay()
                event.setDropAction(Qt.CopyAction)
                event.accept()
                return True
        elif kind == QEvent.DragLeave and self.drop_overlay.isVisible():
            self.drag_leave_timer.start()
            event.accept()
            return True
        if watched is getattr(self, "top_bar", None) and event.type() in (QEvent.Resize, QEvent.LayoutRequest):
            if self.drop_toast.isVisible():
                QTimer.singleShot(0, self, self.position_header_toast)
        return super().eventFilter(watched, event)

    def hide_faded_toast(self):
        if self.toast_effect.opacity() <= 0.01:
            self.drop_toast.hide()

    def show_drop_toast(self, count):
        self.show_header_message(self.t("drop_added", count=count))

    def show_header_message(self, message):
        self.toast_message = message
        self.drop_toast.setToolTip(message)
        self.position_header_toast()
        self.drop_toast.show()
        self.drop_toast.raise_()
        self.toast_timer.stop()
        self.toast_animation.stop()
        self.toast_animation.setStartValue(self.toast_effect.opacity())
        self.toast_animation.setEndValue(1.0)
        self.toast_animation.start()
        self.toast_timer.start()

    def fade_out_toast(self):
        self.toast_animation.stop()
        self.toast_animation.setStartValue(self.toast_effect.opacity())
        self.toast_animation.setEndValue(0.0)
        self.toast_animation.start()

    def make_log_panel(self):
        panel = GlassFrame(16)
        panel.setObjectName("logPanel")
        panel.setMinimumHeight(112)
        panel.setMaximumHeight(176)
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(15, 10, 15, 11)
        layout.setSpacing(7)
        header = QHBoxLayout()
        title = self.language.bind(QLabel(), "log_title")
        title.setObjectName("logTitle")
        header.addWidget(title)
        header.addStretch(1)
        self.log_buttons = []
        for key, action, icon in (("log_export", self.export_log, "download.svg"),
                                  ("log_copy_errors", self.copy_error_log, "copy.svg"),
                                  ("log_clear", self.clear_log, "trash.svg")):
            button = make_button(self.language, key, action, icon=icon)
            button.setObjectName("logAction")
            button.setMinimumHeight(30)
            button.setEnabled(False)
            header.addWidget(button)
            self.log_buttons.append(button)
        layout.addLayout(header)
        self.log_stack = QStackedWidget()
        self.log_views = {}
        for page in self.pages:
            view = QPlainTextEdit()
            view.setObjectName("logView")
            view.setReadOnly(True)
            view.setMaximumBlockCount(400)
            view.setPlaceholderText(self.t("log_placeholder"))
            view.textChanged.connect(self.update_log_buttons)
            view.textChanged.connect(self.schedule_recovery_save)
            self.log_stack.addWidget(view)
            self.log_views[page.name] = view
        self.log_stack.setCurrentIndex(self.stack.currentIndex())
        layout.addWidget(self.log_stack, 1)
        return panel

    def update_log_buttons(self):
        enabled = not self.log_stack.currentWidget().document().isEmpty()
        for button in self.log_buttons:
            button.setEnabled(enabled)

    def clear_log(self):
        self.log_stack.currentWidget().clear()
        self.schedule_recovery_save()

    def schedule_recovery_save(self, *_):
        if not self.closing:
            self.recovery_timer.start()

    def restore_logs(self):
        from PySide6.QtGui import QTextCursor
        settings = self.language.settings
        if not self.has_recovery_snapshot:
            settings.remove("recovery/logs")
            settings.sync()
            return
        for page_name, view in self.log_views.items():
            saved = settings.value(f"recovery/logs/{page_name}", "", type=str)
            if saved:
                view.setPlainText(saved)
                cursor = view.textCursor()
                cursor.movePosition(QTextCursor.MoveOperation.End)
                view.setTextCursor(cursor)

    def save_recovery_state(self):
        settings = self.language.settings
        jobs = list(self.tasks.queue)
        if self.tasks.active_job and not self.tasks.cancelled:
            jobs.insert(0, self.tasks.active_job)
        if jobs:
            settings.setValue("tasks/pending", json.dumps(jobs, default=str, ensure_ascii=False))
            settings.setValue("tasks/results", json.dumps(dict(self.tasks.results), ensure_ascii=False))
            for page_name, view in self.log_views.items():
                settings.setValue(f"recovery/logs/{page_name}", view.toPlainText())
            self.has_recovery_snapshot = True
        else:
            settings.remove("tasks/pending")
            settings.remove("tasks/results")
            settings.remove("recovery/logs")
            self.has_recovery_snapshot = False
        settings.sync()

    def on_task_busy_changed(self, _busy):
        self.update_queue_label()
        if _busy:
            self.schedule_recovery_save()
        elif not self.closing:
            self.save_recovery_state()

    def export_log(self):
        from PySide6.QtCore import QIODevice, QSaveFile
        content = self.log_stack.currentWidget().toPlainText()
        if not content:
            return
        stamp = QDateTime.currentDateTime().toString("yyyyMMdd-HHmmss")
        filename = f"{self.page_title.text()}-{stamp}.txt"
        path, _ = QFileDialog.getSaveFileName(self, self.t("log_export"), filename, "*.txt")
        if path:
            output = QSaveFile(path)
            data = (content + "\n").encode("utf-8")
            if not (output.open(QIODevice.OpenModeFlag.WriteOnly) and
                    output.write(data) == len(data) and output.commit()):
                QMessageBox.warning(self, self.t("log_export"), output.errorString())

    def copy_error_log(self, view=None):
        content = (view if view is not None else self.log_stack.currentWidget()).toPlainText()
        errors = [line for line in content.splitlines() if ERROR_LOG_PATTERN.search(line)]
        if not errors:
            self.show_header_message(self.t("log_no_errors"))
            return
        QApplication.clipboard().setText("\n".join(errors))
        self.show_header_message(self.t("log_errors_copied", count=len(errors)))

    def append_log(self, page_name, message):
        diagnostic_event('ui_message', page=page_name, message=str(message))
        line = str(message).strip()
        if line:
            stamp = QDateTime.currentDateTime().toString("HH:mm:ss")
            self.log_views[page_name].appendPlainText(f"[{stamp}] {line}")

    def update_live_log(self, page_name, message):
        from PySide6.QtGui import QTextCursor
        view = self.log_views[page_name]
        block = view.document().lastBlock()
        if block.userState() != 1:
            self.append_log(page_name, message)
            view.document().lastBlock().setUserState(1)
            return
        stamp = QDateTime.currentDateTime().toString("HH:mm:ss")
        cursor = QTextCursor(block)
        cursor.movePosition(QTextCursor.EndOfBlock, QTextCursor.KeepAnchor)
        cursor.insertText(f"[{stamp}] {message}")

    def on_file_status(self, name, source, key):
        for page in self.pages:
            if page.name == name:
                page.files.set_state(source, key)
                if key != "queue_processing":
                    page.update_file_actions()
                break

    def on_task_progress(self, value):
        self.progress.setValue(max(0, min(100, value)))
        self.progress_detail = f"{self.progress.value()}%" if value >= 0 else ""
        self.progress.setVisible(value >= 0 and bool(self.tasks.active_job) and not self.tasks.paused)
        self.progress.update()
        self.update_queue_label()

    def on_progress_time(self, detail):
        self.progress_detail = detail
        self.update_queue_label()

    def on_paused_changed(self, paused):
        self.progress.setVisible(bool(self.tasks.active_job) and not paused
                                 and self.progress_detail.endswith("%"))
        self.update_queue_label()
        icon = "resume.svg" if paused else "pause.svg"
        key = "resume" if paused else "pause"
        for page in self.pages:
            page.pause.setProperty("translationKey", key)
            page.pause.setText(self.t(key))
            page.pause.setProperty("glyph", icon)
            page.pause.setIcon(contrast_icon(icon, "#e0e8f2" if self.canvas.dark else "#28384b"))
            page.pause.setEnabled(self.task_busy and self.tasks.active_job is not None
                                  and page.name == self.tasks.active_job[0])

    def on_page_changed(self, index):
        self.page_title.setText(self.page_buttons.button(index).text())
        self.contrast_timer.start()
        self.log_panel.setVisible(index != self.settings_index)
        if index != self.settings_index:
            self.log_stack.setCurrentIndex(index)
            self.update_log_buttons()
        if index == self.settings_index:
            self.refresh_model_state()
            if self.hardware_info is None and self.hardware_read is None:
                self.hardware_read = HardwareRead()
                self.hardware_read.signals.finished.connect(self.hardware_loaded)
                QThreadPool.globalInstance().start(self.hardware_read)
            self.notes_open_timer.start()
        else:
            self.notes_open_timer.stop()

    @staticmethod
    def platform_name():
        import platform
        names = {"Windows": "Windows", "Darwin": "macOS", "Linux": "Linux"}
        return names.get(platform.system(), platform.system())

    @staticmethod
    def make_default_output_directory():
        if os.name == "nt" and Path("D:/").is_dir():
            target = Path("D:/格式转换通缓存")
        else:
            documents = QStandardPaths.writableLocation(QStandardPaths.StandardLocation.DocumentsLocation)
            target = Path(documents or Path.home()) / "格式转换通缓存"
        try:
            target.mkdir(parents=True, exist_ok=True)
        except OSError:
            documents = QStandardPaths.writableLocation(QStandardPaths.StandardLocation.DocumentsLocation)
            target = Path(documents or Path.home()) / "格式转换通缓存"
            try:
                target.mkdir(parents=True, exist_ok=True)
            except OSError:
                pass
        return target

    def t(self, key, **values):
        return self.language.t(key, **values)

    def prompt_runtime(self, dependency):
        names = {"vc": "Microsoft Visual C++ Redistributable", "office": "LibreOffice",
                 "ffmpeg": "FFmpeg", "repair": "Formix"}
        box = QMessageBox(self)
        box.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        box.setWindowTitle(self.t("runtime_title"))
        box.setText(self.t("runtime_prompt", name=names[dependency]))
        download = box.addButton(self.t("runtime_download"), QMessageBox.ButtonRole.AcceptRole)
        later = box.addButton(self.t("update_later"), QMessageBox.ButtonRole.RejectRole)
        box.setDefaultButton(later)
        def choose(button):
            if button == download:
                task = RuntimeLink(dependency)
                task.signals.resolved.connect(self.open_web_link)
                QThreadPool.globalInstance().start(task)
        box.buttonClicked.connect(choose)
        box.open()

    def make_page_button(self, label, index):
        key = "page_settings" if label == "设置" else PAGE_INFO[label][0]
        button = self.language.bind(QPushButton(), key)
        button.setObjectName("navPage")
        button.setProperty("glyph", PAGE_ICON[label])
        button.setIcon(contrast_icon(PAGE_ICON[label], "#f0f5fc" if self.canvas.dark else "#293748"))
        button.setIconSize(QSize(17, 17))
        button.setCheckable(True)
        self.page_buttons.addButton(button, index)
        return button

    def cycle_appearance(self):
        if not self.appearance_button.isEnabled():
            return
        self.appearance_button.setEnabled(False)
        modes = ("auto", "light", "dark")
        self.appearance = modes[(modes.index(self.appearance) + 1) % len(modes)]
        self.language.settings.setValue("interface/appearance", self.appearance)
        self.refresh_appearance(animate=self.appearance != "auto")
        self.update_appearance_icon()
        self.icon_transition.start()

    def finish_appearance_transition(self):
        if self.theme_overlay.animation.state() != QPropertyAnimation.State.Stopped or self.icon_transition.state() != QPropertyAnimation.State.Stopped:
            return
        self.appearance_button.setEnabled(True)
        if self.pending_system_scheme is not None:
            scheme = self.pending_system_scheme
            self.pending_system_scheme = None
            self.refresh_appearance(scheme)

    def refresh_appearance(self, scheme=None, *, animate=True):
        app = QApplication.instance()
        if scheme is None:
            scheme = app.styleHints().colorScheme()
        if self.appearance == "auto" and self.theme_overlay.isVisible():
            self.pending_system_scheme = scheme
            return
        system_dark = scheme == Qt.ColorScheme.Dark
        if scheme == Qt.ColorScheme.Unknown:
            system_dark = app.palette().color(QPalette.ColorRole.Window).lightness() < 128
        dark = system_dark if self.appearance == "auto" else self.appearance == "dark"
        if getattr(self, "_applied_dark", None) == dark:
            return
        previous = self.canvas.grab() if animate and self.isVisible() else None
        self._applied_dark = dark
        self.canvas.dark = dark
        shadow_color = QColor(0, 0, 0, 86) if dark else QColor(33, 49, 72, 38)
        for shadow in self.header_shadows:
            shadow.setColor(shadow_color)
        apply_theme(app, dark)
        self.contrast_timer.start()
        self.canvas.update()
        if previous is not None:
            button = self.appearance_button
            button.setEnabled(False)
            self.theme_overlay.start(button.mapTo(self.canvas, button.rect().center()), previous)

    def update_appearance_icon(self):
        icon = Path(__file__).with_name("assets") / "icons" / f"theme-{self.appearance}.svg"
        self.appearance_button.setProperty("glyph", icon.name)
        self.appearance_button.setIcon(QIcon(str(icon)))
        self.contrast_timer.start()
        self.update_appearance_label()

    def update_appearance_label(self):
        label = self.t("theme_" + self.appearance)
        self.appearance_button.setToolTip(label)
        self.appearance_button.setAccessibleName(label)

    def retranslate(self, *_):
        self.update_appearance_label()
        if hasattr(self, "brand_version"):
            self.update_brand_version_status(self.app_update_available)
        if hasattr(self, "model_folder_button"):
            self.show_model_disk_size(self.model_combo.currentData())
        self.model_link.setToolTip(self.t("model_homepage"))
        self.model_combo.setToolTip(self.t("choose_model"))
        self.model_combo.setAccessibleName(self.t("choose_model"))
        self.setWindowTitle(self.t("app_name"))
        if hasattr(self, "about_name_value"):
            self.about_name_value.setText(self.t("app_name"))
            self.about_version_value.setText("v" + app_version())
            self.about_platform_value.setText(self.platform_name())
            self.refresh_hardware_labels()
            self.about_project_link.setText(self.t("about_project"))
            self.about_project_link.setToolTip(self.t("visit_project_website", name="GitHub"))
        app = QApplication.instance()
        if app:
            app.setApplicationDisplayName(self.t("app_name"))
            self.apply_selected_font()
        self.language.retranslate(self)
        for row in self.update_rows:
            row.retranslate()
        self.page_title.setText(self.page_buttons.button(self.stack.currentIndex()).text())
        if hasattr(self, "language_combo"):
            blocked = self.language_combo.blockSignals(True)
            self.language_combo.setCurrentIndex(LANGUAGE_CODES.index(self.language.code))
            self.language_combo.blockSignals(blocked)
        for page in self.pages:
            page.retranslate()
        if hasattr(self, "log_views"):
            for view in self.log_views.values():
                view.setPlaceholderText(self.t("log_placeholder"))
            self.on_paused_changed(self.tasks.paused)
        if self.tasks.proc:
            self.task_badge.setToolTip(self.tasks.current_message())
        elif not self.tasks.queue:
            self.task_badge.setToolTip(self.t("ready"))
        self.cancel.setToolTip(self.t("cancel"))
        self.cancel.setAccessibleName(self.t("cancel"))
        self.update_queue_label()
        self.refresh_model_state()

    def make_settings_page(self):
        page = QWidget()
        root = QVBoxLayout(page)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(14)

        language_card, language_layout = card(self.language, "language_title", "language_hint")
        language_row = QHBoxLayout()
        language_icon = QLabel()
        language_icon.setProperty("glyph", "globe.svg")
        language_icon.setPixmap(QIcon(str(Path(__file__).with_name("assets") / "icons" / "globe.svg")).pixmap(QSize(16, 16)))
        language_row.addWidget(language_icon)
        language_row.addWidget(self.language.bind(QLabel(), "language_label"))
        language_row.addStretch()
        self.language_combo = Dropdown()
        self.language_combo.setFixedWidth(210)
        self.language_combo.setMinimumHeight(40)
        for code in LANGUAGE_CODES:
            self.language_combo.addItem(LANGUAGE_NAMES[code], code)
        self.language_combo.setCurrentIndex(LANGUAGE_CODES.index(self.language.code))
        self.language_combo.currentIndexChanged.connect(self.change_language)
        language_row.addWidget(self.language_combo)
        language_layout.addLayout(language_row)
        browser_row = QHBoxLayout()
        browser_label = self.language.bind(QLabel(), "web_browser")
        browser_row.addWidget(browser_label)
        browser_row.addStretch()
        self.browser_combo = Dropdown()
        self.browser_combo.setFixedSize(210, 40)
        browser_label.setBuddy(self.browser_combo)
        self.browser_combo.addItem(self.t("browser_system"), "system")
        self.browser_combo.setItemData(0, "browser_system", Qt.ItemDataRole.UserRole + 3)
        for key, (name, *_) in BROWSERS.items():
            if browser_path(key):
                self.browser_combo.addItem(name, key)
        saved = self.language.settings.value("web/browser", "system", type=str)
        self.browser_combo.setCurrentIndex(max(0, self.browser_combo.findData(saved)))
        self.browser_combo.currentIndexChanged.connect(
            lambda _: self.language.settings.setValue("web/browser", self.browser_combo.currentData()))
        browser_row.addWidget(self.browser_combo)
        language_layout.addLayout(browser_row)
        root.addWidget(language_card)

        appearance_card, appearance_layout = card(self.language, "appearance_settings")
        font_row = QHBoxLayout()
        font_label = self.language.bind(QLabel(), "interface_font")
        font_row.addWidget(font_label)
        font_row.addStretch()
        self.font_combo = SearchDropdown()
        self.font_combo.setFixedWidth(self.language_combo.width())
        self.font_combo.setMinimumHeight(self.language_combo.minimumHeight())
        self.language.bind(self.font_combo.lineEdit(), "search_fonts", "placeholder")
        font_label.setBuddy(self.font_combo)
        self.font_combo.addItem(self.t("default_font"), "")
        self.font_combo.setItemData(0, "default_font", Qt.ItemDataRole.UserRole + 3)
        for family in interface_families(self.language.settings):
            self.font_combo.addItem(family, family)
        saved_font = self.language.settings.value("interface/fontFamily", "", type=str)
        self.font_combo.setCurrentIndex(max(0, self.font_combo.findData(saved_font)))
        self.font_combo.currentIndexChanged.connect(self.change_font)
        font_row.addWidget(self.font_combo)
        appearance_layout.addLayout(font_row)
        size_row = QHBoxLayout()
        size_label = self.language.bind(QLabel(), "interface_font_size")
        size_row.addWidget(size_label)
        size_row.addStretch()
        self.font_size_combo = Dropdown()
        self.font_size_combo.setFixedSize(210, 40)
        size_label.setBuddy(self.font_size_combo)
        self.font_size_combo.addItem(self.t("auto_size"), 0)
        self.font_size_combo.setItemData(0, "auto_size", Qt.ItemDataRole.UserRole + 3)
        for size in range(11, 19):
            self.font_size_combo.addItem(f"{size} px", size)
        saved_size = self.language.settings.value("interface/fontSize", 0, type=int)
        self.font_size_combo.setCurrentIndex(max(0, self.font_size_combo.findData(saved_size)))
        self.font_size_combo.currentIndexChanged.connect(self.change_font)
        size_row.addWidget(self.font_size_combo)
        appearance_layout.addLayout(size_row)
        self.font_reload = QTimer(self)
        self.font_reload.setSingleShot(True)
        self.font_reload.timeout.connect(self.apply_selected_font)

        background_row = QHBoxLayout()
        background_row.addWidget(self.language.bind(QLabel(), "background_image"))
        background_row.addStretch()
        self.pick_background = make_button(self.language, "select_image", self.choose_background, icon="image.svg")
        self.clear_background = make_button(self.language, "default_background", self.reset_background)
        self.clear_background.setEnabled(False)
        background_row.addWidget(self.pick_background)
        background_row.addWidget(self.clear_background)
        appearance_layout.addLayout(background_row)
        self.background_effects = {}
        self.background_preview_timer = QTimer(self)
        self.background_preview_timer.setSingleShot(True)
        self.background_preview_timer.setInterval(24)
        self.background_preview_timer.timeout.connect(self.preview_background)
        for key, default_value in BACKGROUND_DEFAULTS.items():
            row = QHBoxLayout()
            label = self.language.bind(QLabel(), "background_" + key)
            row.addWidget(label)
            row.addStretch()
            slider = SettingsSlider(Qt.Orientation.Horizontal)
            slider.setFixedWidth(160)
            slider.setObjectName("backgroundSlider")
            slider.setRange(0, 100)
            slider.setTracking(True)
            label.setBuddy(slider)
            slider.setValue(self.language.settings.value("interface/background/" + key, default_value, type=int))
            slider.setEnabled(False)
            row.addWidget(slider)
            value_label = QLabel(f"{slider.value()}%")
            value_label.setMinimumWidth(44)
            value_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            row.addWidget(value_label)
            self.background_effects[key] = slider
            slider.valueChanged.connect(lambda value, k=key, label=value_label:
                                        self.change_background_effect(k, value, label))
            appearance_layout.addLayout(row)
        self.preview_background()
        root.addWidget(appearance_card)

        accel_card, accel_layout = card(self.language, "video_acceleration_title", "video_acceleration_hint")
        accel_row = QHBoxLayout()
        accel_icon = QLabel()
        accel_icon.setProperty("glyph", "monitor.svg")
        accel_icon.setPixmap(QIcon(str(Path(__file__).with_name("assets") / "icons" / "monitor.svg")).pixmap(QSize(16, 16)))
        accel_row.addWidget(accel_icon)
        accel_row.addWidget(self.language.bind(QLabel(), "video_acceleration"))
        accel_row.addStretch()
        self.video_acceleration_combo = Dropdown()
        self.video_acceleration_combo.setFixedWidth(self.language_combo.width())
        self.video_acceleration_combo.setMinimumHeight(40)
        for key, value in (("gpu_auto", "auto"), ("gpu_gpu", "gpu"), ("gpu_hybrid", "hybrid"), ("gpu_cpu", "cpu")):
            index = self.video_acceleration_combo.count()
            self.video_acceleration_combo.addItem(self.t(key), value)
            self.video_acceleration_combo.setItemData(index, key, Qt.ItemDataRole.UserRole + 3)
        saved_acceleration = self.language.settings.value("conversion/videoAcceleration", "auto", type=str)
        selected_acceleration = self.video_acceleration_combo.findData(saved_acceleration)
        self.video_acceleration_combo.setCurrentIndex(selected_acceleration if selected_acceleration >= 0 else 0)
        self.video_acceleration_combo.currentIndexChanged.connect(self.save_video_acceleration)
        accel_row.addWidget(self.video_acceleration_combo)
        accel_layout.addLayout(accel_row)
        root.addWidget(accel_card)

        model_card, model_layout = card(self.language, "model_title", "model_hint")
        model_row = QHBoxLayout()
        self.model_combo = Dropdown()
        self.model_combo.setObjectName("modelPicker")
        self.model_combo.setFixedSize(32, 32)
        for key, repo in MODEL_REPOS.items():
            if key == "deepseek-ocr" and platform.system() == "Darwin":
                continue
            if (platform.system() == "Darwin"
                    and platform.machine().lower() in {"x86_64", "amd64"}
                    and key in {"paddleocr-vl-1.6", "glm-ocr", "dots-ocr", "deepseek-ocr"}):
                continue
            if key != self.models.name and key not in {"granite-docling-258m", "smoldocling", "paddleocr-vl-1.6", "dots-ocr", "deepseek-ocr", "pp-ocrv5-mobile"} and not (self.model_root / key / "READY").is_file():
                continue
            self.model_combo.addItem(MODEL_PROFILES[key].get("label", repo.split("/")[1]), key)
            self.model_combo.setItemData(
                self.model_combo.count() - 1, self.t(f"model_desc_{key}"), Qt.ItemDataRole.ToolTipRole
            )
        selected_model_index = self.model_combo.findData(self.models.name)
        if selected_model_index < 0:
            selected_model_index = self.model_combo.findData("granite-docling-258m")
            self.models = self.model_root / "granite-docling-258m"
            self.tasks.models = self.models
        self.model_combo.setCurrentIndex(selected_model_index)
        self.model_combo.setToolTip(self.t(f"model_desc_{self.models.name}"))
        self.model_combo.view().setMinimumWidth(self.model_combo.sizeHint().width() + 20)
        self.model_link = QPushButton(self.model_combo.currentText())
        self.model_link.setObjectName("projectLink")
        self.model_link.setCursor(Qt.CursorShape.PointingHandCursor)
        connect_action(self.model_link, self.open_model_homepage)
        def fit_model_name():
            metrics = self.model_link.fontMetrics()
            longest = max((metrics.horizontalAdvance(self.model_combo.itemText(i))
                           for i in range(self.model_combo.count())), default=0)
            width = min(longest + 6, 220)
            self.model_link.setFixedWidth(width)
            self.model_link.setText(metrics.elidedText(self.model_combo.currentText(),
                                                       Qt.TextElideMode.ElideRight, width - 2))
        self.model_combo.currentTextChanged.connect(fit_model_name)
        fit_model_name()
        QTimer.singleShot(0, fit_model_name)
        def update_model_tooltips(*_):
            description = self.t(f"model_desc_{self.model_combo.currentData()}")
            self.model_combo.setToolTip(description)
            self.model_link.setToolTip(f"{description}\n{self.t('model_homepage')}")
        self.model_combo.currentIndexChanged.connect(update_model_tooltips)
        update_model_tooltips()
        model_row.addWidget(self.model_link)
        model_row.addWidget(self.model_combo)
        model_row.addStretch()
        model_layout.addLayout(model_row)
        model_status_row = QHBoxLayout()
        model_status_row.setSpacing(8)
        self.model_status_icon = QLabel()
        self.model_status_icon.setFixedSize(16, 16)
        model_status_row.addWidget(self.model_status_icon)
        self.model_status = QLabel()
        self.model_status.setObjectName("muted")
        model_status_row.addWidget(self.model_status, 1)
        self.cuda_pending = True
        self.cuda_version = None
        self.cuda_label = QLabel("CUDA · " + self.t("checking_version"))
        self.cuda_label.setObjectName("muted")
        model_status_row.addWidget(self.cuda_label)
        model_layout.addLayout(model_status_row)
        run_background(cuda_driver_version, self.cuda_detected)
        self.model_disk_size = QLabel()
        self.model_disk_size.setObjectName("muted")
        self.model_disk_size.setWordWrap(True)
        self.model_memory = QLabel()
        self.model_memory.setObjectName("muted")
        self.model_memory.setWordWrap(False)
        model_info_row = QHBoxLayout()
        model_info_row.setSpacing(16)
        self.model_disk_size.setWordWrap(False)
        model_info_row.addWidget(self.model_disk_size)
        model_info_row.addWidget(self.model_memory)
        model_info_row.addStretch(1)
        self.model_folder_button = make_button(
            self.language, "open_model_folder", self.open_model_folder, icon="folder.svg"
        )
        model_info_row.addWidget(self.model_folder_button, 0, Qt.AlignmentFlag.AlignVCenter)
        model_layout.addLayout(model_info_row)
        icons = Path(__file__).with_name("assets") / "icons"
        self.model_icons = {present: QIcon(str(icons / filename)).pixmap(QSize(16, 16))
                            for present, filename in ((True, "circle-check.svg"), (False, "circle-alert.svg"))}
        model_actions = QHBoxLayout()
        self.install_model_button = make_button(self.language, "download_model", role="logAction", icon="download.svg")
        connect_action(self.install_model_button, self.install_model)
        self.delete_model_button = make_button(self.language, "delete_model", icon="trash.svg")
        self.delete_model_button.setProperty("contentAction", True)
        connect_action(self.delete_model_button, self.remove_model)
        model_actions.addWidget(self.install_model_button)
        model_actions.addWidget(self.delete_model_button)
        model_actions.addStretch()
        model_layout.addLayout(model_actions)
        self.model_log_toggle = make_button(self.language, "model_download_log",
                                            role="logAction", icon="chevron-right.svg")
        self.model_log_toggle.setProperty("modelLogToggle", True)
        self.model_log_toggle.setMinimumHeight(28)
        self.model_log_toggle.setCheckable(True)
        self.model_log_toggle.setChecked(False)
        model_log_header = QHBoxLayout()
        model_log_header.addWidget(self.model_log_toggle)
        model_log_header.addStretch()
        model_layout.addLayout(model_log_header)
        self.model_download_log = QPlainTextEdit()
        self.model_download_log.setObjectName("logView")
        self.model_download_log.viewport().setAutoFillBackground(False)
        self.model_download_log.setReadOnly(True)
        self.model_download_log.setMaximumBlockCount(1500)
        self.model_log_copy = make_button(
            self.language, "log_copy_errors",
            lambda: self.copy_error_log(self.model_download_log),
            role="logAction", icon="copy.svg")
        self.model_log_clear = make_button(
            self.language, "log_clear", self.model_download_log.clear,
            role="logAction", icon="trash.svg")
        for button in (self.model_log_copy, self.model_log_clear):
            button.setProperty("modelLogToggle", True)
            button.setMinimumHeight(28)
            button.setEnabled(False)
            model_log_header.addWidget(button)
        def update_model_log_actions():
            content = self.model_download_log.toPlainText()
            self.model_log_clear.setEnabled(bool(content))
            self.model_log_copy.setEnabled(bool(ERROR_LOG_PATTERN.search(content)))
        self.model_download_log.textChanged.connect(update_model_log_actions)
        model_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.model_log_container = QWidget()
        model_log_layout = QVBoxLayout(self.model_log_container)
        model_log_layout.setContentsMargins(0, 0, 0, 0)
        model_log_layout.setSizeConstraint(QVBoxLayout.SizeConstraint.SetNoConstraint)
        model_log_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.model_download_log.setFixedHeight(180)
        model_log_layout.addWidget(self.model_download_log, 0, Qt.AlignmentFlag.AlignTop)
        self.model_log_container.setFixedHeight(0)
        self.model_log_container.hide()
        self.model_log_animation = QVariantAnimation(self)
        self.model_log_animation.setDuration(280)
        self.model_log_animation.setEasingCurve(QEasingCurve.Type.InOutCubic)
        self.model_log_animation.valueChanged.connect(
            lambda height: self.model_log_container.setFixedHeight(round(height))
        )
        self.model_log_animation.finished.connect(
            lambda: self.model_log_container.setVisible(self.model_log_toggle.isChecked())
        )

        def toggle_model_log(expanded):
            self.model_log_animation.stop()
            self.model_log_container.show()
            self.model_log_animation.setStartValue(self.model_log_container.height())
            self.model_log_animation.setEndValue(180 if expanded else 0)
            self.model_log_animation.start()
            glyph = "chevron-down.svg" if expanded else "chevron-right.svg"
            self.model_log_toggle.setProperty("glyph", glyph)
            self.model_log_toggle.setIcon(
                contrast_icon(glyph, "#edf3fb" if self.canvas.dark else "#233142")
            )
        self.model_log_toggle.toggled.connect(toggle_model_log)
        model_layout.addWidget(self.model_log_container)
        root.addWidget(model_card)
        self.model_size_cache = {}
        self.model_size_checked = set()
        self.model_size_requested_key = None
        self.model_size_running_key = None
        self.model_size_process = QProcess(self)
        self.model_size_process.finished.connect(self.model_size_query_finished)
        self.model_size_process.errorOccurred.connect(self.model_size_query_error)
        self.model_combo.currentIndexChanged.connect(self.show_model_selection)
        self.model_combo.activated.connect(self.select_pdf_model_explicitly)
        self.query_selected_model_size()

        self.update_rows = []
        for section, components in (("engine_updates", ("ffmpeg", "libvips", "libreoffice")), ("app_updates", ("app",))):
            update_card, update_layout = card(self.language, section)
            for component in components:
                row = UpdateRow(self.language, component)
                row.webLinkRequested.connect(self.open_web_link)
                row.startupFinished.connect(self.check_next_startup_update)
                if component == "libvips":
                    row.installed.connect(self.refresh_image_formats)
                if component == "app":
                    self.app_update_row = row
                    row.availabilityChanged.connect(self.update_brand_version_status)
                self.update_rows.append(row)
                update_layout.addWidget(row)
            root.addWidget(update_card)
        self.notes_process = QProcess(page)
        self.notes_process.setProgram(sys.executable)
        self.notes_process.setArguments(["-X", "utf8", str(Path(__file__).with_name("engine_update.py")), "release-notes"])
        self.notes_process.finished.connect(self.release_notes_finished)

        about_card, about_layout = card(self.language, "about_title", "about_hint")
        about_icon = QLabel()
        about_icon.setProperty("glyph", "info.svg")
        about_icon.setPixmap(QIcon(str(Path(__file__).with_name("assets") / "icons" / "info.svg")).pixmap(QSize(16, 16)))
        about_heading = QHBoxLayout()
        about_heading.addWidget(about_icon)
        about_heading.addWidget(self.language.bind(QLabel(), "about_product"))
        about_heading.addStretch(1)
        self.about_name_value = QLabel(self.t("app_name"))
        self.about_name_value.setObjectName("muted")
        about_heading.addWidget(self.about_name_value)
        about_layout.addLayout(about_heading)

        version_row = QHBoxLayout()
        version_row.addWidget(self.language.bind(QLabel(), "about_version"))
        version_row.addStretch(1)
        self.about_version_value = QLabel()
        self.about_version_value.setObjectName("muted")
        version_row.addWidget(self.about_version_value)
        about_layout.addLayout(version_row)

        platform_row = QHBoxLayout()
        platform_row.addWidget(self.language.bind(QLabel(), "about_platform"))
        platform_row.addStretch(1)
        self.about_platform_value = QLabel(self.platform_name())
        self.about_platform_value.setObjectName("muted")
        platform_row.addWidget(self.about_platform_value)
        about_layout.addLayout(platform_row)
        self.hardware_info = self.hardware_read = None
        self.hardware_labels = []
        for key in ("cpu_model", "gpu_model"):
            row = QHBoxLayout()
            row.addWidget(self.language.bind(QLabel(), key))
            value = QLabel()
            value.setObjectName("muted")
            value.setTextFormat(Qt.TextFormat.PlainText)
            value.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
            value.setWordWrap(True)
            row.addWidget(value, 1)
            self.hardware_labels.append(value)
            about_layout.addLayout(row)

        self.about_project_link = QPushButton()
        self.about_project_link.setObjectName("projectLink")
        self.about_project_link.setCursor(Qt.CursorShape.PointingHandCursor)
        connect_action(self.about_project_link, lambda: self.open_web_link("https://github.com/xiaofa520/Formix"))
        about_layout.addWidget(self.about_project_link, 0, Qt.AlignmentFlag.AlignLeft)
        root.addWidget(about_card)
        for index in range(root.count()):
            settings_card = root.itemAt(index).widget()
            if settings_card is not None:
                settings_card.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        root.addStretch(1)
        return page

    def hardware_loaded(self, cpu, adapters):
        self.hardware_info = (cpu, "\n".join(adapters))
        self.hardware_read = None
        self.refresh_hardware_labels()

    def refresh_hardware_labels(self):
        for i, label in enumerate(self.hardware_labels):
            label.setText((self.hardware_info[i] or self.t("update_unknown"))
                          if self.hardware_info is not None else self.t("detecting_hardware"))

    def save_video_acceleration(self, *_):
        self.language.settings.setValue("conversion/videoAcceleration", self.video_acceleration_combo.currentData())

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, "drop_overlay"):
            self.drop_overlay.setGeometry(self.canvas.rect())
        if hasattr(self, "contrast_timer"):
            self.contrast_timer.start()
        if hasattr(self, "font_reload") and self.font_size_combo.currentData() == 0:
            self.font_reload.start(100)

    def automatic_font_size(self, font):
        # Compare actual ink heights at a larger size to reduce rounding errors.
        reference = QFontDatabase.systemFont(QFontDatabase.SystemFont.GeneralFont)
        sample_font = QFont(font)
        reference.setPixelSize(64)
        sample_font.setPixelSize(64)
        sample = self.t("file_list")
        target = QFontMetricsF(reference, self).tightBoundingRect(sample).height()
        actual = QFontMetricsF(sample_font, self).tightBoundingRect(sample).height()
        scale = min(self.width() / 1180, self.height() / 780) ** 0.5
        return max(11, min(18, round(13 * scale * target / max(1, actual))))

    def apply_selected_font(self):
        app = QApplication.instance()
        font = QFontDatabase.systemFont(QFontDatabase.SystemFont.GeneralFont)
        family = self.font_combo.currentData()
        if family:
            font.setFamily(family)
        size = self.font_size_combo.currentData() or self.automatic_font_size(font)
        if getattr(self, "_applied_font", None) == (font.family(), size):
            return
        self._applied_font = (font.family(), size)
        font.setPixelSize(size)
        app.setFont(font)
        app.setProperty("interfaceFontSize", size)
        apply_theme(app, getattr(self, "_applied_dark", False))
        for page in self.pages:
            page.destination.setFont(font)

    def change_font(self):
        self.language.settings.setValue("interface/fontFamily", self.font_combo.currentData())
        self.language.settings.setValue("interface/fontSize", self.font_size_combo.currentData())
        self.font_reload.start(0)

    def choose_background(self):
        path, _ = QFileDialog.getOpenFileName(self, self.t("select_image"), str(Path.home()),
                                              self.t("background_image") + " (*.png *.jpg *.jpeg *.webp *.bmp)")
        if path:
            self.load_background(path)

    def load_background(self, path, restoring=False):
        self.pick_background.setEnabled(False)
        self.clear_background.setEnabled(False)
        self.restoring_background = restoring
        app_data = QStandardPaths.writableLocation(QStandardPaths.StandardLocation.AppLocalDataLocation)
        cache_dir = Path(app_data) / "cache" / "background"
        self.background_task = BackgroundLoad(path, cache_dir)
        self.background_task.signals.loaded.connect(self.background_loaded, Qt.ConnectionType.QueuedConnection)
        QThreadPool.globalInstance().start(self.background_task)

    def background_loaded(self, image):
        task = self.background_task
        self.background_task = None
        self.pick_background.setEnabled(True)
        if not image.isNull():
            self.canvas.set_background_image(image)
            if task.cached_path:
                self.language.settings.setValue("interface/background", task.cached_path)
            if task.cache_error:
                QMessageBox.warning(self, self.t("background_image"), str(task.cache_error))
        elif self.restoring_background:
            self.reset_background()
        else:
            QMessageBox.warning(self, self.t("background_image"), self.t("background_read_error"))
        self.clear_background.setEnabled(not self.canvas.image.isNull())
        for slider in self.background_effects.values():
            slider.setEnabled(not self.canvas.image.isNull())

    def refresh_contrast(self):
        canvas = self.canvas
        # Theme owns foreground colors; wallpaper brightness must not override it.
        ink = "#ffffff" if canvas.dark else "#000000"
        link_ink = "#8dc5ff" if canvas.dark else "#175fa8"
        hover_ink = "#c4e2ff" if canvas.dark else "#104578"
        sheet = (f"QWidget {{ color: {ink}; }}"
                 f"QPushButton#projectLink {{ color: {link_ink}; }}"
                 f"QPushButton#projectLink:hover {{ color: {hover_ink}; }}")
        if self.styleSheet() != sheet:
            self.setStyleSheet(sheet)
        widgets = [*self.findChildren(QPushButton), *self.findChildren(QLabel)]
        for widget in widgets:
            name = widget.objectName()
            glyph = widget.property("glyph")
            if isinstance(widget, QLabel) and name == "hint" and 'href="settings"' in widget.text():
                text = re.sub(r"color:\s*#[0-9a-fA-F]{6}", f"color: {link_ink}", widget.text())
                if text != widget.text():
                    widget.setText(text)
            adaptive_text = name in {"queueStatus", "platformLabel", "navCategory", "navPage",
                                     "fileCount", "muted", "emptyHint"}
            if not adaptive_text and not glyph:
                continue
            if adaptive_text:
                # Clear old per-widget overrides, including those on hidden pages.
                if widget.styleSheet():
                    widget.setStyleSheet("")
            if glyph:
                checked_ink = ink
                icon = contrast_icon(glyph, ink, checked_ink)
                if isinstance(widget, QPushButton):
                    if widget.icon().cacheKey() != icon.cacheKey():
                        widget.setIcon(icon)
                elif widget.pixmap() and widget.property("glyphInk") != ink:
                    widget.setPixmap(icon.pixmap(widget.pixmap().deviceIndependentSize().toSize(), widget.devicePixelRatioF()))
                    widget.setProperty("glyphInk", ink)

    def showEvent(self, event):
        super().showEvent(event)
        self.contrast_timer.start()

    def change_background_effect(self, key, value, label):
        label.setText(f"{value}%")
        self.language.settings.setValue("interface/background/" + key, value)
        if not self.background_preview_timer.isActive():
            self.background_preview_timer.start()

    def preview_background(self):
        self.canvas.set_effects(self.background_effects["image_opacity"].value(),
                                self.background_effects["blur"].value(),
                                self.background_effects["mask_opacity"].value())

    def reset_background(self):
        self.language.settings.remove("interface/background")
        app_data = QStandardPaths.writableLocation(QStandardPaths.StandardLocation.AppLocalDataLocation)
        cache_dir = Path(app_data) / "cache" / "background"
        if cache_dir.is_dir():
            for cached in (*cache_dir.glob("wallpaper*"), *cache_dir.glob(".wallpaper*.tmp")):
                try:
                    cached.unlink(missing_ok=True)
                except OSError:
                    pass
        self.canvas.set_background_image(QImage())
        self.clear_background.setEnabled(False)
        for key, slider in self.background_effects.items():
            slider.setValue(BACKGROUND_DEFAULTS[key])
            slider.setEnabled(False)

    def load_release_notes(self):
        if (self.notes_process.state() == QProcess.ProcessState.NotRunning
                and self.app_update_row.process.state() == QProcess.ProcessState.NotRunning):
            self.notes_process.start()

    def release_notes_finished(self, code, *_):
        output = bytes(self.notes_process.readAllStandardOutput())
        self.notes_process.readAllStandardError()
        if not code:
            try:
                data = json.loads(output)
            except (ValueError, UnicodeError):
                data = None
            if isinstance(data, dict) and isinstance(data.get("tag"), str) and data["tag"].strip() and isinstance(data.get("notes"), str):
                self.language.settings.setValue("updates/releaseNotes", [data["tag"], data["notes"].strip()])
                self.app_update_row.refresh_dialog_notes("release_notes_empty")

    def change_language(self, index):
        self.language.set_language(self.language_combo.itemData(index))

    def open_model_homepage(self):
        url = f"https://huggingface.co/{MODEL_REPOS[self.model_combo.currentData()]}"
        self.open_web_link(url)

    def open_web_link(self, url):
        browser = self.browser_combo.currentData()
        if sys.platform == "win32":
            run_background(lambda: dispatch_web_url(url, browser),
                           lambda opened, error: self.web_url_result(url, opened))
        else:
            self.web_url_result(url, dispatch_web_url(url, browser))

    def web_url_result(self, url, opened):
        if opened:
            return
        dialog = QMessageBox(self)
        dialog.setWindowTitle(self.t("copy_model_url"))
        dialog.setText(self.t("model_browser_handoff") + "\n\n" + url)
        dialog.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        copy = dialog.addButton(self.t("copy_model_url"), QMessageBox.ButtonRole.ActionRole)
        dialog.addButton(self.t("cancel"), QMessageBox.ButtonRole.RejectRole)
        dialog.exec()
        if dialog.clickedButton() == copy:
            QApplication.clipboard().setText(url)

    def open_model_folder(self):
        folder = self.model_root / self.model_combo.currentData()
        if (folder / "READY").is_file():
            self.open_folder_path(folder, "open_model_folder")
        else:
            QMessageBox.information(self, self.t("open_model_folder"), self.t("model_missing"))

    def open_folder_path(self, path, title_key):
        def failed(folder):
            if not self.closing:
                QMessageBox.warning(self, self.t(title_key), self.t("folder_open_failed", path=str(folder)))
        open_folder_async(path, failed)

    def show_model_stage(self, key):
        self.model_stage = key
        self.model_status.setText(self.t(key))
        self.update_queue_label()

    def query_selected_model_size(self, *_):
        key = self.model_combo.currentData()
        if not key:
            return
        cached = self.language.settings.value(f"models/size/{key}", "", type=str)
        if cached:
            try:
                revision, size = json.loads(cached)
                if isinstance(revision, str) and isinstance(size, int) and size > 0:
                    self.model_size_cache[key] = (revision, size)
            except (ValueError, TypeError):
                pass
        self.show_model_disk_size(key)
        if key not in self.model_size_checked:
            self.model_size_checked.add(key)
            self.model_size_requested_key = key
            self.start_model_size_query()

    def show_model_disk_size(self, key):
        cached = self.model_size_cache.get(key)
        if cached:
            size_gib = cached[1] / 1024**3
            self.model_disk_size.setText(self.t("model_disk_size", size=f"{size_gib:.2f} GiB"))
        elif self.model_size_running_key == key or self.model_size_requested_key == key:
            self.model_disk_size.setText(self.t("model_size_loading"))
        else:
            self.model_disk_size.setText(self.t("model_disk_size", size=self.t("update_unknown")))

    def start_model_size_query(self):
        if (self.model_size_process.state() != QProcess.ProcessState.NotRunning
                or not self.model_size_requested_key):
            return
        key = self.model_size_requested_key
        self.model_size_requested_key = None
        self.model_size_running_key = key
        self.model_size_process.start(sys.executable, ["-X", "utf8", WORKER, "size", key])

    def model_size_query_finished(self, code, *_):
        key = self.model_size_running_key
        value = bytes(self.model_size_process.readAllStandardOutput()).strip()
        error = bytes(self.model_size_process.readAllStandardError()).decode(errors="replace").strip()
        self.model_size_running_key = None
        if key and not code:
            try:
                revision, size = json.loads(value)
                if isinstance(revision, str) and isinstance(size, int) and size > 0:
                    self.model_size_cache[key] = (revision, size)
                    self.language.settings.setValue(f"models/size/{key}", json.dumps([revision, size]))
                    self.language.settings.sync()
            except (ValueError, TypeError):
                pass
        if key == self.model_combo.currentData():
            self.show_model_disk_size(key)
        if self.model_size_requested_key:
            self.start_model_size_query()

    def model_size_query_error(self, error):
        if error != QProcess.ProcessError.FailedToStart:
            return
        key = self.model_size_running_key
        self.model_size_running_key = None
        if key == self.model_combo.currentData():
            self.show_model_disk_size(key)
        if self.model_size_requested_key:
            self.start_model_size_query()

    def cuda_detected(self, version, error):
        self.cuda_pending = False
        self.cuda_version = version
        self.cuda_label.setText(self.t("cuda_version", version=version or self.t("cuda_absent")))
        self.show_model_selection()

    def show_model_memory(self):
        profile = MODEL_PROFILES[self.model_combo.currentData()]
        def requirement(key):
            value = profile.get(key)
            return self.t("update_unknown") if value is None else f"{value} GiB"
        self.model_memory.setText(self.t("model_memory_info", ram=requirement("min_available_ram_gib"),
                                         vram=requirement("min_cuda_vram_gib")))

    def refresh_model_state(self, *_):
        self.installed_model_keys = {key for key in MODEL_PROFILES if (self.model_root / key / "READY").is_file()}
        self.show_model_selection()

    def open_ocr_model_settings(self, key):
        self._ocr_model_download_context = True
        index = self.model_combo.findData(key)
        if index < 0:
            self.model_combo.addItem(MODEL_PROFILES[key].get("label", key), key)
            index = self.model_combo.findData(key)
        self.model_combo.setCurrentIndex(index)
        self.show_model_selection()
        self.page_buttons.button(self.stack.indexOf(self.settings_scroll)).click()
        QTimer.singleShot(250, lambda: self.settings_scroll.ensureWidgetVisible(self.model_combo, 0, 90))

    def restore_pdf_model_selection(self, index):
        if self._ocr_model_download_context and self.stack.widget(index) is not self.settings_scroll:
            self.model_combo.setCurrentIndex(self.model_combo.findData(self.models.name))
            self._ocr_model_download_context = False

    def select_pdf_model_explicitly(self, *_):
        self._ocr_model_download_context = False
        self.show_model_selection()

    def show_model_selection(self, *_):
        selected = self.model_root / self.model_combo.currentData()
        installed = selected.name in self.installed_model_keys
        if not self._ocr_model_download_context:
            if self.language.settings.value("pdf/model", "", type=str) != selected.name:
                self.language.settings.setValue("pdf/model", selected.name)
                self.language.settings.sync()
                diagnostic_event('pdf_model_preference_saved', model=selected.name,
                                 status=str(self.language.settings.status()))
            if selected != self.models:
                diagnostic_event('pdf_model_selected', model=selected.name, downloaded=installed)
                self.models = selected
                self.tasks.models = selected
        locked = bool(self.tasks.active_job or self.tasks.queue or getattr(self, "meta", None))
        self.model_combo.setEnabled(not locked)
        self.model_status_icon.setPixmap(self.model_icons[installed])
        self.model_status.setText(self.t("model_installed" if installed else "model_missing"))
        self.show_model_memory()
        self.query_selected_model_size()
        if self.model_stage:
            self.model_status.setText(self.t(self.model_stage))
        self.install_model_button.setEnabled(not installed and not locked and
                                             not (selected.name == "deepseek-ocr" and self.cuda_pending))
        self.delete_model_button.setEnabled(installed and not locked)

    def install_model(self):
        if self.model_combo.currentData() == "deepseek-ocr" and not self.cuda_version:
            if self.cuda_pending:
                return
            prompt = QMessageBox(self)
            prompt.setWindowTitle("DeepSeek-OCR")
            prompt.setText(self.t("deepseek_gpu_required", gb=MODEL_PROFILES["deepseek-ocr"]["min_cuda_vram_gib"]))
            download = prompt.addButton(self.t("download_driver"), QMessageBox.ButtonRole.ActionRole)
            prompt.addButton(self.t("cancel"), QMessageBox.ButtonRole.RejectRole)
            prompt.exec()
            if prompt.clickedButton() == download:
                self.open_web_link("https://www.nvidia.com/Download/index.aspx")
            return
        self.meta = QProcess(self)
        self.install_model_button.setEnabled(False)
        self.model_status.setText(self.t("model_querying"))
        self.meta.finished.connect(self.confirm_model_download)
        self.model_combo.setEnabled(False)
        self.meta.errorOccurred.connect(self.model_query_error)
        self.meta.start(sys.executable, ["-X", "utf8", WORKER, "size", self.model_combo.currentData()])

    def model_query_error(self, error):
        if error == QProcess.ProcessError.FailedToStart:
            self.confirm_model_download(1)

    def confirm_model_download(self, code, *_):
        value = bytes(self.meta.readAllStandardOutput()).strip()
        self.meta.deleteLater()
        self.meta = None
        self.refresh_model_state()
        if self.closing:
            return
        if code:
            QMessageBox.warning(self, self.t("model_manager"), self.t("model_size_error"))
            return
        try:
            revision, size = json.loads(value)
        except (ValueError, TypeError):
            QMessageBox.warning(self, self.t("model_manager"), self.t("model_size_error"))
            return
        key = self.model_combo.currentData()
        question = self.t("model_download_question", model=self.model_combo.currentText(), size=size / 1_000_000)
        answer = QMessageBox.question(self, self.t("model_download_title"), question + "\n" + self.t("model_env_notice"))
        if answer == QMessageBox.StandardButton.Yes:
            self.tasks.queue.append((self.model_combo.currentText(), None, key, revision, None, "cpu"))
            self.tasks.next_job()
            self.update_queue_label()

    def remove_model(self):
        if self.tasks.active_job or self.tasks.queue:
            QMessageBox.information(self, self.t("model_manager"), self.t("model_busy"))
            return
        selected = self.model_root / self.model_combo.currentData()
        if selected.exists() and QMessageBox.question(self, self.t("delete_model"), self.t("model_remove_question")) == QMessageBox.StandardButton.Yes:
            retired = Path(tempfile.mkdtemp(dir=self.model_root, prefix='.retired-'))
            try:
                selected.rename(retired / 'model')
            except OSError as exc:
                retired.rmdir()
                QMessageBox.warning(self, self.t('model_manager'), str(exc))
                return
            # The vision runtime is shared by all downloaded models. Remove it
            # together with the last model, but keep it while another model
            # still depends on it.
            remaining_models = any(
                (self.model_root / key / "READY").is_file()
                for key in MODEL_REPOS if key != selected.name
            )
            if not remaining_models:
                for runtime in self.model_root.glob(".vision-runtime-v*-*"):
                    try:
                        runtime.rename(retired / runtime.name)
                    except OSError as exc:
                        QMessageBox.warning(self, self.t("model_manager"), str(exc))
            cleanup_path(retired, lambda _, error: QMessageBox.warning(self, self.t('model_manager'), str(error))
                         if error and not self.closing else None)
            for key in MODEL_REPOS:
                if (self.model_root / key / "READY").is_file():
                    self.model_combo.setCurrentIndex(self.model_combo.findData(key))
                    break
        self.refresh_model_state()

    def update_queue_label(self):
        queued = len(self.tasks.queue)
        has_pending_work = bool(self.tasks.active_job or queued)
        preserve_completion = False
        if has_pending_work:
            self.queue_result_timer.stop()
            self.queue_summary_expired = False
            state = self.t("file_paused" if self.tasks.paused else "queue_processing")
            if self.tasks.label_key == "task_model_download" and self.model_stage and not self.tasks.paused:
                state = self.t(self.model_stage)
            text = (state if self.tasks.label_key == "task_model_download" else
                    self.t("queue_counts", total=queued + 1, state=state, waiting=queued))
            if self.progress_detail and not self.tasks.paused:
                text += " · " + self.progress_detail
        elif self.tasks.results and not self.queue_summary_expired:
            outcomes = [(key, count) for key, count in self.tasks.results.items() if count]
            preserve_completion = bool(outcomes) and all(key == "file_done" for key, _ in outcomes)
            text = (self.t("file_done") if preserve_completion else
                    " · ".join(f"{self.t(key)} {count}" for key, count in outcomes))
            if not self.queue_result_timer.isActive():
                self.queue_result_timer.start()
        else:
            self.queue_result_timer.stop()
            text = self.t("queue_waiting", count=queued) if queued else self.t("queue_empty")
            if not self.tasks.results:
                self.queue_summary_expired = False
        self.queue_label.setMinimumWidth(
            self.queue_label.fontMetrics().horizontalAdvance(text) if preserve_completion else 0
        )
        self.queue_label.set_status(text, preserve=preserve_completion)
        expanded = has_pending_work
        if expanded:
            target_width = 350
        elif self.tasks.results and not self.queue_summary_expired:
            text_width = self.queue_label.fontMetrics().horizontalAdvance(text)
            completed_width = self.queue_label.fontMetrics().horizontalAdvance(self.t("file_done")) + 44
            target_width = max(104, min(190, max(text_width + 44, completed_width)))
        else:
            target_width = 70
        if target_width != self.task_badge_width:
            self.task_badge_animation.stop()
            self.task_badge_animation.setStartValue(self.task_badge.width())
            self.task_badge_animation.setEndValue(target_width)
            self.task_badge_width = target_width
            self.task_badge_animation.start()
        self.task_badge_layout.setStretch(0, 1 if expanded else 0)
        self.task_badge_layout.setAlignment(
            self.task_status_group,
            Qt.AlignmentFlag.AlignVCenter if expanded else Qt.AlignmentFlag.AlignCenter,
        )
        self.task_status_group.setSizePolicy(
            QSizePolicy.Expanding if expanded else QSizePolicy.Fixed,
            QSizePolicy.Preferred,
        )
        self.queue_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

    def expire_queue_summary(self):
        if self.tasks.active_job or self.tasks.queue:
            return
        self.queue_summary_expired = True
        self.update_queue_label()

    def on_busy_changed(self, busy):
        self.task_busy = busy
        if busy:
            self.repeat_conversion_timer.stop()
        elif not self.tasks.queue and not self.closing:
            self.repeat_conversion_timer.start()
        if not busy:
            self.model_stage = None
        self.cancel.setVisible(busy)
        self.on_paused_changed(self.tasks.paused)
        self.on_task_progress(-1)
        self.refresh_model_state()

    def enable_completed_files_for_repeat(self):
        if self.closing or self.tasks.active_job or self.tasks.queue:
            return
        for page in self.pages:
            for source in page.files.sources:
                if page.files.states.get(source) == "file_done":
                    page.files.pending.add(source)
            page.update_file_actions()

    def restore_pending_jobs(self):
        if self.closing:
            return
        settings = self.language.settings
        saved = settings.value("tasks/pending", "", type=str)
        jobs = []
        if saved:
            try:
                rows = json.loads(saved)
            except ValueError:
                rows = []
            for row in rows if isinstance(rows, list) else ():
                if not isinstance(row, list) or len(row) not in {6, 7}:
                    continue
                name, source, option, audio, folder, mode = row[:6]
                if not all(isinstance(v, str) for v in (name, option, audio, mode)):
                    continue
                if source is None and option in MODEL_REPOS and folder is None:
                    jobs.append(tuple(row[:6]))
                elif (isinstance(source, str) and isinstance(folder, str) and Path(folder).is_absolute()
                      and option in PAGES.get(name, ())):
                    remote = name == "M3U8 合成" and source.lower().startswith(("http://", "https://"))
                    if remote or Path(source).is_absolute():
                        job = (name, source if remote else Path(source), option, audio, Path(folder), mode)
                        if len(row) == 7 and name in {"音频压缩", "视频压缩", "图片压缩"}:
                            params = row[6] if isinstance(row[6], dict) else {}
                            detail = params.get("detail")
                            width = params.get("width", "original")
                            if name == "视频压缩":
                                try:
                                    detail = max(0, min(4320, int(detail)))
                                except (TypeError, ValueError):
                                    detail = 0
                                try:
                                    width = max(0, min(7680, int(width))) if width != "original" else "original"
                                except (TypeError, ValueError):
                                    width = "original"
                            else:
                                allowed_detail = {"音频压缩": {"original", "mono"},
                                                  "图片压缩": {"original", "75", "50"}}[name]
                                if not isinstance(detail, str) or detail not in allowed_detail:
                                    detail = "original"
                            try:
                                bitrate = max(0, min(512, int(params.get("bitrate", 0))))
                            except (TypeError, ValueError):
                                bitrate = 0
                            if bitrate:
                                bitrate = max(32, bitrate)
                            params = {"detail": detail, "bitrate": bitrate,
                                      "preserve_metadata": True}
                            if name == "视频压缩":
                                params.update(width=width, height=detail)
                            job += (params,)
                        elif len(row) == 7 and name == "图片转换" and option == "ico":
                            params = row[6] if isinstance(row[6], dict) else {}
                            sizes = params.get("icon_sizes", [32, 64, 128])
                            if not isinstance(sizes, list) or any(size not in (32, 64, 128) for size in sizes):
                                sizes = [32, 64, 128]
                            job += ({"icon_sizes": sorted(set(sizes)) or [32, 64, 128]},)
                        if len(row) == 7 and name in {"图片提取文字", "PDF 转换"} and isinstance(row[6], dict):
                            model = row[6].get("recognition_model")
                            if model in MODEL_PROFILES:
                                job += ({"recognition_model": model},)
                        jobs.append(job)
        should_restore = False
        if jobs:
            dialog = QMessageBox(QMessageBox.Icon.Question, self.t("restore_jobs"),
                                 self.t("restore_jobs_prompt", count=len(jobs)),
                                 QMessageBox.StandardButton.NoButton, self)
            restore_button = dialog.addButton(self.t("restore_jobs"), QMessageBox.ButtonRole.AcceptRole)
            dialog.addButton(self.t("cancel"), QMessageBox.ButtonRole.RejectRole)
            dialog.setDefaultButton(restore_button)
            dialog.exec()
            should_restore = dialog.clickedButton() == restore_button
        if should_restore:
            self.tasks.new_batch = False
            self.tasks.queue.extend(jobs)
            for page in self.pages:
                sources = [str(job[1]) for job in jobs if job[1] is not None and job[0] == page.name]
                if sources:
                    page.files.setStringList(list(dict.fromkeys(page.files.stringList() + sources)))
                    for source in sources:
                        page.files.set_state(source, "file_queued")
                    page.update_file_actions()
                    self.append_log(page.name, self.t("recovery_restored", count=len(sources)))
            self.save_recovery_state()
            self.tasks.next_job()
            self.update_queue_label()
        elif saved:
            settings.remove("tasks/pending")
            settings.remove("tasks/results")
            settings.remove("recovery/logs")
            for view in self.log_views.values():
                view.clear()
            self.has_recovery_snapshot = False
            settings.sync()
        self.update_queue_label()
        self.check_next_startup_update()

    def closeEvent(self, event):
        if self.closing:
            processes = [self.runtime_check, self.notes_process, self.hardware_probe,
                         getattr(self, "model_size_process", None),
                         getattr(self, 'meta', None), *(row.process for row in self.update_rows)]
            if self.tasks.proc or any(p and p.state() != QProcess.ProcessState.NotRunning for p in processes):
                event.ignore()
            else:
                self.close_poll.stop()
                event.accept()
            return
        self.closing = True
        self.tasks.closing = True
        self.recovery_timer.stop()
        self.save_recovery_state()
        self.tasks.queue.clear()
        for task in self.drop_scans:
            task.cancelled.set()
        for page in self.pages:
            for task in page._folder_scans:
                task.cancelled.set()
        if self.tasks.proc:
            self.tasks.stop()
        self.category_timer.stop()
        self.navigation_timer.stop()
        self.notes_open_timer.stop()
        self.hardware_probe_timeout.stop()
        for process in [self.runtime_check, self.notes_process, self.hardware_probe,
                        getattr(self, "model_size_process", None), *(row.process for row in self.update_rows)]:
            if process is None:
                continue
            if process.state() != QProcess.ProcessState.NotRunning:
                kill_process_tree(process)
        if getattr(self, "meta", None):
            kill_process_tree(self.meta)
        self.close_poll.start()
        event.ignore()


def apply_theme(app, dark=False):
    QDir.setSearchPaths("formixicons", [str(Path(__file__).with_name("assets") / "icons")])
    if app.style().objectName().lower() != "fusion" and not app.styleSheet():
        app.setStyle("Fusion")
    stylesheet = Path(__file__).with_name("glass.qss").read_text(encoding="utf-8-sig")
    if dark:
        stylesheet += Path(__file__).with_name("glass-dark.qss").read_text(encoding="utf-8")
    base_size = app.property("interfaceFontSize") or 13
    stylesheet = re.sub(r"(font-size:\s*)(\d+)px",
                        lambda m: f"{m[1]}{round(int(m[2]) * base_size / 13)}px", stylesheet)
    app.setStyleSheet(stylesheet)




def main():
    group_windows_processes()
    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )
    app = QApplication(sys.argv)
    app.setOrganizationName("Formix")
    app.setApplicationName("Formix")
    app.setApplicationVersion(app_version())
    language = LanguageManager()
    icon = Path(__file__).with_name("assets") / "logo1.png"
    if icon.exists():
        app.setWindowIcon(QIcon(str(icon)))
        app.setApplicationDisplayName(language.t("app_name"))
    apply_theme(app)
    window = Window(language)
    window.show()
    return app.exec()


