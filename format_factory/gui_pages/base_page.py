# format_factory/gui_pages/base_page.py
import os
import html as _html_mod
import shlex
from datetime import datetime

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLineEdit,
    QComboBox, QLabel, QFileDialog, QTextEdit, QProgressBar,
    QListWidget, QAbstractItemView, QFrame, QSizePolicy, QApplication
)
from PyQt6.QtCore import pyqtSignal, Qt, QTimer, QMimeData
from PyQt6.QtGui import QFont, QDragEnterEvent, QDropEvent, QColor, QBrush

from ..config import (VIDEO_FORMATS, AUDIO_FORMATS, IMAGE_FORMATS,
                      M3U8_OUTPUT_FORMATS, DEFAULT_FFMPEG_ARGS)

# ── Size constants (match reference screenshot) ───────────────────
_BTN_H    = 32
_BTN_W    = 110
_BTN_W_SM = 80
_BTN_W_PRI= 130
_CTRL_H   = 32
_COMBO_W  = 140


# ═══════════════════════════════════════════════════════════════════
#  Helpers
# ═══════════════════════════════════════════════════════════════════
class SectionLabel(QLabel):
    def __init__(self, text, parent=None):
        super().__init__(text, parent)
        self.setObjectName("section_title")


class CardWidget(QFrame):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("card")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(14, 12, 14, 12)
        lay.setSpacing(8)

    def layout(self):      # convenience – returns inner QVBoxLayout
        return super().layout()


class AnimatedProgressBar(QProgressBar):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(10)
        self.setValue(0)
        self.setTextVisible(True)
        self.setFormat("总进度: %p%")
        self.setSizePolicy(QSizePolicy.Policy.Expanding,
                           QSizePolicy.Policy.Fixed)


class DropFileList(QListWidget):
    """File list that also accepts drag-and-drop."""
    files_dropped = pyqtSignal(list)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAcceptDrops(True)
        self.setSelectionMode(
            QAbstractItemView.SelectionMode.ExtendedSelection)
        self.setMinimumHeight(90)
        self.setSizePolicy(QSizePolicy.Policy.Expanding,
                           QSizePolicy.Policy.Expanding)

    def dragEnterEvent(self, e: QDragEnterEvent):
        if e.mimeData().hasUrls():
            e.acceptProposedAction()

    def dragMoveEvent(self, e):
        if e.mimeData().hasUrls():
            e.acceptProposedAction()

    def dropEvent(self, e: QDropEvent):
        paths = [u.toLocalFile() for u in e.mimeData().urls()
                 if u.isLocalFile()]
        if paths:
            self.files_dropped.emit(paths)


