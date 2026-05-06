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


class M3U8DownloaderPage(BaseConverterPage):
    def __init__(self, ffmpeg_handler=None, parent=None):
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
        il.addWidget(SectionLabel("M3U8 来源"))

        url_row = QHBoxLayout(); url_row.setSpacing(8)
        url_lbl = QLabel("地址 / 路径")
        url_lbl.setObjectName("row_label")
        url_lbl.setFixedWidth(72)
        self.m3u8_url_edit = QLineEdit()
        self.m3u8_url_edit.setMinimumHeight(_CTRL_H)
        self.m3u8_url_edit.setPlaceholderText(
            "输入 M3U8 URL 或本地 .m3u8 文件路径…")
        self.m3u8_url_edit.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.m3u8_url_edit.textChanged.connect(self._update_src)
        url_row.addWidget(url_lbl)
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
        ol.addWidget(SectionLabel("输出选项"))

        # 格式行
        fmt_row = QHBoxLayout(); fmt_row.setSpacing(8)
        fmt_row.addWidget(SectionLabel("格式"))
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
        dir_row.addWidget(SectionLabel("目录"))
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
        self.start_conversion_button = QPushButton("▶  开始下载/转换")
        self.start_conversion_button.setObjectName("primary")
        self.start_conversion_button.setEnabled(False)
        self.start_conversion_button.setMinimumSize(_BTN_W_PRI, _BTN_H)
        self.start_conversion_button.setSizePolicy(
            QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self.start_conversion_button.clicked.connect(self._start_clicked)

        self.cancel_conversion_button = QPushButton("⏹  取消")
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
        log_header.addWidget(SectionLabel("📋  转换日志"))
        log_header.addStretch()

        self._btn_copy_log = QPushButton("⎘ 复制")
        self._btn_copy_log.setMinimumSize(64, 26)
        self._btn_copy_log.setMaximumHeight(26)
        self._btn_copy_log.setSizePolicy(
            QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self._btn_copy_log.setToolTip("复制全部日志到剪贴板")
        self._btn_copy_log.clicked.connect(self._copy_log)

        self._btn_clear_log = QPushButton("✕ 清空")
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

    # ── helpers ──────────────────────────────────────────────────────
    def _get_file_filter(self):
        return "M3U8 文件 (*.m3u8);;所有文件 (*.*)"

    def _update_src(self):
        val = (self.m3u8_url_edit.text().strip()
               if hasattr(self, "m3u8_url_edit") else "")
        self.input_files = [val] if val else []
        self._update_state()

    def _pick_local(self):
        p, _ = QFileDialog.getOpenFileName(
            self, "选择本地 M3U8 文件", "", self._get_file_filter())
        if p:
            self.m3u8_url_edit.setText(p)

    def _start_conversion_process(self):
        if not self.input_files or not self.input_files[0]:
            self.log_message("请输入 M3U8 URL 或选择本地文件", "error")
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
