# format_factory/gui_pages/av_splitter_page.py
"""
音视频分离 / 合成页面
  • 分离：从视频文件中提取纯视频流 或 纯音频流
  • 合成：将一条视频文件 + 一条音频文件合并成一个容器
两种模式在同一个页面中通过 Tab 切换。
"""
import os
import html as _html
from datetime import datetime

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QTabWidget,
    QPushButton, QLineEdit, QComboBox, QLabel,
    QFileDialog, QTextEdit, QProgressBar,
    QFrame, QSizePolicy, QListWidget, QAbstractItemView,
    QApplication,
)
from PyQt6.QtCore import pyqtSignal, Qt, QTimer
from PyQt6.QtGui import QFont, QDragEnterEvent, QDropEvent

# ── 常量 ──────────────────────────────────────────────────────────────
_BTN_H     = 32
_BTN_W     = 110
_BTN_W_SM  = 80
_BTN_W_PRI = 140

# 分离：视频输出格式（仅视频流，无音频）
VIDEO_ONLY_FMTS = ["m4a", "mp4", "mkv", "avi", "mov", "webm", "flv"]
# 分离：音频输出格式
AUDIO_ONLY_FMTS = ["m4a", "mp3", "aac", "wav", "flac", "ogg", "opus"]
# 合成：输出容器格式
MERGE_FMTS      = ["mp4", "mkv", "avi", "mov", "webm", "flv"]

# 输入文件过滤器
_VIDEO_FILTER = "视频文件 (*.mp4 *.mkv *.avi *.mov *.wmv *.flv *.m4a *.webm *.ts *.m2ts *.vob);;所有文件 (*.*)"
_AUDIO_FILTER = "音频文件 (*.mp3 *.aac *.wav *.flac *.ogg *.opus *.m4a *.ac3 *.dts);;所有文件 (*.*)"

# 分离：提取视频流默认参数（复制流，零损耗）
_SPLIT_VIDEO_ARGS: dict[str, list] = {
    "mp4":  ["-c:v", "copy", "-an"],
    "mkv":  ["-c:v", "copy", "-an"],
    "avi":  ["-c:v", "copy", "-an"],
    "mov":  ["-c:v", "copy", "-an"],
    "webm": ["-c:v", "copy", "-an"],
    "flv":  ["-c:v", "copy", "-an"],
    "m4a":  ["-c:v", "copy", "-an"],
}

# 分离：提取音频流默认参数
_SPLIT_AUDIO_ARGS: dict[str, list] = {
    "mp3":  ["-vn", "-c:a", "libmp3lame", "-b:a", "192k"],
    "aac":  ["-vn", "-c:a", "copy"],
    "m4a":  ["-vn", "-c:a", "copy"],
    "wav":  ["-vn", "-c:a", "pcm_s16le"],
    "flac": ["-vn", "-c:a", "flac", "-compression_level", "5"],
    "ogg":  ["-vn", "-c:a", "libvorbis", "-q:a", "4"],
    "opus": ["-vn", "-c:a", "libopus", "-b:a", "96k"],
}

# 合成：默认参数（复制流优先，只有需要重编码时才开编解码器）
_MERGE_ARGS: dict[str, list] = {
    "mp4":  ["-c:v", "copy", "-c:a", "aac",        "-b:a", "192k", "-movflags", "+faststart"],
    "mkv":  ["-c:v", "copy", "-c:a", "copy"],
    "avi":  ["-c:v", "copy", "-c:a", "libmp3lame",  "-b:a", "192k"],
    "mov":  ["-c:v", "copy", "-c:a", "aac",        "-b:a", "192k", "-movflags", "+faststart"],
    "webm": ["-c:v", "copy", "-c:a", "libopus",    "-b:a", "128k"],
    "flv":  ["-c:v", "copy", "-c:a", "aac",        "-b:a", "128k"],
}


# ═══════════════════════════════════════════════════════════════════════
#  小部件
# ═══════════════════════════════════════════════════════════════════════
class _SectionLabel(QLabel):
    def __init__(self, text, parent=None):
        super().__init__(text, parent)
        self.setObjectName("section_title")


class _Card(QFrame):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("card")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(14, 12, 14, 12)
        lay.setSpacing(8)

    def layout(self):
        return super().layout()


class _DropList(QListWidget):
    files_dropped = pyqtSignal(list)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAcceptDrops(True)
        self.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.setMinimumHeight(80)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

    def dragEnterEvent(self, e: QDragEnterEvent):
        if e.mimeData().hasUrls(): e.acceptProposedAction()

    def dragMoveEvent(self, e):
        if e.mimeData().hasUrls(): e.acceptProposedAction()

    def dropEvent(self, e: QDropEvent):
        paths = [u.toLocalFile() for u in e.mimeData().urls() if u.isLocalFile()]
        if paths:
            self.files_dropped.emit(paths)