# ── Custom args panel ─────────────────────────────────────────────
class ArgsPanel(QWidget):
    # 通用备用预设（当没有专属预设时使用）
    _CUSTOM_ONLY = [("自定义…", "__custom__")]

    # 按输出格式细分的预设
    PRESETS_BY_FMT = {
        # ── 视频 ──────────────────────────────────────────────────────
        "mp4": [
            ("默认 (H.264 CRF23)",        []),
            ("高质量 (H.264 CRF18)",       ["-crf", "18"]),
            ("快速压缩 (H.264 CRF28)",     ["-crf", "28"]),
            ("极速编码 (ultrafast)",        ["-preset", "ultrafast", "-crf", "23"]),
            ("H.265 / HEVC (CRF28)",       ["-c:v", "libx265", "-preset", "medium",
                                            "-crf", "28", "-c:a", "aac", "-b:a", "192k"]),
            ("H.265 高质量 (CRF22)",       ["-c:v", "libx265", "-preset", "slow",
                                            "-crf", "22", "-c:a", "aac", "-b:a", "192k"]),
            ("无损 (H.264 lossless)",      ["-c:v", "libx264", "-preset", "medium",
                                            "-crf", "0", "-c:a", "pcm_s16le"]),
            ("仅视频流 (去除音频)",         ["-c:v", "copy", "-an"]),
            ("仅复制流 (超快无重编码)",     ["-c", "copy"]),
            ("自定义…",                    "__custom__"),
        ],
        "mkv": [
            ("默认 (H.264 CRF23)",        []),
            ("高质量 (H.264 CRF18)",       ["-crf", "18"]),
            ("快速压缩 (H.264 CRF28)",     ["-crf", "28"]),
            ("H.265 / HEVC (CRF28)",       ["-c:v", "libx265", "-preset", "medium",
                                            "-crf", "28", "-c:a", "aac", "-b:a", "192k"]),
            ("H.265 高质量 (CRF22)",       ["-c:v", "libx265", "-preset", "slow",
                                            "-crf", "22", "-c:a", "aac", "-b:a", "192k"]),
            ("AV1 (libaom, 慢速高压缩)",   ["-c:v", "libaom-av1", "-crf", "35", "-b:v", "0",
                                            "-c:a", "libopus", "-b:a", "128k"]),
            ("无损 (H.264 lossless)",      ["-c:v", "libx264", "-preset", "medium",
                                            "-crf", "0", "-c:a", "flac"]),
            ("仅视频流 (去除音频)",         ["-c:v", "copy", "-an"]),
            ("仅复制流 (超快无重编码)",     ["-c", "copy"]),
            ("自定义…",                    "__custom__"),
        ],
        "mov": [
            ("默认 (H.264 CRF23)",        []),
            ("高质量 (H.264 CRF18)",       ["-crf", "18"]),
            ("ProRes 422 (专业剪辑)",      ["-c:v", "prores_ks", "-profile:v", "2",
                                            "-c:a", "pcm_s16le"]),
            ("ProRes 4444 (最高质量)",     ["-c:v", "prores_ks", "-profile:v", "4",
                                            "-c:a", "pcm_s16le"]),
            ("仅视频流 (去除音频)",         ["-c:v", "copy", "-an"]),
            ("仅复制流 (超快无重编码)",     ["-c", "copy"]),
            ("自定义…",                    "__custom__"),
        ],
        "avi": [
            ("默认 (MPEG-4)",             []),
            ("高质量 (Q2)",               ["-c:v", "mpeg4", "-q:v", "2",
                                           "-c:a", "libmp3lame", "-q:a", "2"]),
            ("H.264 + MP3",              ["-c:v", "libx264", "-crf", "23",
                                          "-c:a", "libmp3lame", "-b:a", "192k"]),
            ("仅视频流 (去除音频)",        ["-c:v", "copy", "-an"]),
            ("仅复制流 (超快无重编码)",    ["-c", "copy"]),
            ("自定义…",                   "__custom__"),
        ],
        "webm": [
            ("默认 (VP9 CRF30)",          []),
            ("VP9 高质量 (CRF20)",         ["-c:v", "libvpx-vp9", "-crf", "20", "-b:v", "0",
                                            "-c:a", "libopus", "-b:a", "192k"]),
            ("VP9 快速压缩 (CRF40)",       ["-c:v", "libvpx-vp9", "-crf", "40", "-b:v", "0",
                                            "-c:a", "libopus", "-b:a", "96k"]),
            ("AV1 (libaom, 慢速高压缩)",   ["-c:v", "libaom-av1", "-crf", "35", "-b:v", "0",
                                            "-c:a", "libopus", "-b:a", "128k"]),
            ("仅视频流 (去除音频)",         ["-c:v", "libvpx-vp9", "-crf", "30", "-b:v", "0", "-an"]),
            ("自定义…",                    "__custom__"),
        ],
        "flv": [
            ("默认 (H.264 CRF23)",        []),
            ("高质量 (CRF18)",             ["-c:v", "libx264", "-preset", "medium",
                                            "-crf", "18", "-c:a", "aac", "-b:a", "192k"]),
            ("低码率 (CRF28)",             ["-c:v", "libx264", "-preset", "fast",
                                            "-crf", "28", "-c:a", "aac", "-b:a", "96k"]),
            ("仅复制流 (超快无重编码)",     ["-c", "copy"]),
            ("自定义…",                    "__custom__"),
        ],
        "gif": [
            ("默认 (10fps 320px)",         []),
            ("高帧率 (15fps 480px)",       ["-vf", "fps=15,scale=480:-1:flags=lanczos",
                                            "-loop", "0"]),
            ("高清大图 (15fps 720px)",     ["-vf", "fps=15,scale=720:-1:flags=lanczos",
                                            "-loop", "0"]),
            ("小体积 (8fps 240px)",        ["-vf", "fps=8,scale=240:-1:flags=lanczos",
                                            "-loop", "0"]),
            ("超小体积 (6fps 160px)",      ["-vf", "fps=6,scale=160:-1:flags=lanczos",
                                            "-loop", "0"]),
            ("循环播放",                   ["-loop", "0"]),
            ("播放一次",                   ["-loop", "1"]),
            ("自定义…",                    "__custom__"),
        ],
        # ── M3U8 ──────────────────────────────────────────────────────
        "m3u8": [
            ("默认 (复制流)",              []),
            ("自定义…",                    "__custom__"),
        ],
        # ── 音频 ──────────────────────────────────────────────────────
        "mp3": [
            ("默认 (192k)",               []),
            ("高质量 (320k)",              ["-b:a", "320k"]),
            ("高质量 VBR (V0)",            ["-c:a", "libmp3lame", "-q:a", "0"]),
            ("标准 VBR (V4)",              ["-c:a", "libmp3lame", "-q:a", "4"]),
            ("低码率 (128k)",              ["-b:a", "128k"]),
            ("低码率 (96k)",               ["-b:a", "96k"]),
            ("仅提取音频 (复制流)",         ["-c:a", "copy", "-vn"]),
            ("自定义…",                    "__custom__"),
        ],
        "m4a": [
            ("默认 (AAC 192k)",            []),
            ("高质量 (AAC 320k)",          ["-b:a", "320k"]),
            ("无损 ALAC (Apple Lossless)", ["-c:a", "alac"]),
            ("低码率 (AAC 128k)",          ["-b:a", "128k"]),
            ("仅提取音频 (复制流)",         ["-c:a", "copy", "-vn"]),
            ("自定义…",                    "__custom__"),
        ],
        "aac": [
            ("默认 (192k)",               []),
            ("高质量 (320k)",              ["-b:a", "320k"]),
            ("标准 (128k)",               ["-b:a", "128k"]),
            ("低码率 (96k)",               ["-b:a", "96k"]),
            ("仅提取音频 (复制流)",         ["-c:a", "copy", "-vn"]),
            ("自定义…",                    "__custom__"),
        ],
        "wav": [
            ("默认 (PCM 16bit)",           []),
            ("PCM 24bit",                  ["-c:a", "pcm_s24le"]),
            ("PCM 32bit",                  ["-c:a", "pcm_s32le"]),
            ("PCM 浮点 32bit",             ["-c:a", "pcm_f32le"]),
            ("仅提取音频 (复制流)",         ["-c:a", "copy", "-vn"]),
            ("自定义…",                    "__custom__"),
        ],
        "flac": [
            ("默认 (压缩级别 5)",           []),
            ("最高压缩 (级别 8)",           ["-c:a", "flac", "-compression_level", "8"]),
            ("最快压缩 (级别 0)",           ["-c:a", "flac", "-compression_level", "0"]),
            ("仅提取音频 (复制流)",         ["-c:a", "copy", "-vn"]),
            ("自定义…",                    "__custom__"),
        ],
        "ogg": [
            ("默认 (Vorbis Q4)",           []),
            ("高质量 (Q8)",                ["-c:a", "libvorbis", "-q:a", "8"]),
            ("标准 (Q6)",                  ["-c:a", "libvorbis", "-q:a", "6"]),
            ("低码率 (Q2)",                ["-c:a", "libvorbis", "-q:a", "2"]),
            ("仅提取音频 (复制流)",         ["-c:a", "copy", "-vn"]),
            ("自定义…",                    "__custom__"),
        ],
        "opus": [
            ("默认 (96k)",                 []),
            ("高质量 (192k)",              ["-c:a", "libopus", "-b:a", "192k"]),
            ("标准 (128k)",               ["-c:a", "libopus", "-b:a", "128k"]),
            ("低码率 (64k)",               ["-c:a", "libopus", "-b:a", "64k"]),
            ("极低码率 (32k)",             ["-c:a", "libopus", "-b:a", "32k"]),
            ("仅提取音频 (复制流)",         ["-c:a", "copy", "-vn"]),
            ("自定义…",                    "__custom__"),
        ],
        # ── 图片 ──────────────────────────────────────────────────────
        "jpg": [
            ("默认 (Q2)",                  []),
            ("高质量 (Q1)",                ["-q:v", "1"]),
            ("标准 (Q3)",                  ["-q:v", "3"]),
            ("压缩 (Q5)",                  ["-q:v", "5"]),
            ("缩放 1920px 宽",             ["-vf", "scale=1920:-1:flags=lanczos", "-q:v", "2"]),
            ("缩放 1280px 宽",             ["-vf", "scale=1280:-1:flags=lanczos", "-q:v", "2"]),
            ("缩放 800px 宽",              ["-vf", "scale=800:-1:flags=lanczos",  "-q:v", "2"]),
            ("缩放 512px 宽",              ["-vf", "scale=512:-1:flags=lanczos",  "-q:v", "3"]),
            ("自定义…",                    "__custom__"),
        ],
        "png": [
            ("默认",                       []),
            ("最大压缩 (级别 9)",           ["-compression_level", "9"]),
            ("无压缩 (级别 0)",             ["-compression_level", "0"]),
            ("缩放 1920px 宽",             ["-vf", "scale=1920:-1:flags=lanczos"]),
            ("缩放 1280px 宽",             ["-vf", "scale=1280:-1:flags=lanczos"]),
            ("缩放 800px 宽",              ["-vf", "scale=800:-1:flags=lanczos"]),
            ("缩放 512px 宽",              ["-vf", "scale=512:-1:flags=lanczos"]),
            ("自定义…",                    "__custom__"),
        ],
        "webp": [
            ("默认 (Q85)",                 []),
            ("高质量 (Q95)",               ["-quality", "95"]),
            ("有损压缩 (Q60)",             ["-quality", "60"]),
            ("极小体积 (Q40)",             ["-quality", "40"]),
            ("缩放 1920px 宽",             ["-vf", "scale=1920:-1:flags=lanczos", "-quality", "85"]),
            ("缩放 1280px 宽",             ["-vf", "scale=1280:-1:flags=lanczos", "-quality", "85"]),
            ("缩放 800px 宽",              ["-vf", "scale=800:-1:flags=lanczos",  "-quality", "85"]),
            ("自定义…",                    "__custom__"),
        ],
        "bmp": [
            ("默认",                       []),
            ("缩放 1920px 宽",             ["-vf", "scale=1920:-1:flags=lanczos"]),
            ("缩放 1280px 宽",             ["-vf", "scale=1280:-1:flags=lanczos"]),
            ("缩放 800px 宽",              ["-vf", "scale=800:-1:flags=lanczos"]),
            ("缩放 512px 宽",              ["-vf", "scale=512:-1:flags=lanczos"]),
            ("自定义…",                    "__custom__"),
        ],
        "tiff": [
            ("默认",                       []),
            ("LZW 无损压缩",               ["-compression_algo", "lzw"]),
            ("Deflate 压缩",               ["-compression_algo", "deflate"]),
            ("缩放 1920px 宽",             ["-vf", "scale=1920:-1:flags=lanczos"]),
            ("缩放 1280px 宽",             ["-vf", "scale=1280:-1:flags=lanczos"]),
            ("自定义…",                    "__custom__"),
        ],
        "ico": [
            ("默认 (256x256)",             []),
            ("128x128",                    ["-vf", "scale=128:128:flags=lanczos"]),
            ("64x64",                      ["-vf", "scale=64:64:flags=lanczos"]),
            ("32x32",                      ["-vf", "scale=32:32:flags=lanczos"]),
            ("16x16",                      ["-vf", "scale=16:16:flags=lanczos"]),
            ("自定义…",                    "__custom__"),
        ],
    }

    # 媒体类型级别的回退预设（格式没有专属预设时使用）
    PRESETS = {
        "video": [
            ("默认 (H.264 CRF23)",        []),
            ("高质量 (H.264 CRF18)",       ["-crf", "18"]),
            ("仅复制流 (超快无重编码)",     ["-c", "copy"]),
            ("自定义…",                    "__custom__"),
        ],
        "audio": [
            ("默认 (192k)",               []),
            ("高质量 (320k)",              ["-b:a", "320k"]),
            ("低码率 (96k)",               ["-b:a", "96k"]),
            ("自定义…",                    "__custom__"),
        ],
        "image": [
            ("默认",                       []),
            ("自定义…",                    "__custom__"),
        ],
        "m3u8": [
            ("默认 (复制流)",              []),
            ("自定义…",                    "__custom__"),
        ],
    }

    # 各媒体类型的默认初始格式（与 output_format_combo 第0项一致）
    _DEFAULT_FMT = {"video": "mp4", "audio": "mp3", "image": "jpg", "m3u8": "mp4"}

    def __init__(self, media_type, parent=None):
        super().__init__(parent)
        self.media_type   = media_type
        self._gpu_vendor  = "none"   # 由 MainWindow 通过 set_gpu_vendor() 更新
        # 优先用该媒体类型默认格式的专属预设，回退才用媒体类型级别预设
        _default_fmt = self._DEFAULT_FMT.get(media_type, "")
        self._cur_presets = (
            self.PRESETS_BY_FMT.get(_default_fmt)
            or self.PRESETS.get(media_type, self.PRESETS["video"])
        )
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(4)

        row = QHBoxLayout(); row.setSpacing(8)
        row.addWidget(SectionLabel("预设 / 参数"))
        self.preset_combo = QComboBox()
        self.preset_combo.setMinimumSize(_COMBO_W, _CTRL_H)
        self._fill_combo()
        self.preset_combo.currentIndexChanged.connect(self._on_preset)
        row.addWidget(self.preset_combo)
        row.addStretch()
        lay.addLayout(row)

        self.extra_edit = QLineEdit()
        self.extra_edit.setPlaceholderText(
            "额外 FFmpeg 参数（留空则使用预设）")
        self.extra_edit.setMinimumHeight(_CTRL_H)
        self.extra_edit.setVisible(False)
        lay.addWidget(self.extra_edit)

    # GPU vendor → 支持的编码角色（与 settings_page.py 保持同步）
    _GPU_ROLES = {
        "nvidia": {"h264", "hevc"},
        "amd":    {"h264", "hevc"},
        "intel":  {"h264", "hevc"},
        "none":   set(),
    }
    # 预设名称 → 对应的编码角色（None = 纯 CPU / 流复制 / 音频/图片预设）
    _PRESET_ROLE = {
        # H.264 系列
        "默认 (H.264 CRF23)":       "h264",
        "高质量 (H.264 CRF18)":      "h264",
        "快速压缩 (H.264 CRF28)":    "h264",
        "极速编码 (ultrafast)":       "h264",
        "H.264 + MP3":               "h264",
        "默认 (MPEG-4)":             None,    # mpeg4 编码器 GPU 不支持
        "高质量 (Q2)":               None,
        # H.265/HEVC 系列
        "H.265 / HEVC (CRF28)":     "hevc",
        "H.265 高质量 (CRF22)":     "hevc",
        # AV1 — 目前主流 GPU 不支持 libaom-av1
        "AV1 (libaom, 慢速高压缩)": None,
        # ProRes — GPU 不支持
        "ProRes 422 (专业剪辑)":    None,
        "ProRes 4444 (最高质量)":   None,
        # 无损 lossless — 硬件编码器不支持 CRF 0
        "无损 (H.264 lossless)":    None,
        # 复制流 / 去音频 — 不需要编码
        "仅视频流 (去除音频)":       None,
        "仅复制流 (超快无重编码)":   None,
        # VP9/WebM — GPU 不支持 libvpx-vp9
        "默认 (VP9 CRF30)":         None,
        "VP9 高质量 (CRF20)":       None,
        "VP9 快速压缩 (CRF40)":     None,
    }

    def set_gpu_vendor(self, vendor: str):
        """由 MainWindow 在 GPU 设置变更时调用，静默更新内部状态。"""
        self._gpu_vendor = vendor

    def _preset_label(self, name: str) -> str:
        return name

    def _fill_combo(self):
        """清空并重新填充预设下拉，保持当前选中位置。"""
        cur_idx = self.preset_combo.currentIndex() \
            if hasattr(self, "preset_combo") else 0
        self.preset_combo.blockSignals(True)
        self.preset_combo.clear()
        for name, _ in self._cur_presets:
            self.preset_combo.addItem(self._preset_label(name))
        self.preset_combo.setCurrentIndex(
            max(0, min(cur_idx, self.preset_combo.count() - 1)))
        self.preset_combo.blockSignals(False)
        self.extra_edit.setVisible(self.is_custom_override()) \
            if hasattr(self, "extra_edit") else None

    def set_output_fmt(self, fmt: str):
        """根据输出格式切换预设列表，重置为第 0 项。"""
        new_presets = self.PRESETS_BY_FMT.get(fmt)
        if new_presets is None:
            new_presets = self.PRESETS.get(self.media_type, self._CUSTOM_ONLY)
        if new_presets is self._cur_presets:
            return
        self._cur_presets = new_presets
        self.preset_combo.blockSignals(True)
        self.preset_combo.clear()
        for name, _ in self._cur_presets:
            self.preset_combo.addItem(self._preset_label(name))
        self.preset_combo.setCurrentIndex(0)
        self.preset_combo.blockSignals(False)
        self.extra_edit.setVisible(False)

    def _on_preset(self, _):
        self.extra_edit.setVisible(self.is_custom_override())

    def is_custom_override(self):
        idx = self.preset_combo.currentIndex()
        if idx < 0 or idx >= len(self._cur_presets):
            return False
        return self._cur_presets[idx][1] == "__custom__"

    def get_extra_args(self):
        if self.is_custom_override():
            raw = self.extra_edit.text().strip()
            try:
                return shlex.split(raw, posix=False) if raw else []
            except ValueError:
                return raw.split() if raw else []
        idx = self.preset_combo.currentIndex()
        if 0 <= idx < len(self._cur_presets):
            v = self._cur_presets[idx][1]
            return [] if v == "__custom__" else (v or [])
        return []


