# format_factory/gui_pages/m3u8_downloader.py
import os
from PyQt6.QtWidgets import (
    QHBoxLayout, QVBoxLayout, QLabel, QLineEdit, QPushButton,
    QFileDialog, QFrame, QComboBox, QSizePolicy, QApplication, QTextEdit
)
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QFont

from .base_page import (BaseConverterPage, CardWidget, SectionLabel,
                        DropFileList, AnimatedProgressBar, ArgsPanel,
                        _BTN_H, _BTN_W, _BTN_W_SM, _BTN_W_PRI,
                        _CTRL_H, _COMBO_W)
from ..i18n import LANG_AUTO, LANG_EN, LANG_JA, LANG_KO, LANG_ZH_CN, LANG_ZH_TW, resolve_language, tr


_M3U8_TEXT = {
    LANG_ZH_CN: {
        "source": "M3U8 来源",
        "address": "地址 / 路径",
        "placeholder": "输入 M3U8 URL 或本地 .m3u8 文件路径…",
        "pick_local": "选择本地 .m3u8 文件",
        "options": "输出选项",
        "format": "格式",
        "directory": "目录",
        "select": "选择",
        "select_tip": "选择保存目录",
        "start": "开始下载/转换",
        "log": "转换日志",
        "copy_tip": "复制全部日志到剪贴板",
        "clear_tip": "清空日志",
        "missing_ffmpeg": "未找到 FFmpeg，请到设置下载",
        "missing_source": "请输入 M3U8 URL 或选择本地文件",
        "pick_title": "选择本地 M3U8 文件",
        "filter": "M3U8 文件 (*.m3u8);;所有文件 (*.*)",
    },
    LANG_ZH_TW: {
        "source": "M3U8 來源",
        "address": "地址 / 路徑",
        "placeholder": "輸入 M3U8 URL 或本地 .m3u8 檔案路徑…",
        "pick_local": "選擇本地 .m3u8 檔案",
        "options": "輸出選項",
        "format": "格式",
        "directory": "目錄",
        "select": "選擇",
        "select_tip": "選擇儲存目錄",
        "start": "開始下載/轉換",
        "log": "轉換日誌",
        "copy_tip": "複製全部日誌到剪貼簿",
        "clear_tip": "清空日誌",
        "missing_ffmpeg": "未找到 FFmpeg，請到設定下載",
        "missing_source": "請輸入 M3U8 URL 或選擇本地檔案",
        "pick_title": "選擇本地 M3U8 檔案",
        "filter": "M3U8 檔案 (*.m3u8);;所有檔案 (*.*)",
    },
    LANG_EN: {
        "source": "M3U8 Source",
        "address": "URL / Path",
        "placeholder": "Enter an M3U8 URL or a local .m3u8 path…",
        "pick_local": "Choose local .m3u8 file",
        "options": "Output options",
        "format": "Format",
        "directory": "Directory",
        "select": "Select",
        "select_tip": "Choose output directory",
        "start": "Download / Convert",
        "log": "Conversion log",
        "copy_tip": "Copy all logs to clipboard",
        "clear_tip": "Clear log",
        "missing_ffmpeg": "FFmpeg not found. Please download it from Settings.",
        "missing_source": "Enter an M3U8 URL or choose a local file.",
        "pick_title": "Choose local M3U8 file",
        "filter": "M3U8 files (*.m3u8);;All files (*.*)",
    },
    LANG_JA: {
        "source": "M3U8 ソース",
        "address": "URL / パス",
        "placeholder": "M3U8 URL またはローカル .m3u8 パスを入力…",
        "pick_local": "ローカル .m3u8 ファイルを選択",
        "options": "出力オプション",
        "format": "形式",
        "directory": "保存先",
        "select": "選択",
        "select_tip": "出力先フォルダを選択",
        "start": "ダウンロード / 変換",
        "log": "変換ログ",
        "copy_tip": "ログをクリップボードへコピー",
        "clear_tip": "ログを消去",
        "missing_ffmpeg": "FFmpeg が見つかりません。設定からダウンロードしてください。",
        "missing_source": "M3U8 URL を入力するか、ローカルファイルを選択してください。",
        "pick_title": "ローカル M3U8 ファイルを選択",
        "filter": "M3U8 ファイル (*.m3u8);;すべてのファイル (*.*)",
    },
    LANG_KO: {
        "source": "M3U8 소스",
        "address": "URL / 경로",
        "placeholder": "M3U8 URL 또는 로컬 .m3u8 경로를 입력하세요…",
        "pick_local": "로컬 .m3u8 파일 선택",
        "options": "출력 옵션",
        "format": "형식",
        "directory": "저장 위치",
        "select": "선택",
        "select_tip": "출력 폴더 선택",
        "start": "다운로드 / 변환",
        "log": "변환 로그",
        "copy_tip": "모든 로그를 클립보드에 복사",
        "clear_tip": "로그 지우기",
        "missing_ffmpeg": "FFmpeg를 찾을 수 없습니다. 설정에서 다운로드하세요.",
        "missing_source": "M3U8 URL을 입력하거나 로컬 파일을 선택하세요.",
        "pick_title": "로컬 M3U8 파일 선택",
        "filter": "M3U8 파일 (*.m3u8);;모든 파일 (*.*)",
    },
}