def _mk_btn(text, min_w=_BTN_W, obj_name="") -> QPushButton:
    b = QPushButton(text)
    b.setMinimumSize(min_w, _BTN_H)
    b.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
    if obj_name:
        b.setObjectName(obj_name)
    return b


def _hline() -> QFrame:
    f = QFrame()
    f.setFrameShape(QFrame.Shape.HLine)
    return f


# ═══════════════════════════════════════════════════════════════════════
#  日志 Mixin
# ═══════════════════════════════════════════════════════════════════════
class _LogMixin:
    """共用日志方法，注入到 SplitTab / MergeTab。"""
    _is_dark: bool = False

    _PALETTE_LIGHT = {
        "info":    ("#2563EB", "ℹ"),
        "success": ("#16A34A", "✔"),
        "warning": ("#D97706", "⚠"),
        "error":   ("#DC2626", "✖"),
        "meta":    ("#0284C7", "📋"),
        "cmd":     ("#9333EA", "$"),
    }
    _PALETTE_DARK = {
        "info":    ("#93C5FD", "ℹ"),
        "success": ("#6EE7B7", "✔"),
        "warning": ("#FCD34D", "⚠"),
        "error":   ("#FCA5A5", "✖"),
        "meta":    ("#7DD3FC", "📋"),
        "cmd":     ("#C4B5FD", "$"),
    }

    def _kind_style(self, kind: str):
        p = self._PALETTE_DARK if self._is_dark else self._PALETTE_LIGHT
        return p.get(kind, ("#71717A" if self._is_dark else "#52525B", "·"))

    def log_message(self, msg: str, kind: str = "info"):
        ts     = datetime.now().strftime("%H:%M:%S")
        colour, icon = self._kind_style(kind)
        safe   = _html.escape(msg)
        ts_col = "#A1A1AA" if self._is_dark else "#52525B"
        row = (f'<p style="margin:1px 0;">'
               f'<span style="color:{ts_col};font-size:10px">[{ts}]</span>&nbsp;'
               f'<span style="color:{colour};font-weight:600">{icon}&nbsp;{safe}</span>'
               f'</p>')
        self._log.append(row)
        QTimer.singleShot(0, lambda:
            self._log.verticalScrollBar().setValue(
                self._log.verticalScrollBar().maximum()))

    def log_ffmpeg_line(self, _idx: int, kind: str, text: str):
        if kind == "progress":
            safe    = _html.escape(text)
            p_col   = "#D97706" if self._is_dark else "#92400E"
            ts_col  = "#A1A1AA" if self._is_dark else "#52525B"
            ts      = datetime.now().strftime("%H:%M:%S")
            self._prog_lbl.setText(
                f'<span style="color:{ts_col};font-size:10px">[{ts}]</span>&nbsp;'
                f'<span style="color:{p_col};font-size:11px;font-weight:600">⟳&nbsp;{safe}</span>')
        else:
            self.log_message(text, kind)

    def _clear_log(self):
        self._log.clear()
        self._prog_lbl.clear()

    def _copy_log(self):
        QApplication.clipboard().setText(self._log.toPlainText())
        self._copy_btn.setText("✔ 已复制")
        QTimer.singleShot(1500, lambda: self._copy_btn.setText("⎘ 复制"))

    def _build_log_card(self) -> _Card:
        card = _Card()
        lay  = card.layout()
        lay.setSpacing(6)

        hdr = QHBoxLayout()
        hdr.addWidget(_SectionLabel("📋  处理日志"))
        hdr.addStretch()
        self._copy_btn = QPushButton("⎘ 复制")
        self._copy_btn.setMinimumSize(64, 26); self._copy_btn.setMaximumHeight(26)
        self._copy_btn.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self._copy_btn.clicked.connect(self._copy_log)
        clr_btn = QPushButton("✕ 清空")
        clr_btn.setMinimumSize(64, 26); clr_btn.setMaximumHeight(26)
        clr_btn.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        clr_btn.clicked.connect(self._clear_log)
        hdr.addWidget(self._copy_btn)
        hdr.addWidget(clr_btn)
        lay.addLayout(hdr)

        self._log = QTextEdit()
        self._log.setReadOnly(True)
        self._log.setMinimumHeight(100)
        self._log.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self._log.setLineWrapMode(QTextEdit.LineWrapMode.WidgetWidth)
        mono = QFont("Consolas", 11); mono.setStyleHint(QFont.StyleHint.Monospace)
        self._log.setFont(mono)
        lay.addWidget(self._log)

        self._prog_lbl = QLabel()
        self._prog_lbl.setObjectName("section_title")
        self._prog_lbl.setTextFormat(Qt.TextFormat.RichText)
        self._prog_lbl.setMinimumHeight(18)
        self._prog_lbl.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        lay.addWidget(self._prog_lbl)

        return card