# ═══════════════════════════════════════════════════════════════════
#  Base converter page
# ═══════════════════════════════════════════════════════════════════
class BaseConverterPage(QWidget):
    conversion_requested     = pyqtSignal(int, str, list, str)
    cancel_conversion_signal = pyqtSignal()

    def __init__(self, media_type, ffmpeg_handler, parent=None):
        super().__init__(parent)
        self.media_type     = media_type
        self.ffmpeg_handler = ffmpeg_handler
        self.input_files    = []
        self.output_dir     = ""
        self._is_dark       = False   # updated by MainWindow._apply_theme
        self.output_formats_available = self._get_fmts(media_type)
        self.file_original_formats    = {}
        self._init_ui()
        self._connect_internal_signals()

    # ── helpers ──────────────────────────────
    def _get_fmts(self, mt):
        return {"video": VIDEO_FORMATS, "audio": AUDIO_FORMATS,
                "image": IMAGE_FORMATS, "m3u8": M3U8_OUTPUT_FORMATS}.get(mt, [])

    def _media_label(self):
        return {"video": "视频", "audio": "音频",
                "image": "图片", "m3u8": "M3U8"}.get(self.media_type, "文件")

    def _get_file_filter(self):
        return "所有文件 (*.*)"

    def _mk_btn(self, text, min_w=_BTN_W, obj_name=""):
        b = QPushButton(text)
        b.setMinimumSize(min_w, _BTN_H)
        b.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        if obj_name:
            b.setObjectName(obj_name)
        return b

    # ── UI ───────────────────────────────────
    def _init_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(14, 12, 14, 12)
        root.setSpacing(10)

        # ══ 上半区：左列（文件）+ 右列（选项+操作）横向分栏 ══
        body = QHBoxLayout()
        body.setSpacing(10)

        # ── 左列：文件列表卡片 ──────────────────────────────
        file_card = CardWidget()
        fl = file_card.layout()
        fl.setSpacing(8)

        file_hdr = QHBoxLayout()
        self.input_label = SectionLabel(f"文件列表")
        file_hdr.addWidget(self.input_label)
        file_hdr.addStretch()
        # 文件计数标签
        self._file_count_lbl = QLabel("0 个文件")
        self._file_count_lbl.setObjectName("section_title")
        file_hdr.addWidget(self._file_count_lbl)
        fl.addLayout(file_hdr)

        self.input_file_list_widget = DropFileList()
        self.input_file_list_widget.files_dropped.connect(self._on_files_dropped)
        self.input_file_list_widget.setMinimumHeight(120)
        fl.addWidget(self.input_file_list_widget, 1)

        br = QHBoxLayout(); br.setSpacing(6)
        self.select_input_files_button = self._mk_btn("＋ 添加文件")
        self.select_input_files_button.setToolTip("选择文件（追加到当前列表）")
        self.select_input_files_button.clicked.connect(self._select_files)
        self.select_input_folder_button = self._mk_btn("添加文件夹")
        self.select_input_folder_button.setToolTip("选择文件夹，把其中所有支持的文件添加到列表")
        self.select_input_folder_button.clicked.connect(self._select_folder)
        self.remove_selected_files_button = self._mk_btn(
            "删除选中", obj_name="danger")
        self.remove_selected_files_button.setToolTip("移除选中的文件")
        self.remove_selected_files_button.clicked.connect(self._remove_files)
        br.addWidget(self.select_input_files_button)
        br.addWidget(self.select_input_folder_button)
        br.addWidget(self.remove_selected_files_button)
        br.addStretch()
        fl.addLayout(br)

        body.addWidget(file_card, 5)

        # ── 右列：选项卡片 + 操作卡片（垂直堆叠）──────────────
        right_col = QVBoxLayout()
        right_col.setSpacing(10)

        # 输出选项卡片
        opt_card = CardWidget()
        ol = opt_card.layout()
        ol.setSpacing(10)
        ol.addWidget(SectionLabel("输出选项"))

        # 格式行（视频时追加分辨率下拉）
        fmt_row = QHBoxLayout(); fmt_row.setSpacing(8)
        fmt_row.addWidget(SectionLabel("格式"))
        self.output_format_combo = QComboBox()
        self.output_format_combo.setFixedHeight(_CTRL_H)
        self.output_format_combo.setMinimumWidth(_COMBO_W)
        self.output_format_combo.addItems(self.output_formats_available)
        self.output_format_combo.currentIndexChanged.connect(self._on_fmt_changed)
        fmt_row.addWidget(self.output_format_combo)

        if self.media_type == "video":
            fmt_row.addWidget(SectionLabel("分辨率"))
            self.resolution_combo = QComboBox()
            self.resolution_combo.setFixedHeight(_CTRL_H)
            self.resolution_combo.setMinimumWidth(_COMBO_W)
            self.resolution_combo.addItems([
                "原始分辨率",
                "3840×2160  (4K)",
                "2560×1440  (2K)",
                "1920×1080  (1080p)",
                "1280×720   (720p)",
                "854×480    (480p)",
                "640×360    (360p)",
                "426×240    (240p)",
            ])
            fmt_row.addWidget(self.resolution_combo)
        else:
            self.resolution_combo = None

        fmt_row.addStretch()
        ol.addLayout(fmt_row)

        # 目录行
        dir_row = QHBoxLayout(); dir_row.setSpacing(6)
        dir_row.addWidget(SectionLabel("目录"))
        self.output_dir_edit = QLineEdit()
        self.output_dir_edit.setPlaceholderText("选择输出目录…")
        self.output_dir_edit.setReadOnly(True)
        self.output_dir_edit.setFixedHeight(_CTRL_H)
        self.output_dir_edit.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        dir_row.addWidget(self.output_dir_edit, 1)
        self.select_output_dir_button = self._mk_btn("选择", _BTN_W_SM)
        self.select_output_dir_button.clicked.connect(self._select_dir)
        dir_row.addWidget(self.select_output_dir_button)
        ol.addLayout(dir_row)

        # 分隔线 + 参数面板
        self._hline(ol)
        self.args_panel = ArgsPanel(self.media_type)
        ol.addWidget(self.args_panel)

        right_col.addWidget(opt_card)

        # 操作卡片（开始/取消 + 进度条）
        ctrl_card = CardWidget()
        cl = ctrl_card.layout()
        cl.setSpacing(8)

        ar = QHBoxLayout(); ar.setSpacing(8)
        self.start_conversion_button = self._mk_btn(
            "▶  开始转换", min_w=_BTN_W_PRI, obj_name="primary")
        self.start_conversion_button.setEnabled(False)
        self.start_conversion_button.clicked.connect(self._start_clicked)
        self.cancel_conversion_button = self._mk_btn(
            "⏹  取消", min_w=_BTN_W_SM, obj_name="danger")
        self.cancel_conversion_button.setEnabled(False)
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
        root.addLayout(body, 3)

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

        root.addWidget(log_card, 2)

    def _hline(self, layout):
        f = QFrame()
        f.setFrameShape(QFrame.Shape.HLine)
        layout.addWidget(f)

    # ── Signals ──────────────────────────────
    def _connect_internal_signals(self):
        if self.ffmpeg_handler:
            self.ffmpeg_handler.file_info_ready.connect(
                self.handle_file_info_ready)

    # ── File ops ─────────────────────────────
    def _select_files(self):
        paths, _ = QFileDialog.getOpenFileNames(
            self, f"选择{self._media_label()}文件", "",
            self._get_file_filter())
        if paths:
            self._clear_file_list()
            self._add_paths(paths)

    def _select_folder(self):
        folder = QFileDialog.getExistingDirectory(self, f"选择{self._media_label()}文件夹")
        if not folder:
            return
        # 从文件过滤器里提取支持的后缀
        exts = set()
        flt = self._get_file_filter()
        import re as _re2
        for m in _re2.finditer(r'\*\.(\w+)', flt):
            exts.add(m.group(1).lower())
        paths = []
        for fname in os.listdir(folder):
            ext = fname.rsplit(".", 1)[-1].lower() if "." in fname else ""
            if ext in exts:
                paths.append(os.path.join(folder, fname))
        if paths:
            self._clear_file_list()
            self._add_paths(sorted(paths))
        else:
            self.log_message(f"文件夹中没有找到支持的{self._media_label()}文件", "warning")

    def _clear_file_list(self):
        self.input_files.clear()
        self.file_original_formats.clear()
        self.input_file_list_widget.clear()
        self.overall_progress_bar.setValue(0)
        self._update_state()
        self._update_file_count()

    def _on_files_dropped(self, paths):
        """拖入文件时追加到当前列表。"""
        self._add_paths(paths)

    def _update_file_count(self):
        n = len(self.input_files)
        if hasattr(self, "_file_count_lbl"):
            self._file_count_lbl.setText(f"{n} 个文件" if n else "0 个文件")

    @staticmethod
    def _fmt_size(path):
        try:
            sz = os.path.getsize(path)
            if sz >= 1024 * 1024 * 1024:
                return f"{sz/1024/1024/1024:.2f} GB"
            if sz >= 1024 * 1024:
                return f"{sz/1024/1024:.1f} MB"
            if sz >= 1024:
                return f"{sz/1024:.0f} KB"
            return f"{sz} B"
        except OSError:
            return "?"

    def _add_paths(self, paths):
        existing = set(self.input_files)
        added = 0
        for p in paths:
            if p not in existing:
                self.input_files.append(p)
                existing.add(p)
                sz = self._fmt_size(p)
                label = f"{os.path.basename(p)}  [{sz}]"
                self.input_file_list_widget.addItem(label)
                if self.ffmpeg_handler:
                    self.ffmpeg_handler.get_file_info_ffprobe(p)
                added += 1
        if added:
            self.log_message(f"已添加 {added} 个文件", "info")
            self._update_state()
            self._update_combo()
            self._update_file_count()
        else:
            self.log_message("所选文件已在列表中", "warning")

    def _remove_files(self):
        sel = self.input_file_list_widget.selectedItems()
        if not sel:
            self.log_message("请先选中要删除的文件", "warning")
            return
        for item in sel:
            row = self.input_file_list_widget.row(item)
            if row < len(self.input_files):
                fp = self.input_files.pop(row)
                self.file_original_formats.pop(fp, None)
            self.input_file_list_widget.takeItem(row)
        self.overall_progress_bar.setValue(0)
        self._update_state()
        self._update_combo()
        self._update_file_count()

    def _select_dir(self):
        d = QFileDialog.getExistingDirectory(self, "选择输出目录")
        if d:
            self.output_dir = d
            self.output_dir_edit.setText(d)
            self._update_state()

    # ── Conversion ───────────────────────────
    def _on_fmt_changed(self, _):
        fmt = self.output_format_combo.currentText()
        self.args_panel.set_output_fmt(fmt)
        self._update_state()

    def _start_clicked(self):
        if not self.input_files:
            self.log_message("请先添加输入文件", "error"); return
        if not self.output_dir:
            self.log_message("请选择输出目录", "error"); return
        self._clear_log()
        self._progress_line.clear()
        self.log_message(f"开始转换 {len(self.input_files)} 个文件…", "info")
        self.start_conversion_button.setEnabled(False)
        self.cancel_conversion_button.setEnabled(True)
        self.overall_progress_bar.setValue(0)
        self._start_conversion_process()

    def _cancel_clicked(self):
        self.log_message("正在请求取消…", "warning")
        self.cancel_conversion_signal.emit()

    def _start_conversion_process(self):
        pass   # override in subclass

    def _build_args(self, fmt: str) -> list:
        default = DEFAULT_FFMPEG_ARGS.get(
            self.media_type, {}).get(fmt, [])
        extra = self.args_panel.get_extra_args()
        args = extra if self.args_panel.is_custom_override() \
               else default + extra

        # 分辨率注入（仅视频页有 resolution_combo）
        res_combo = getattr(self, "resolution_combo", None)
        if res_combo is not None:
            idx = res_combo.currentIndex()
            _RES_MAP = {
                1: "3840:2160",
                2: "2560:1440",
                3: "1920:1080",
                4: "1280:720",
                5: "854:480",
                6: "640:360",
                7: "426:240",
            }
            scale = _RES_MAP.get(idx)
            if scale and "-vf" not in args:
                args = args + ["-vf", f"scale={scale}"]

        return args

    # ═══════════════════════════════════════════════════════════════
    #  LOG SYSTEM
    #
    #  Rules that prevent the "disappearing dots / text" bug:
    #   1. All text appended via appendHtml() wrapped in a full <p>.
    #   2. Message content is HTML-escaped before insertion so special
    #      characters (·, ✔, &, <, >, etc.) never trigger Qt's HTML
    #      parser to eat or mangle characters.
    #   3. Progress/live lines go ONLY to _progress_line (QLabel),
    #      they never touch the QTextEdit at all.
    #   4. We never call removeSelectedText() or deletePreviousChar()
    #      on the QTextEdit — those are the direct cause of the bug.
    # ═══════════════════════════════════════════════════════════════

    # ── Log colour palettes（无背景时回退用）─────────────────────────
    # Light mode fallback: vivid mid-tone colours, readable on white
    _KIND_LIGHT = {
        "error":    ("#DC2626", "✖"),   # 红 600
        "warning":  ("#D97706", "⚠"),   # 琥珀 600
        "success":  ("#16A34A", "✔"),   # 绿 600
        "info":     ("#2563EB", "ℹ"),   # 蓝 600
        "cmd":      ("#9333EA", "$"),   # 紫 600
        "meta":     ("#0284C7", "📋"),  # 天蓝 600
        "encoder":  ("#84CC16", "⚙"),  # 黄绿 500
        "warn":     ("#DC2626", "⚠"),   # 同 error
    }
    # Dark mode fallback: soft pastels, readable on dark background
    _KIND_DARK = {
        "error":    ("#FCA5A5", "✖"),   # soft red
        "warning":  ("#FCD34D", "⚠"),   # warm yellow
        "success":  ("#6EE7B7", "✔"),   # mint green
        "info":     ("#93C5FD", "ℹ"),   # sky blue
        "cmd":      ("#C4B5FD", "$"),   # light violet
        "meta":     ("#7DD3FC", "📋"),  # light blue
        "encoder":  ("#BEF264", "⚙"),  # light lime
        "warn":     ("#FCA5A5", "⚠"),  # same as error
    }

    # 各日志类型的色相偏移（相对互补色）和图标
    _KIND_OFFSETS = {
        "error":   (0.00, "✖"),
        "warning": (0.08, "⚠"),
        "success": (0.33, "✔"),
        "info":    (0.17, "ℹ"),
        "cmd":     (0.75, "$"),
        "meta":    (0.58, "📋"),
        "encoder": (0.25, "⚙"),
        "warn":    (0.00, "⚠"),
    }

    def set_theme(self, mode: str, bg_colors: dict = None):
        """Called by MainWindow when light/dark mode or background changes."""
        self._is_dark   = (mode == "dark")
        self._bg_colors = bg_colors or {}

    def _kind_style(self, kind: str):
        """
        动态计算日志颜色。

        有背景图片时（亮色/暗色均适用）：
          以图片平均色的互补色为基础，按语义偏移色相，
          亮色模式用高饱和中亮度，暗色模式用中饱和高亮度。

        无背景图片时：回退固定调色板（_KIND_LIGHT / _KIND_DARK）。
        """
        import colorsys
        is_dark = getattr(self, "_is_dark", False)
        bg      = getattr(self, "_bg_colors", {})
        dom_hue = bg.get("dom_hue", 0.0)   # 0.0 = 无背景 / 无彩色

        # ── 无背景：用固定调色板 ──────────────────────────────────────
        if not dom_hue and not bg.get("complement_hex"):
            palette = self._KIND_DARK if is_dark else self._KIND_LIGHT
            return palette.get(kind, ("#71717A" if is_dark else "#52525B", "·"))

        # ── 有背景：基于平均色动态计算互补色系 ─────────────────────────
        # 互补色色相 = dom_hue + 0.5
        comp = (dom_hue + 0.5) % 1.0
        offset, icon = self._KIND_OFFSETS.get(kind, (0.0, "·"))
        hue = (comp + offset) % 1.0

        if is_dark:
            # 暗色模式：饱和度中等、明度高 → 鲜亮柔和
            sat, val = 0.70, 0.95
        else:
            # 亮色模式：饱和度高、明度适中 → 鲜艳但不过曝
            sat, val = 0.88, 0.72

        r, g, b = colorsys.hsv_to_rgb(hue, sat, val)
        colour = "#{:02X}{:02X}{:02X}".format(
            int(r * 255), int(g * 255), int(b * 255))
        return colour, icon

    def _append_log_row(self, ts: str, colour: str, icon: str, text: str):
        """
        Append ONE log row to the QTextEdit.
        text is HTML-escaped here so caller never needs to escape it.
        """
        safe   = _html_mod.escape(text)
        ts_col = "#A1A1AA" if getattr(self, "_is_dark", False) else "#52525B"
        row = (
            f'<p style="margin:1px 0;">'
            f'<span style="color:{ts_col};font-size:10px">[{ts}]</span>&nbsp;'
            f'<span style="color:{colour};font-weight:600">{icon}&nbsp;{safe}</span>'
            f'</p>'
        )
        self.log_display.append(row)
        self._scroll_log()

    def log_message(self, msg: str, kind: str = "info"):
        """System-level log entry (queue events, results, errors…)."""
        ts = datetime.now().strftime("%H:%M:%S")
        colour, icon = self._kind_style(kind)
        self._append_log_row(ts, colour, icon, msg)

    def log_ffmpeg_line(self, idx: int, kind: str, text: str):
        """
        Structured FFmpeg log line.

        progress → _progress_line label ONLY.  QTextEdit untouched.
        others   → _append_log_row() with escaped text.
        """
        ts = datetime.now().strftime("%H:%M:%S")

        if kind == "progress":
            safe = _html_mod.escape(text)
            prog_col = "#D97706" if getattr(self, "_is_dark", False) else "#92400E"
            ts_col   = "#A1A1AA" if getattr(self, "_is_dark", False) else "#52525B"
            self._progress_line.setText(
                f'<span style="color:{ts_col};font-size:10px">[{ts}]</span>&nbsp;'
                f'<span style="color:{prog_col};font-size:11px;font-weight:600">⟳&nbsp;{safe}</span>'
            )
        else:
            colour, icon = self._kind_style(kind)
            self._append_log_row(ts, colour, icon, text)

    def _scroll_log(self):
        QTimer.singleShot(0, lambda:
            self.log_display.verticalScrollBar().setValue(
                self.log_display.verticalScrollBar().maximum()))

    def _clear_log(self):
        self.log_display.clear()
        self._progress_line.clear()

    def _copy_log(self):
        QApplication.clipboard().setText(self.log_display.toPlainText())
        self._btn_copy_log.setText("✔ 已复制")
        QTimer.singleShot(1500,
            lambda: self._btn_copy_log.setText("⎘ 复制"))

    # ── Progress bar ─────────────────────────
    def update_overall_progress(self, idx, total, pct):
        if total == 0:
            return
        ppf = 100 / total
        self.overall_progress_bar.setValue(
            int(idx * ppf + pct / 100 * ppf))
        self.overall_progress_bar.setFormat(
            f"总进度: ({idx+1}/{total})  %p%")

    # ── State / combo ─────────────────────────
    def _update_state(self):
        ok = bool(self.input_files and self.output_dir
                  and self.output_format_combo.currentText())
        self.start_conversion_button.setEnabled(ok)

    def _update_combo(self):
        is_dark = getattr(self, "_is_dark", False)
        disabled_bg = QColor(60, 60, 70)    if is_dark else QColor(210, 210, 215)
        disabled_fg = QColor(100, 100, 110) if is_dark else QColor(150, 150, 158)
        normal_bg   = QColor(0, 0, 0, 0)

        for i in range(self.output_format_combo.count()):
            fmt  = self.output_format_combo.itemText(i)
            item = self.output_format_combo.model().item(i)
            if self.media_type == "m3u8":
                item.setEnabled(True)
                item.setBackground(QBrush(normal_bg))
                continue

            disable = bool(self.input_files) and all(
                self.file_original_formats.get(fp) == fmt
                for fp in self.input_files)

            item.setEnabled(not disable)
            if disable:
                item.setBackground(QBrush(disabled_bg))
                item.setForeground(QBrush(disabled_fg))
            else:
                item.setBackground(QBrush(normal_bg))
                item.setData(None, Qt.ItemDataRole.ForegroundRole)

            if self.output_format_combo.currentIndex() == i and disable:
                for j in range(self.output_format_combo.count()):
                    if self.output_format_combo.model().item(j).isEnabled():
                        self.output_format_combo.setCurrentIndex(j)
                        break

    def handle_file_info_ready(self, fp, info, err):
        if fp not in self.input_files:
            return
        if err:
            self.log_message(f"解析失败: {os.path.basename(fp)}", "warning")
            return

        fmt = ""
        # ffprobe format_name 可能是逗号分隔的多个格式，取最符合的
        if "format" in info and "format_name" in info["format"]:
            candidates = info["format"]["format_name"].split(",")
            ext = os.path.splitext(fp)[1].lstrip(".").lower()
            # 1. 优先：候选中与文件扩展名映射结果一致的
            ext_mapped = self._map(ext)
            for c in candidates:
                mapped = self._map(c.strip())
                if mapped == ext_mapped and mapped in self.output_formats_available:
                    fmt = mapped
                    break
            # 2. 次选：候选中任意匹配格式列表的
            if not fmt:
                for c in candidates:
                    mapped = self._map(c.strip())
                    if mapped in self.output_formats_available:
                        fmt = mapped
                        break
            # 3. 兜底：取第一个候选映射
            if not fmt:
                fmt = self._map(candidates[0].strip())
        # 如果 format 没命中，尝试从 streams[0] 读 codec_name（图片常见路径）
        if not fmt and info.get("streams"):
            fmt = self._map(info["streams"][0].get("codec_name", ""))
        # 最后兜底：从文件扩展名推断
        if not fmt:
            ext = os.path.splitext(fp)[1].lstrip(".").lower()
            fmt = self._map(ext)

        if fmt:
            self.file_original_formats[fp] = fmt
            name = os.path.basename(fp)
            self.log_message(f"检测到格式: {name}  →  {fmt.upper()}", "meta")
        self._update_combo()

    def _map(self, fmt):
        M = {
            # 视频容器
            "mov": "mov", "qt": "mov",
            "mp4": "mp4", "m4v": "mp4",
            "isom": "mp4", "isom": "mp4", "iso2": "mp4",   # ISO Base Media
            "f4v": "mp4", "f4a": "mp4",
            "3gp": "mp4", "3g2": "mp4", "3gpp": "mp4",
            "mkv": "mkv", "matroska": "mkv",
            "webm": "webm",
            "avi": "avi", "vfw": "avi",
            "flv": "flv", "flv1": "flv",
            "gif": "gif", "gif_pipe": "gif",
            "hevc": "mkv", "h264": "mp4", "h265": "mkv",  # raw bitstream → 容器
            "ts": "mp4", "mpegts": "mp4",                  # TS 流 → mp4
            "mpeg": "avi", "mpegvideo": "avi",
            "rm": "avi", "rmvb": "avi",                    # RealMedia → avi 兜底
            "asf": "mkv", "wmv": "mkv",                   # WMV → mkv
            "vob": "mp4", "dvd": "mp4",
            # 音频
            "mp3": "mp3", "mp2": "mp3", "mp2a": "mp3",
            "wav": "wav", "pcm_s16le": "wav", "pcm_s16be": "wav",
            "pcm_s24le": "wav", "pcm_s32le": "wav", "pcm_f32le": "wav",
            "pcm": "wav",
            "flac": "flac",
            "aac": "aac", "m4a": "m4a", "adts": "aac",   # ADTS 裸流
            "ogg": "ogg", "ogv": "ogg", "oga": "ogg", "vorbis": "ogg",
            "opus": "opus",
            "wma": "ogg", "wmav2": "ogg",                 # WMA → ogg 兜底
            "amr": "aac", "amr_nb": "aac", "amr_wb": "aac",
            "ac3": "aac", "eac3": "aac",
            "dts": "flac",
            # 图片
            "jpeg": "jpg", "jpg": "jpg", "mjpeg": "jpg", "jpeg_pipe": "jpg",
            "png": "png", "png_pipe": "png",
            "webp": "webp", "webp_pipe": "webp",
            "bmp": "bmp", "bmp_pipe": "bmp", "dib": "bmp",
            "tiff": "tiff", "tif": "tiff", "tiff_pipe": "tiff",
            "ico": "ico", "icon": "ico", "ico_pipe": "ico",
            "gif_pipe": "gif",
        }
        return M.get(fmt.lower(), fmt.lower())