def _m3u8_text(language: str, key: str) -> str:
    lang = resolve_language(language or LANG_AUTO)
    return _M3U8_TEXT.get(lang, _M3U8_TEXT[LANG_EN]).get(key, key)


class M3U8DownloaderPage(BaseConverterPage):
    def __init__(self, ffmpeg_handler=None, parent=None):
        self._language = LANG_AUTO
        super().__init__("m3u8", ffmpeg_handler, parent)

    # Override _init_ui completely — different input widget
    def _init_ui(self):
        import html as _html_mod
        from datetime import datetime
        self._html_mod = _html_mod
        self._datetime = datetime

        root = QVBoxLayout(self)
        root.setContentsMargins(14, 12, 14, 12)
        root.setSpacing(10)

        # ══ 上半区：左右分栏 ══
        body = QHBoxLayout()
        body.setSpacing(10)

        # ── 左列：来源卡片 ──────────────────────────
        in_card = CardWidget()
        il = in_card.layout()
        il.setSpacing(10)
        self.source_section_label = SectionLabel("M3U8 来源")
        il.addWidget(self.source_section_label)

        url_row = QHBoxLayout(); url_row.setSpacing(8)
        self.url_lbl = QLabel("地址 / 路径")
        self.url_lbl.setObjectName("row_label")
        self.url_lbl.setFixedWidth(72)
        self.m3u8_url_edit = QLineEdit()
        self.m3u8_url_edit.setMinimumHeight(_CTRL_H)
        self.m3u8_url_edit.setPlaceholderText("输入 M3U8 URL 或本地 .m3u8 文件路径…")
        self.m3u8_url_edit.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.m3u8_url_edit.textChanged.connect(self._update_src)
        url_row.addWidget(self.url_lbl)
        url_row.addWidget(self.m3u8_url_edit, 1)
        il.addLayout(url_row)

        loc_row = QHBoxLayout(); loc_row.setSpacing(8)
        self.select_local_m3u8_button = QPushButton("选择本地 .m3u8 文件")
        self.select_local_m3u8_button.setMinimumSize(190, _BTN_H)
        self.select_local_m3u8_button.setSizePolicy(
            QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self.select_local_m3u8_button.clicked.connect(self._pick_local)
        loc_row.addWidget(self.select_local_m3u8_button)
        loc_row.addStretch()
        il.addLayout(loc_row)
        il.addStretch()

        # Hidden stub widgets so base-class references don't crash
        self.input_label                  = QLabel()
        self.input_label.setVisible(False)
        self.input_file_list_widget       = DropFileList()
        self.input_file_list_widget.setVisible(False)
        self.select_input_files_button    = QPushButton()
        self.select_input_files_button.setVisible(False)
        self.remove_selected_files_button = QPushButton()
        self.remove_selected_files_button.setVisible(False)

        body.addWidget(in_card, 5)

        # ── 右列：选项 + 操作（垂直堆叠）──────────────
        right_col = QVBoxLayout()
        right_col.setSpacing(10)

        # 输出选项卡片
        opt_card = CardWidget()
        ol = opt_card.layout()
        ol.setSpacing(10)
        self.output_options_label = SectionLabel("输出选项")
        ol.addWidget(self.output_options_label)

        # 格式行
        fmt_row = QHBoxLayout(); fmt_row.setSpacing(8)
        self.format_label = SectionLabel("格式")
        fmt_row.addWidget(self.format_label)
        self.output_format_combo = QComboBox()
        self.output_format_combo.setMinimumSize(_COMBO_W, _CTRL_H)
        self.output_format_combo.setSizePolicy(
            QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self.output_format_combo.addItems(self.output_formats_available)
        self.output_format_combo.currentIndexChanged.connect(self._on_fmt_changed)
        fmt_row.addWidget(self.output_format_combo)
        fmt_row.addStretch()
        ol.addLayout(fmt_row)

        # 目录行
        dir_row = QHBoxLayout(); dir_row.setSpacing(6)
        self.directory_label = SectionLabel("目录")
        dir_row.addWidget(self.directory_label)
        self.output_dir_edit = QLineEdit()
        self.output_dir_edit.setMinimumHeight(_CTRL_H)
        self.output_dir_edit.setPlaceholderText("选择保存目录…")
        self.output_dir_edit.setReadOnly(True)
        self.output_dir_edit.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.select_output_dir_button = QPushButton("选择")
        self.select_output_dir_button.setMinimumSize(_BTN_W_SM, _BTN_H)
        self.select_output_dir_button.setSizePolicy(
            QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self.select_output_dir_button.clicked.connect(self._select_dir)
        dir_row.addWidget(self.output_dir_edit, 1)
        dir_row.addWidget(self.select_output_dir_button)
        ol.addLayout(dir_row)

        # 参数面板
        f = QFrame(); f.setFrameShape(QFrame.Shape.HLine)
        ol.addWidget(f)
        self.args_panel = ArgsPanel("m3u8")
        ol.addWidget(self.args_panel)

        right_col.addWidget(opt_card)

        # 操作卡片
        ctrl_card = CardWidget()
        cl = ctrl_card.layout()
        cl.setSpacing(8)

        ar = QHBoxLayout(); ar.setSpacing(8)
        self.start_conversion_button = QPushButton("开始下载/转换")
        self.start_conversion_button.setObjectName("primary")
        self.start_conversion_button.setEnabled(False)
        self.start_conversion_button.setMinimumSize(_BTN_W_PRI, _BTN_H)
        self.start_conversion_button.setSizePolicy(
            QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self.start_conversion_button.clicked.connect(self._start_clicked)

        self.cancel_conversion_button = QPushButton("取消")
        self.cancel_conversion_button.setObjectName("danger")
        self.cancel_conversion_button.setEnabled(False)
        self.cancel_conversion_button.setMinimumSize(_BTN_W_SM, _BTN_H)
        self.cancel_conversion_button.setSizePolicy(
            QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self.cancel_conversion_button.clicked.connect(self._cancel_clicked)
        ar.addWidget(self.start_conversion_button)
        ar.addWidget(self.cancel_conversion_button)
        ar.addStretch()
        cl.addLayout(ar)

        self.overall_progress_bar = AnimatedProgressBar()
        cl.addWidget(self.overall_progress_bar)

        right_col.addWidget(ctrl_card)
        right_col.addStretch()

        body.addLayout(right_col, 4)
        root.addLayout(body, 2)

        # ══ 下半区：日志卡片（全宽）══
        log_card = CardWidget()
        ll = log_card.layout()
        ll.setSpacing(6)

        log_header = QHBoxLayout()
        self.log_section_label = SectionLabel("转换日志")
        log_header.addWidget(self.log_section_label)
        log_header.addStretch()

        self._btn_copy_log = QPushButton("复制")
        self._btn_copy_log.setMinimumSize(64, 26)
        self._btn_copy_log.setMaximumHeight(26)
        self._btn_copy_log.setSizePolicy(
            QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self._btn_copy_log.setToolTip("复制全部日志到剪贴板")
        self._btn_copy_log.clicked.connect(self._copy_log)

        self._btn_clear_log = QPushButton("清空")
        self._btn_clear_log.setMinimumSize(64, 26)
        self._btn_clear_log.setMaximumHeight(26)
        self._btn_clear_log.setSizePolicy(
            QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self._btn_clear_log.setToolTip("清空日志")
        self._btn_clear_log.clicked.connect(self._clear_log)

        log_header.addWidget(self._btn_copy_log)
        log_header.addWidget(self._btn_clear_log)
        ll.addLayout(log_header)

        self.log_display = QTextEdit()
        self.log_display.setReadOnly(True)
        self.log_display.setMinimumHeight(100)
        self.log_display.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.log_display.setLineWrapMode(QTextEdit.LineWrapMode.WidgetWidth)
        mono = QFont("Consolas", 11)
        mono.setStyleHint(QFont.StyleHint.Monospace)
        self.log_display.setFont(mono)
        ll.addWidget(self.log_display)

        self._progress_line = QLabel()
        self._progress_line.setObjectName("section_title")
        self._progress_line.setTextFormat(Qt.TextFormat.RichText)
        self._progress_line.setMinimumHeight(18)
        self._progress_line.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self._progress_line.clear()
        ll.addWidget(self._progress_line)

        root.addWidget(log_card, 3)

        self._update_src()
        self._retranslate_ui()

    # ── helpers ──────────────────────────────────────────────────────
    def _get_file_filter(self):
        return _m3u8_text(self._language, "filter")

    def _update_src(self):
        val = (self.m3u8_url_edit.text().strip()
               if hasattr(self, "m3u8_url_edit") else "")
        self.input_files = [val] if val else []
        self._update_state()

    def _pick_local(self):
        p, _ = QFileDialog.getOpenFileName(
            self, _m3u8_text(self._language, "pick_title"), "", self._get_file_filter())
        if p:
            self.m3u8_url_edit.setText(p)

    def _start_conversion_process(self):
        if not self.ffmpeg_handler:
            self.log_message(_m3u8_text(self._language, "missing_ffmpeg"), "error")
            self.start_conversion_button.setEnabled(True)
            self.cancel_conversion_button.setEnabled(False)
            return
        if not self.input_files or not self.input_files[0]:
            self.log_message(_m3u8_text(self._language, "missing_source"), "error")
            self.start_conversion_button.setEnabled(True)
            self.cancel_conversion_button.setEnabled(False)
            return
        src  = self.input_files[0]
        fmt  = self.output_format_combo.currentText()
        if src.startswith(("http://", "https://")):
            raw  = src.split("?")[0].split("/")[-1]
            stem = os.path.splitext(raw)[0] if "." in raw else "downloaded_stream"
        else:
            stem = os.path.splitext(os.path.basename(src))[0]

        if fmt == "m3u8":
            # HLS：m3u8 和 ts 切片统一放在 {stem}_segments 子目录
            seg_dir = os.path.join(self.output_dir, stem + "_segments")
            os.makedirs(seg_dir, exist_ok=True)
            base = ["-protocol_whitelist", "file,http,https,tcp,tls,crypto"]
            extra = self.args_panel.get_extra_args()
            if self.args_panel.is_custom_override():
                args = base + extra
            else:
                preset_args = list(extra)
                for i, a in enumerate(preset_args):
                    if a == "%03d.ts":
                        preset_args[i] = os.path.join(seg_dir, "%03d.ts")
                args = base + preset_args
            out_path = os.path.join(seg_dir, stem + ".m3u8")
            self.log_message(f"来源: {src}", "info")
            self.ffmpeg_handler.convert_file(0, src, out_path, args)
        else:
            from format_factory.config import DEFAULT_FFMPEG_ARGS
            protocol_args = ["-protocol_whitelist", "file,http,https,tcp,tls,crypto"]
            extra = self.args_panel.get_extra_args()
            if self.args_panel.is_custom_override():
                args = protocol_args + extra
            else:
                fmt_defaults = DEFAULT_FFMPEG_ARGS.get("video", {}).get(fmt, ["-c", "copy"])
                args = protocol_args + fmt_defaults + extra
            self.log_message(f"来源: {src}", "info")
            self.conversion_requested.emit(0, src, args, stem)

    def _update_state(self):
        has_src = bool(
            self.m3u8_url_edit.text().strip()
            if hasattr(self, "m3u8_url_edit") else False)
        self.start_conversion_button.setEnabled(
            has_src and bool(self.output_dir))

    def set_language(self, language: str):
        self._language = resolve_language(language or LANG_AUTO)
        super().set_language(language)
        self._retranslate_ui()

    def _retranslate_ui(self):
        if hasattr(self, "source_section_label"):
            self.source_section_label.setText(_m3u8_text(self._language, "source"))
        if hasattr(self, "url_lbl"):
            self.url_lbl.setText(_m3u8_text(self._language, "address"))
        if hasattr(self, "m3u8_url_edit"):
            self.m3u8_url_edit.setPlaceholderText(_m3u8_text(self._language, "placeholder"))
        if hasattr(self, "select_local_m3u8_button"):
            self.select_local_m3u8_button.setText(_m3u8_text(self._language, "pick_local"))
        if hasattr(self, "output_options_label"):
            self.output_options_label.setText(_m3u8_text(self._language, "options"))
        if hasattr(self, "format_label"):
            self.format_label.setText(_m3u8_text(self._language, "format"))
        if hasattr(self, "directory_label"):
            self.directory_label.setText(_m3u8_text(self._language, "directory"))
        if hasattr(self, "select_output_dir_button"):
            self.select_output_dir_button.setText(_m3u8_text(self._language, "select"))
            self.select_output_dir_button.setToolTip(_m3u8_text(self._language, "select_tip"))
        if hasattr(self, "output_dir_edit"):
            self.output_dir_edit.setPlaceholderText(tr(self._language, "output_dir_placeholder"))
        if hasattr(self, "start_conversion_button"):
            self.start_conversion_button.setText(_m3u8_text(self._language, "start"))
        if hasattr(self, "log_section_label"):
            self.log_section_label.setText(_m3u8_text(self._language, "log"))
        if hasattr(self, "_btn_copy_log"):
            self._btn_copy_log.setToolTip(_m3u8_text(self._language, "copy_tip"))
        if hasattr(self, "_btn_clear_log"):
            self._btn_clear_log.setToolTip(_m3u8_text(self._language, "clear_tip"))