# ═══════════════════════════════════════════════════════════════════════
#  分离 Tab
# ═══════════════════════════════════════════════════════════════════════
class SplitTab(QWidget, _LogMixin):
    """
    从视频文件中分离出：
      - 纯视频流（去掉音频）
      - 纯音频流（去掉视频）
    支持批量文件，可同时提取视频和/或音频。
    """
    # (idx, input_path, output_path, ffmpeg_args)
    task_ready = pyqtSignal(int, str, str, list)
    cancel_sig = pyqtSignal()

    def __init__(self, ffmpeg_handler, parent=None):
        super().__init__(parent)
        self._handler      = ffmpeg_handler
        self._files: list  = []
        self._out_dir: str = ""
        self._tasks: list  = []   # flat list of (inp, outp, args)
        self._total        = 0
        self._done         = 0
        self._is_dark      = False
        self._init_ui()
        if ffmpeg_handler:
            ffmpeg_handler.file_info_ready.connect(self._on_file_info)

    # ── UI ────────────────────────────────────────────────────────────
    def _init_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(12, 10, 12, 10)
        root.setSpacing(10)

        body = QHBoxLayout(); body.setSpacing(10)

        # ── 左：文件列表 ──────────────────────────────────────────────
        fc = _Card()
        fl = fc.layout(); fl.setSpacing(8)

        fhdr = QHBoxLayout()
        fhdr.addWidget(_SectionLabel("视频文件列表"))
        fhdr.addStretch()
        self._cnt_lbl = QLabel("0 个文件"); self._cnt_lbl.setObjectName("section_title")
        fhdr.addWidget(self._cnt_lbl)
        fl.addLayout(fhdr)

        self._file_list = _DropList()
        self._file_list.files_dropped.connect(self._add_paths)
        fl.addWidget(self._file_list, 1)

        br = QHBoxLayout(); br.setSpacing(6)
        add_btn = _mk_btn("＋ 添加文件")
        add_btn.clicked.connect(self._select_files)
        add_folder_btn = _mk_btn("📁 添加文件夹")
        add_folder_btn.clicked.connect(self._select_folder)
        rm_btn  = _mk_btn("✕ 删除选中", obj_name="danger")
        rm_btn.clicked.connect(self._remove_files)
        br.addWidget(add_btn); br.addWidget(add_folder_btn); br.addWidget(rm_btn); br.addStretch()
        fl.addLayout(br)
        body.addWidget(fc, 5)

        # ── 右：选项 + 操作 ───────────────────────────────────────────
        right = QVBoxLayout(); right.setSpacing(10)

        # 选项卡片
        oc = _Card()
        ol = oc.layout(); ol.setSpacing(10)
        ol.addWidget(_SectionLabel("分离选项"))
        ol.addWidget(_hline())

        # 提取内容选择
        ol.addWidget(_SectionLabel("提取内容"))
        self._extract_combo = QComboBox()
        self._extract_combo.setFixedHeight(_BTN_H)
        self._extract_combo.addItems([
            "仅提取音频",
            "仅提取视频（去除音频）",
            "同时提取音频 + 视频",
        ])
        self._extract_combo.setMinimumWidth(220)
        self._extract_combo.currentIndexChanged.connect(self._on_extract_changed)
        ol.addWidget(self._extract_combo)

        ol.addWidget(_hline())

        # 音频格式
        self._audio_fmt_row = QHBoxLayout()
        self._audio_fmt_row.addWidget(_SectionLabel("音频格式"))
        self._audio_fmt_combo = QComboBox()
        self._audio_fmt_combo.setFixedHeight(_BTN_H)
        self._audio_fmt_combo.addItems(AUDIO_ONLY_FMTS)
        self._audio_fmt_combo.setMinimumWidth(120)
        self._audio_fmt_row.addWidget(self._audio_fmt_combo)
        self._audio_fmt_row.addStretch()
        ol.addLayout(self._audio_fmt_row)

        # 视频格式
        self._video_fmt_row = QHBoxLayout()
        self._video_fmt_row.addWidget(_SectionLabel("视频格式"))
        self._video_fmt_combo = QComboBox()
        self._video_fmt_combo.setFixedHeight(_BTN_H)
        self._video_fmt_combo.addItems(VIDEO_ONLY_FMTS)
        self._video_fmt_combo.setMinimumWidth(120)
        self._video_fmt_row.addWidget(self._video_fmt_combo)
        self._video_fmt_row.addStretch()
        ol.addLayout(self._video_fmt_row)

        ol.addWidget(_hline())

        # 输出目录
        dir_row = QHBoxLayout(); dir_row.setSpacing(6)
        dir_row.addWidget(_SectionLabel("输出目录"))
        self._dir_edit = QLineEdit()
        self._dir_edit.setPlaceholderText("选择输出目录…")
        self._dir_edit.setReadOnly(True)
        self._dir_edit.setFixedHeight(_BTN_H)
        self._dir_edit.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        dir_row.addWidget(self._dir_edit, 1)
        dir_btn = _mk_btn("📁 选择", _BTN_W_SM)
        dir_btn.clicked.connect(self._select_dir)
        dir_row.addWidget(dir_btn)
        ol.addLayout(dir_row)

        right.addWidget(oc)

        # 操作卡片
        cc = _Card()
        cl = cc.layout(); cl.setSpacing(8)

        ar = QHBoxLayout(); ar.setSpacing(8)
        self._start_btn = _mk_btn("开始分离", _BTN_W_PRI, "primary")
        self._start_btn.setEnabled(False)
        self._start_btn.clicked.connect(self._start)
        self._cancel_btn = _mk_btn("取消", _BTN_W_SM, "danger")
        self._cancel_btn.setEnabled(False)
        self._cancel_btn.clicked.connect(lambda: self.cancel_sig.emit())
        ar.addWidget(self._start_btn); ar.addWidget(self._cancel_btn); ar.addStretch()
        cl.addLayout(ar)

        self._progress = QProgressBar()
        self._progress.setFixedHeight(10)
        self._progress.setValue(0)
        self._progress.setTextVisible(True)
        self._progress.setFormat("总进度: %p%")
        self._progress.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        cl.addWidget(self._progress)

        right.addWidget(cc)
        right.addStretch()
        body.addLayout(right, 4)
        root.addLayout(body, 3)

        # 日志
        root.addWidget(self._build_log_card(), 2)

        # 默认隐藏视频格式行（默认"仅提取音频"）
        self._on_extract_changed(0)

    # ── 文件操作 ──────────────────────────────────────────────────────
    def _select_files(self):
        paths, _ = QFileDialog.getOpenFileNames(self, "选择视频文件", "", _VIDEO_FILTER)
        if paths:
            self._files.clear()
            self._file_list.clear()
            self._add_paths(paths)

    def _select_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "选择视频文件夹")
        if not folder: return
        exts = {"mp4","mkv","avi","mov","wmv","flv","webm","ts","m2ts","vob"}
        paths = sorted(
            os.path.join(folder, f) for f in os.listdir(folder)
            if os.path.splitext(f)[1].lstrip(".").lower() in exts)
        if paths:
            self._files.clear()
            self._file_list.clear()
            self._add_paths(paths)
        else:
            self.log_message("文件夹中没有找到支持的视频文件", "warning")

    def _add_paths(self, paths):
        existing = set(self._files)
        added = 0
        for p in paths:
            if p not in existing:
                self._files.append(p)
                existing.add(p)
                sz = self._fmt_size(p)
                self._file_list.addItem(f"{os.path.basename(p)}  [{sz}]")
                if self._handler:
                    self._handler.get_file_info_ffprobe(p)
                added += 1
        if added:
            self.log_message(f"已添加 {added} 个文件", "info")
            self._update_state()
            self._cnt_lbl.setText(f"{len(self._files)} 个文件")
        else:
            self.log_message("所选文件已在列表中", "warning")

    def _remove_files(self):
        sel = self._file_list.selectedItems()
        if not sel:
            self.log_message("请先选中要删除的文件", "warning"); return
        for item in sel:
            row = self._file_list.row(item)
            if row < len(self._files):
                self._files.pop(row)
            self._file_list.takeItem(row)
        self._cnt_lbl.setText(f"{len(self._files)} 个文件")
        self._update_state()

    def _select_dir(self):
        d = QFileDialog.getExistingDirectory(self, "选择输出目录")
        if d:
            self._out_dir = d
            self._dir_edit.setText(d)
            self._update_state()

    def _update_state(self):
        ok = bool(self._files and self._out_dir)
        self._start_btn.setEnabled(ok)

    @staticmethod
    def _fmt_size(path):
        try:
            sz = os.path.getsize(path)
            return (f"{sz/1024/1024:.1f} MB" if sz > 1024*1024
                    else f"{sz/1024:.0f} KB")
        except OSError:
            return "?"

    # ── 选项联动 ──────────────────────────────────────────────────────
    def _on_extract_changed(self, idx: int):
        # 0=仅音频  1=仅视频  2=音频+视频
        show_audio = idx in (0, 2)
        show_video = idx in (1, 2)
        for i in range(self._audio_fmt_row.count()):
            w = self._audio_fmt_row.itemAt(i)
            if w and w.widget(): w.widget().setVisible(show_audio)
        for i in range(self._video_fmt_row.count()):
            w = self._video_fmt_row.itemAt(i)
            if w and w.widget(): w.widget().setVisible(show_video)

    # ── 开始处理 ──────────────────────────────────────────────────────
    def _start(self):
        if not self._files:
            self.log_message("请先添加视频文件", "error"); return
        if not self._out_dir:
            self.log_message("请选择输出目录", "error"); return

        extract_idx = self._extract_combo.currentIndex()
        audio_fmt   = self._audio_fmt_combo.currentText()
        video_fmt   = self._video_fmt_combo.currentText()

        # 构建任务列表
        self._tasks = []
        for inp in self._files:
            stem = os.path.splitext(os.path.basename(inp))[0]
            if extract_idx in (0, 2):   # 提取音频
                out  = os.path.join(self._out_dir, f"{stem}_audio.{audio_fmt}")
                args = _SPLIT_AUDIO_ARGS.get(audio_fmt, ["-vn"])
                self._tasks.append((inp, out, args))
            if extract_idx in (1, 2):   # 提取视频
                out  = os.path.join(self._out_dir, f"{stem}_video.{video_fmt}")
                args = _SPLIT_VIDEO_ARGS.get(video_fmt, ["-c:v", "copy", "-an"])
                self._tasks.append((inp, out, args))

        self._total = len(self._tasks)
        self._done  = 0
        self._progress.setValue(0)
        self._progress.setFormat(f"总进度: (0/{self._total})  %p%")
        self._start_btn.setEnabled(False)
        self._cancel_btn.setEnabled(True)
        self._clear_log()
        self.log_message(f"开始处理，共 {self._total} 个任务…", "info")

        for i, (inp, out, args) in enumerate(self._tasks):
            self.log_message(
                f"[{i+1}] {os.path.basename(inp)}  →  {os.path.basename(out)}", "info")
            self.task_ready.emit(i, inp, out, args)

    # ── 进度回调（由 MainWindow 调用） ────────────────────────────────
    def update_progress(self, idx: int, total: int, pct: int):
        if total == 0: return
        ppf = 100 / total
        val = int(idx * ppf + pct / 100 * ppf)
        self._progress.setValue(val)
        self._progress.setFormat(f"总进度: ({idx+1}/{total})  %p%")

    def on_task_finished(self, idx: int, status: str, msg: str):
        self._done += 1
        if status == "success":
            self.log_message(f"[{idx+1}] ✔ 完成: {msg}", "success")
        elif status == "cancelled":
            self.log_message(f"[{idx+1}] 已取消", "warning")
            self._finish_all()
            return
        else:
            self.log_message(f"[{idx+1}] ✖ 失败: {msg}", "error")

        if self._done >= self._total:
            self._finish_all()

    def _finish_all(self):
        self._start_btn.setEnabled(bool(self._files and self._out_dir))
        self._cancel_btn.setEnabled(False)
        self._progress.setValue(100)
        self.log_message("所有任务已处理完毕", "success")

    def _on_file_info(self, fp: str, info: dict, err: str):
        if fp not in self._files: return
        if err: return
        if info.get("streams"):
            has_v = any(s.get("codec_type") == "video" for s in info["streams"])
            has_a = any(s.get("codec_type") == "audio" for s in info["streams"])
            flags = []
            if has_v: flags.append("视频流")
            if has_a: flags.append("音频流")
            if flags:
                self.log_message(
                    f"{os.path.basename(fp)} — 包含: {' + '.join(flags)}", "meta")

    def set_theme(self, mode: str, bg_colors: dict = None):
        self._is_dark = (mode == "dark")


# ═══════════════════════════════════════════════════════════════════════
#  合成 Tab
# ═══════════════════════════════════════════════════════════════════════
class MergeTab(QWidget, _LogMixin):
    """
    将一条视频文件 + 一条音频文件合并为一个输出文件。
    支持批量：每行视频对应一行音频（顺序配对），也可 1 对 N（一个音频配多个视频）。
    """
    task_ready = pyqtSignal(int, str, str, list)   # 单任务：idx, -i v, -i a, out, args
    # 合并需要两个输入，用特殊信号传递
    merge_ready = pyqtSignal(int, str, str, str, list)  # idx, video, audio, out, args
    cancel_sig  = pyqtSignal()

    def __init__(self, ffmpeg_handler, parent=None):
        super().__init__(parent)
        self._handler        = ffmpeg_handler
        self._video_files: list = []
        self._audio_file: str   = ""
        self._out_dir: str      = ""
        self._total             = 0
        self._done              = 0
        self._is_dark           = False
        self._init_ui()

    # ── UI ────────────────────────────────────────────────────────────
    def _init_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(12, 10, 12, 10)
        root.setSpacing(10)

        body = QHBoxLayout(); body.setSpacing(10)

        # ── 左：两个文件列表 ──────────────────────────────────────────
        left = QVBoxLayout(); left.setSpacing(8)

        # 视频列表
        vc = _Card()
        vl = vc.layout(); vl.setSpacing(6)
        vhdr = QHBoxLayout()
        vhdr.addWidget(_SectionLabel("视频文件（可多个）"))
        vhdr.addStretch()
        self._v_cnt = QLabel("0 个"); self._v_cnt.setObjectName("section_title")
        vhdr.addWidget(self._v_cnt)
        vl.addLayout(vhdr)

        self._v_list = _DropList()
        self._v_list.files_dropped.connect(self._add_video)
        self._v_list.setMinimumHeight(80)
        vl.addWidget(self._v_list, 1)

        vbr = QHBoxLayout(); vbr.setSpacing(6)
        v_add = _mk_btn("＋ 添加视频")
        v_add.clicked.connect(self._select_video)
        v_rm  = _mk_btn("✕ 删除选中", obj_name="danger")
        v_rm.clicked.connect(self._remove_video)
        vbr.addWidget(v_add); vbr.addWidget(v_rm); vbr.addStretch()
        vl.addLayout(vbr)
        left.addWidget(vc, 3)

        # 音频（单个）
        ac = _Card()
        al = ac.layout(); al.setSpacing(6)
        al.addWidget(_SectionLabel("音频文件（单个，将配对给所有视频）"))

        self._a_edit = QLineEdit()
        self._a_edit.setPlaceholderText("选择音频文件…")
        self._a_edit.setReadOnly(True)
        self._a_edit.setFixedHeight(_BTN_H)
        al.addWidget(self._a_edit)

        abr = QHBoxLayout(); abr.setSpacing(6)
        a_add = _mk_btn("选择音频")
        a_add.clicked.connect(self._select_audio)
        a_rm  = _mk_btn("✕ 清除", obj_name="danger")
        a_rm.clicked.connect(self._clear_audio)
        abr.addWidget(a_add); abr.addWidget(a_rm); abr.addStretch()
        al.addLayout(abr)
        left.addWidget(ac, 1)

        body.addLayout(left, 5)

        # ── 右：选项 + 操作 ───────────────────────────────────────────
        right = QVBoxLayout(); right.setSpacing(10)

        oc = _Card()
        ol = oc.layout(); ol.setSpacing(10)
        ol.addWidget(_SectionLabel("合成选项"))
        ol.addWidget(_hline())

        # 输出格式
        fmt_row = QHBoxLayout(); fmt_row.setSpacing(8)
        fmt_row.addWidget(_SectionLabel("输出格式"))
        self._fmt_combo = QComboBox()
        self._fmt_combo.setFixedHeight(_BTN_H)
        self._fmt_combo.addItems(MERGE_FMTS)
        self._fmt_combo.setMinimumWidth(120)
        fmt_row.addWidget(self._fmt_combo); fmt_row.addStretch()
        ol.addLayout(fmt_row)

        # 音频处理选项
        ol.addWidget(_SectionLabel("音频处理"))
        self._audio_mode_combo = QComboBox()
        self._audio_mode_combo.setFixedHeight(_BTN_H)
        self._audio_mode_combo.addItems([
            "复制音频流（无损，推荐）",
            "重新编码为 M4A (AAC)",
            "重新编码为 AAC 192k",
            "重新编码为 MP3 192k",
            "重新编码为 FLAC（无损）",
            "重新编码为 Opus 96k",
        ])
        self._audio_mode_combo.setMinimumWidth(220)
        ol.addWidget(self._audio_mode_combo)

        ol.addWidget(_hline())

        # 输出目录
        dir_row = QHBoxLayout(); dir_row.setSpacing(6)
        dir_row.addWidget(_SectionLabel("输出目录"))
        self._dir_edit = QLineEdit()
        self._dir_edit.setPlaceholderText("选择输出目录…")
        self._dir_edit.setReadOnly(True)
        self._dir_edit.setFixedHeight(_BTN_H)
        self._dir_edit.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        dir_row.addWidget(self._dir_edit, 1)
        dir_btn = _mk_btn("📁 选择", _BTN_W_SM)
        dir_btn.clicked.connect(self._select_dir)
        dir_row.addWidget(dir_btn)
        ol.addLayout(dir_row)

        right.addWidget(oc)

        # 操作卡片
        cc = _Card()
        cl = cc.layout(); cl.setSpacing(8)

        ar = QHBoxLayout(); ar.setSpacing(8)
        self._start_btn = _mk_btn("开始合成", _BTN_W_PRI, "primary")
        self._start_btn.setEnabled(False)
        self._start_btn.clicked.connect(self._start)
        self._cancel_btn = _mk_btn("取消", _BTN_W_SM, "danger")
        self._cancel_btn.setEnabled(False)
        self._cancel_btn.clicked.connect(lambda: self.cancel_sig.emit())
        ar.addWidget(self._start_btn); ar.addWidget(self._cancel_btn); ar.addStretch()
        cl.addLayout(ar)

        self._progress = QProgressBar()
        self._progress.setFixedHeight(10)
        self._progress.setValue(0)
        self._progress.setTextVisible(True)
        self._progress.setFormat("总进度: %p%")
        self._progress.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        cl.addWidget(self._progress)

        right.addWidget(cc)
        right.addStretch()
        body.addLayout(right, 4)
        root.addLayout(body, 3)

        root.addWidget(self._build_log_card(), 2)

    # ── 文件操作 ──────────────────────────────────────────────────────
    def _select_video(self):
        paths, _ = QFileDialog.getOpenFileNames(self, "选择视频文件", "", _VIDEO_FILTER)
        if paths:
            self._video_files.clear()
            self._v_list.clear()
            self._add_video(paths)

    def _add_video(self, paths: list):
        existing = set(self._video_files)
        added = 0
        for p in paths:
            if p not in existing:
                self._video_files.append(p)
                existing.add(p)
                sz = self._fmt_size(p)
                self._v_list.addItem(f"{os.path.basename(p)}  [{sz}]")
                added += 1
        if added:
            self.log_message(f"已添加 {added} 个视频文件", "info")
            self._v_cnt.setText(f"{len(self._video_files)} 个")
            self._update_state()

    def _remove_video(self):
        sel = self._v_list.selectedItems()
        if not sel:
            self.log_message("请先选中要删除的视频", "warning"); return
        for item in sel:
            row = self._v_list.row(item)
            if row < len(self._video_files):
                self._video_files.pop(row)
            self._v_list.takeItem(row)
        self._v_cnt.setText(f"{len(self._video_files)} 个")
        self._update_state()

    def _select_audio(self):
        p, _ = QFileDialog.getOpenFileName(self, "选择音频文件", "", _AUDIO_FILTER)
        if p:
            self._audio_file = p
            self._a_edit.setText(os.path.basename(p))
            self.log_message(f"已选择音频: {os.path.basename(p)}", "info")
            self._update_state()

    def _clear_audio(self):
        self._audio_file = ""
        self._a_edit.clear()
        self._update_state()

    def _select_dir(self):
        d = QFileDialog.getExistingDirectory(self, "选择输出目录")
        if d:
            self._out_dir = d
            self._dir_edit.setText(d)
            self._update_state()

    def _update_state(self):
        ok = bool(self._video_files and self._audio_file and self._out_dir)
        self._start_btn.setEnabled(ok)

    @staticmethod
    def _fmt_size(path):
        try:
            sz = os.path.getsize(path)
            return (f"{sz/1024/1024:.1f} MB" if sz > 1024*1024
                    else f"{sz/1024:.0f} KB")
        except OSError:
            return "?"

    # ── 构建合成参数 ──────────────────────────────────────────────────
    def _build_merge_args(self, fmt: str) -> list:
        """根据格式和音频处理模式构建 ffmpeg 参数（不含 -i 和输出路径）。"""
        audio_mode = self._audio_mode_combo.currentIndex()
        base = _MERGE_ARGS.get(fmt, ["-c:v", "copy", "-c:a", "copy"])

        # 替换音频编码部分
        if audio_mode == 0:   # 复制流
            # 找到 -c:a 及其值，替换为 copy
            args = list(base)
            for i, a in enumerate(args):
                if a == "-c:a" and i+1 < len(args):
                    args[i+1] = "copy"
                    # 删掉后面的 -b:a（如果有）
                    while i+2 < len(args) and args[i+2] == "-b:a":
                        del args[i+2]; del args[i+2]
                    break
        elif audio_mode == 1:  # M4A (AAC)
            args = ["-c:v", "copy", "-c:a", "aac", "-b:a", "192k"]
            if fmt in ("mp4", "mov"):
                args += ["-movflags", "+faststart"]
        elif audio_mode == 2:  # AAC 192k
            args = ["-c:v", "copy", "-c:a", "aac", "-b:a", "192k"]
            if fmt in ("mp4", "mov"):
                args += ["-movflags", "+faststart"]
        elif audio_mode == 3:  # MP3 192k
            args = ["-c:v", "copy", "-c:a", "libmp3lame", "-b:a", "192k"]
        elif audio_mode == 4:  # FLAC
            args = ["-c:v", "copy", "-c:a", "flac"]
        else:                  # Opus
            args = ["-c:v", "copy", "-c:a", "libopus", "-b:a", "96k"]

        return args

    # ── 开始处理 ──────────────────────────────────────────────────────
    def _start(self):
        if not self._video_files:
            self.log_message("请先添加视频文件", "error"); return
        if not self._audio_file:
            self.log_message("请选择音频文件", "error"); return
        if not self._out_dir:
            self.log_message("请选择输出目录", "error"); return

        fmt  = self._fmt_combo.currentText()
        args = self._build_merge_args(fmt)

        self._total = len(self._video_files)
        self._done  = 0
        self._progress.setValue(0)
        self._progress.setFormat(f"总进度: (0/{self._total})  %p%")
        self._start_btn.setEnabled(False)
        self._cancel_btn.setEnabled(True)
        self._clear_log()
        self.log_message(f"开始合成，共 {self._total} 个任务…", "info")

        for i, vf in enumerate(self._video_files):
            stem = os.path.splitext(os.path.basename(vf))[0]
            out  = os.path.join(self._out_dir, f"{stem}_merged.{fmt}")
            self.log_message(
                f"[{i+1}] {os.path.basename(vf)} + {os.path.basename(self._audio_file)}"
                f"  →  {os.path.basename(out)}", "info")
            self.merge_ready.emit(i, vf, self._audio_file, out, args)

    # ── 进度回调 ──────────────────────────────────────────────────────
    def update_progress(self, idx: int, total: int, pct: int):
        if total == 0: return
        ppf = 100 / total
        val = int(idx * ppf + pct / 100 * ppf)
        self._progress.setValue(val)
        self._progress.setFormat(f"总进度: ({idx+1}/{total})  %p%")

    def on_task_finished(self, idx: int, status: str, msg: str):
        self._done += 1
        if status == "success":
            self.log_message(f"[{idx+1}] ✔ 完成: {msg}", "success")
        elif status == "cancelled":
            self.log_message(f"[{idx+1}] 已取消", "warning")
            self._finish_all(); return
        else:
            self.log_message(f"[{idx+1}] ✖ 失败: {msg}", "error")
        if self._done >= self._total:
            self._finish_all()

    def _finish_all(self):
        self._start_btn.setEnabled(
            bool(self._video_files and self._audio_file and self._out_dir))
        self._cancel_btn.setEnabled(False)
        self._progress.setValue(100)
        self.log_message("所有任务已处理完毕", "success")

    def set_theme(self, mode: str, bg_colors: dict = None):
        self._is_dark = (mode == "dark")


# ═══════════════════════════════════════════════════════════════════════
#  主页面（Tab 容器）
# ═══════════════════════════════════════════════════════════════════════
class AVSplitterPage(QWidget):
    """
    音视频分离/合成页面。

    对外暴露与其他转换页相同的信号接口：
      conversion_requested(idx, inp, args, stem)  — 普通单输入任务
      merge_requested(idx, video, audio, out, args) — 双输入合成任务
      cancel_conversion_signal()
    """
    conversion_requested     = pyqtSignal(int, str, list, str)   # 分离
    merge_requested          = pyqtSignal(int, str, str, str, list)  # 合成
    cancel_conversion_signal = pyqtSignal()

    def __init__(self, ffmpeg_handler, parent=None):
        super().__init__(parent)
        self._handler   = ffmpeg_handler
        self._is_dark   = False
        self._batch_page = None   # 当前活动子页（由 MainWindow 无需关心，内部自管）

        self._init_ui()

    def _init_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        self._tabs = QTabWidget()
        self._tabs.setDocumentMode(True)

        self.split_tab = SplitTab(self._handler)
        self.merge_tab = MergeTab(self._handler)

        self._tabs.addTab(self.split_tab, "分离音视频")
        self._tabs.addTab(self.merge_tab, "合成音视频")

        root.addWidget(self._tabs)

        # 把子 tab 的信号转发出去
        self.split_tab.task_ready.connect(self._on_split_task)
        self.split_tab.cancel_sig.connect(self.cancel_conversion_signal)
        self.merge_tab.merge_ready.connect(self._on_merge_task)
        self.merge_tab.cancel_sig.connect(self.cancel_conversion_signal)

    # ── 信号转发 ──────────────────────────────────────────────────────
    def _on_split_task(self, idx: int, inp: str, out: str, args: list):
        """分离任务：转换为 conversion_requested 信号（通过 stem 推导输出路径）。"""
        # stem 已经包含了后缀标记（_audio / _video），去掉最后的扩展名
        stem = os.path.splitext(os.path.basename(out))[0]
        self._batch_page = self.split_tab
        self.conversion_requested.emit(idx, inp, args, stem)

    def _on_merge_task(self, idx: int, video: str, audio: str, out: str, args: list):
        """合成任务：需要两个输入，走独立信号。"""
        self._batch_page = self.merge_tab
        self.merge_requested.emit(idx, video, audio, out, args)

    # ── MainWindow 回调接口 ───────────────────────────────────────────
    def log_ffmpeg_line(self, idx: int, kind: str, text: str):
        if self._batch_page:
            self._batch_page.log_ffmpeg_line(idx, kind, text)

    def log_message(self, msg: str, kind: str = "info"):
        if self._batch_page:
            self._batch_page.log_message(msg, kind)

    def update_overall_progress(self, idx: int, total: int, pct: int):
        if self._batch_page:
            self._batch_page.update_progress(idx, total, pct)

    def on_finished(self, idx: int, status: str, msg: str):
        if self._batch_page:
            self._batch_page.on_task_finished(idx, status, msg)

    def set_theme(self, mode: str, bg_colors: dict = None):
        self._is_dark = (mode == "dark")
        self.split_tab.set_theme(mode, bg_colors)
        self.merge_tab.set_theme(mode, bg_colors)
