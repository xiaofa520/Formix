# format_factory/gui_pages/settings_page.py
"""
设置页  —  手动选择 GPU 厂商（无自动检测），双列布局。
"""
import os
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QLabel, QPushButton, QComboBox, QFileDialog,
    QFrame, QSizePolicy, QScrollArea, QButtonGroup, QSlider
)
from PyQt6.QtCore import pyqtSignal, Qt
from PyQt6.QtGui import QPixmap, QFont

from .base_page import CardWidget, SectionLabel, _BTN_H, _CTRL_H
from ..config import APP_VERSION

# GPU 厂商信息
GPU_VENDORS = {
    "none":   {"label": "不使用 GPU",        "icon": "🖥",  "color": "#94a3b8"},
    "nvidia": {"label": "NVIDIA  (NVENC)",    "icon": "🟢",  "color": "#76b900"},
    "amd":    {"label": "AMD  (AMF)",         "icon": "🔴",  "color": "#ed1c24"},
    "intel":  {"label": "Intel  (Quick Sync)","icon": "🔵",  "color": "#0071c5"},
}

# GPU 对应的 ffmpeg 编码器
# supported_roles: GPU 能加速的编码角色集合，其余预设自动回退 CPU
GPU_ENCODERS = {
    "nvidia": {"h264": "h264_nvenc",  "hevc": "hevc_nvenc",
               "extra": ["-rc", "vbr", "-cq", "23", "-b:v", "0"],
               "label": "NVIDIA NVENC",
               "supported_roles": {"h264", "hevc"}},
    "amd":    {"h264": "h264_amf",    "hevc": "hevc_amf",
               "extra": ["-quality", "balanced"],
               "label": "AMD AMF",
               "supported_roles": {"h264", "hevc"}},
    "intel":  {"h264": "h264_qsv",    "hevc": "hevc_qsv",
               "extra": ["-global_quality", "23"],
               "label": "Intel Quick Sync",
               "supported_roles": {"h264", "hevc"}},
}


class SettingsPage(QWidget):
    # ── 所有信号必须在类体顶层 ───────────────────────────────────────
    theme_changed        = pyqtSignal(str)
    blur_changed         = pyqtSignal(int)
    mask_opacity_changed = pyqtSignal(int)
    bg_image_changed     = pyqtSignal(str)
    bg_clear_requested   = pyqtSignal()     # 用户点击 ✕ 清除背景（含关闭每日壁纸）
    gpu_vendor_changed   = pyqtSignal(str)
    daily_wallpaper_toggled = pyqtSignal(bool)
    daily_wallpaper_refresh = pyqtSignal()
    check_update_requested  = pyqtSignal()

    def __init__(self, current_theme="light", current_blur=0,
                 current_bg="", gpu_vendor="none",
                 daily_enabled=False, mask_opacity=50, parent=None):
        super().__init__(parent)
        self._theme        = current_theme
        self._blur         = current_blur          # 0-20
        self._mask_opacity = mask_opacity          # 0-100
        self._bg_path      = current_bg
        self._vendor       = gpu_vendor
        self._is_dark      = (current_theme == "dark")
        self._daily_enabled = daily_enabled
        self._init_ui()
        self._refresh_daily_ui()

    # ── Public ───────────────────────────────────────────────────────
    def set_theme(self, mode: str, bg_colors: dict = None):
        self._is_dark = (mode == "dark")

    def current_vendor(self) -> str:
        return self._vendor

    # ── UI ───────────────────────────────────────────────────────────
    def _init_ui(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        outer.addWidget(scroll)

        inner = QWidget()
        scroll.setWidget(inner)

        root = QVBoxLayout(inner)
        root.setContentsMargins(20, 16, 20, 20)
        root.setSpacing(10)

        # ── 第一行：外观  +  GPU 设置（左右并排）
        row1 = QHBoxLayout(); row1.setSpacing(10)
        row1.addWidget(self._build_appearance_card(), 5)
        row1.addWidget(self._build_gpu_card(),        5)
        root.addLayout(row1)

        # ── 第二行：关于 + 软件更新（左右并排）
        row2 = QHBoxLayout(); row2.setSpacing(10)
        row2.addWidget(self._build_about_card(),  4)
        row2.addWidget(self._build_update_card(), 6)
        root.addLayout(row2)
        root.addStretch()

    # ── 外观卡片 ─────────────────────────────────────────────────────
    def _build_appearance_card(self) -> CardWidget:
        card = CardWidget()
        lay  = card.layout()
        lay.setSpacing(12)

        lay.addWidget(SectionLabel("外观"))

        # 主题切换
        lay.addWidget(self._row_label("颜色模式"))
        t_row = QHBoxLayout(); t_row.setSpacing(6); t_row.setContentsMargins(0,0,0,0)

        self.light_btn = QPushButton("亮色")
        self.light_btn.setObjectName("toggle_light")
        self.light_btn.setFixedHeight(_BTN_H)
        self.light_btn.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.light_btn.clicked.connect(lambda: self._set_theme("light"))

        self.dark_btn = QPushButton("深色")
        self.dark_btn.setObjectName("toggle_dark")
        self.dark_btn.setFixedHeight(_BTN_H)
        self.dark_btn.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.dark_btn.clicked.connect(lambda: self._set_theme("dark"))

        t_row.addWidget(self.light_btn, 1)
        t_row.addWidget(self.dark_btn,  1)
        lay.addLayout(t_row)

        lay.addWidget(self._div())

        # 毛玻璃模糊强度（滑块 0-20）
        lay.addWidget(self._row_label("毛玻璃模糊"))
        blur_row = QHBoxLayout(); blur_row.setSpacing(8); blur_row.setContentsMargins(0,0,0,0)
        self.blur_slider = QSlider(Qt.Orientation.Horizontal)
        self.blur_slider.setMinimum(0)
        self.blur_slider.setMaximum(20)
        self.blur_slider.setValue(self._blur)
        self.blur_slider.setTickInterval(5)
        self.blur_slider.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.blur_val_lbl = QLabel(f"{self._blur}")
        self.blur_val_lbl.setObjectName("section_title")
        self.blur_val_lbl.setFixedWidth(28)
        self.blur_val_lbl.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        blur_hint = QLabel("需先设置背景图")
        blur_hint.setObjectName("section_title")
        blur_row.addWidget(self.blur_slider, 1)
        blur_row.addWidget(self.blur_val_lbl)
        blur_row.addWidget(blur_hint)
        self.blur_slider.valueChanged.connect(self._on_blur)
        lay.addLayout(blur_row)

        lay.addWidget(self._div())

        # 遮罩透明度（滑块 0-100）
        lay.addWidget(self._row_label("背景遮罩透明度"))
        mask_row = QHBoxLayout(); mask_row.setSpacing(8); mask_row.setContentsMargins(0,0,0,0)
        self.mask_slider = QSlider(Qt.Orientation.Horizontal)
        self.mask_slider.setMinimum(0)
        self.mask_slider.setMaximum(100)
        self.mask_slider.setValue(self._mask_opacity)
        self.mask_slider.setTickInterval(10)
        self.mask_slider.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.mask_val_lbl = QLabel(f"{self._mask_opacity}%")
        self.mask_val_lbl.setObjectName("section_title")
        self.mask_val_lbl.setFixedWidth(36)
        self.mask_val_lbl.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        mask_hint = QLabel("0=全透明  100=最深")
        mask_hint.setObjectName("section_title")
        mask_row.addWidget(self.mask_slider, 1)
        mask_row.addWidget(self.mask_val_lbl)
        mask_row.addWidget(mask_hint)
        self.mask_slider.valueChanged.connect(self._on_mask_opacity)
        lay.addLayout(mask_row)

        lay.addWidget(self._div())

        # 背景图片
        lay.addWidget(SectionLabel("背景图片"))
        bg_row = QHBoxLayout(); bg_row.setSpacing(6); bg_row.setContentsMargins(0,0,0,0)

        self.bg_lbl = QLabel("未设置")
        self.bg_lbl.setObjectName("section_title")
        self.bg_lbl.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self.bg_lbl.setMaximumWidth(180)

        self.choose_btn = QPushButton("选择图片")
        self.choose_btn.setFixedHeight(_BTN_H)
        self.choose_btn.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self.choose_btn.clicked.connect(self._choose_bg)

        self.clear_btn = QPushButton("✕")
        self.clear_btn.setObjectName("danger")
        self.clear_btn.setFixedSize(34, _BTN_H)
        self.clear_btn.clicked.connect(self._clear_bg)

        bg_row.addWidget(self.bg_lbl, 1)
        bg_row.addWidget(self.choose_btn)
        bg_row.addWidget(self.clear_btn)
        lay.addLayout(bg_row)

        # 预览缩略图
        self.preview = QLabel()
        self.preview.setFixedHeight(64)
        self.preview.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        self.preview.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        lay.addWidget(self.preview)

        lay.addWidget(self._div())

        # ── 每日壁纸 ──────────────────────────────────────────────
        lay.addWidget(SectionLabel("每日壁纸"))

        daily_info = QLabel("自动每天零点从 API 获取一张壁纸作为背景图")
        daily_info.setObjectName("section_title")
        daily_info.setWordWrap(True)
        lay.addWidget(daily_info)

        daily_row = QHBoxLayout(); daily_row.setSpacing(6); daily_row.setContentsMargins(0,0,0,0)

        self.daily_toggle_btn = QPushButton("启用每日壁纸")
        self.daily_toggle_btn.setFixedHeight(_BTN_H)
        self.daily_toggle_btn.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.daily_toggle_btn.clicked.connect(self._on_daily_toggle)

        self.daily_refresh_btn = QPushButton("立即刷新")
        self.daily_refresh_btn.setFixedHeight(_BTN_H)
        self.daily_refresh_btn.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self.daily_refresh_btn.setEnabled(False)
        self.daily_refresh_btn.clicked.connect(self._on_daily_refresh)

        daily_row.addWidget(self.daily_toggle_btn, 1)
        daily_row.addWidget(self.daily_refresh_btn)
        lay.addLayout(daily_row)

        self.daily_status_lbl = QLabel("未启用")
        self.daily_status_lbl.setObjectName("section_title")
        self.daily_status_lbl.setWordWrap(True)
        lay.addWidget(self.daily_status_lbl)
        lay.addStretch()

        if self._bg_path and os.path.isfile(self._bg_path):
            self.bg_lbl.setText(os.path.basename(self._bg_path))
            self._refresh_preview()

        return card

    # ── GPU 设置卡片 ─────────────────────────────────────────────────
    def _build_gpu_card(self) -> CardWidget:
        card = CardWidget()
        lay  = card.layout()
        lay.setSpacing(12)

        lay.addWidget(SectionLabel("GPU 硬件加速"))

        # 说明文字
        info_lbl = QLabel(
            "选择显卡厂商后，视频转换将自动使用 GPU 编码器，\n"
            "速度提升 3–10×。需要 FFmpeg 编译了对应编码器。"
        )
        info_lbl.setObjectName("section_title")
        info_lbl.setWordWrap(True)
        lay.addWidget(info_lbl)

        lay.addWidget(self._div())

        # 四个厂商按钮
        lay.addWidget(self._row_label("选择 GPU 厂商"))

        # 上排：NVIDIA  AMD
        row_a = QHBoxLayout(); row_a.setSpacing(8); row_a.setContentsMargins(0,0,0,0)
        # 下排：Intel   不使用
        row_b = QHBoxLayout(); row_b.setSpacing(8); row_b.setContentsMargins(0,0,0,0)

        self._vendor_btns = {}
        order_a = ["nvidia", "amd"]
        order_b = ["intel",  "none"]

        for vendor in order_a:
            btn = self._make_vendor_btn(vendor)
            self._vendor_btns[vendor] = btn
            row_a.addWidget(btn, 1)

        for vendor in order_b:
            btn = self._make_vendor_btn(vendor)
            self._vendor_btns[vendor] = btn
            row_b.addWidget(btn, 1)

        lay.addLayout(row_a)
        lay.addLayout(row_b)

        lay.addWidget(self._div())

        # 当前状态标签
        self._gpu_status_lbl = QLabel()
        self._gpu_status_lbl.setWordWrap(True)
        self._gpu_status_lbl.setObjectName("section_title")
        lay.addWidget(self._gpu_status_lbl)

        # 编码器信息网格
        enc_grid = QGridLayout(); enc_grid.setSpacing(4)
        enc_grid.setColumnStretch(1, 1)

        self._enc_h264_lbl = QLabel("—")
        self._enc_hevc_lbl = QLabel("—")
        for col, (k, v) in enumerate(
                [("H.264 编码器", self._enc_h264_lbl),
                 ("H.265 编码器", self._enc_hevc_lbl)]):
            r = col
            lbl = QLabel(k); lbl.setObjectName("section_title")
            enc_grid.addWidget(lbl, r, 0)
            enc_grid.addWidget(v,   r, 1)

        lay.addLayout(enc_grid)
        lay.addStretch()

        # 初始刷新
        self._refresh_vendor_buttons()
        self._refresh_encoder_labels()
        return card

    def _make_vendor_btn(self, vendor: str) -> QPushButton:
        info = GPU_VENDORS[vendor]
        btn  = QPushButton(f"{info['icon']}  {info['label']}")
        btn.setFixedHeight(38)
        btn.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        btn.setObjectName(f"vendor_btn_{vendor}")
        btn.clicked.connect(lambda _=False, v=vendor: self._set_vendor(v))
        return btn

    # ── 关于卡片 ─────────────────────────────────────────────────────
    def _build_about_card(self) -> CardWidget:
        card = CardWidget()
        lay  = card.layout()
        lay.setSpacing(10)

        lay.addWidget(SectionLabel("关于"))

        # 版本行：版本号 + 内联状态徽标（RichText 动态更新）
        self._about_txt_lbl = QLabel()
        self._about_txt_lbl.setTextFormat(Qt.TextFormat.RichText)
        self._about_txt_lbl.setWordWrap(True)
        self._about_badge = ""   # 动态部分，空=检查中
        self._refresh_about_txt()
        lay.addWidget(self._about_txt_lbl)

        lay.addStretch()
        return card

    # ── 软件更新卡片 ──────────────────────────────────────────────────
    def _build_update_card(self) -> CardWidget:
        card = CardWidget()
        lay  = card.layout()
        lay.setSpacing(10)

        lay.addWidget(SectionLabel("软件更新"))

        # 按钮行
        update_row = QHBoxLayout()
        update_row.setSpacing(6)
        update_row.setContentsMargins(0, 0, 0, 0)

        self._check_update_btn = QPushButton("🔍 检查更新")
        self._check_update_btn.setFixedHeight(_BTN_H)
        self._check_update_btn.setSizePolicy(
            QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self._check_update_btn.clicked.connect(self._on_check_update)

        self._update_status_lbl = QLabel('点击"检查更新"以获取最新版本信息')
        self._update_status_lbl.setObjectName("section_title")
        self._update_status_lbl.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)

        update_row.addWidget(self._check_update_btn)
        update_row.addWidget(self._update_status_lbl, 1)
        lay.addLayout(update_row)

        # 更新公告区（带滚动条）
        lay.addWidget(self._row_label("更新公告"))
        self._update_notes_lbl = QLabel("")
        self._update_notes_lbl.setObjectName("section_title")
        self._update_notes_lbl.setTextFormat(Qt.TextFormat.RichText)
        self._update_notes_lbl.setWordWrap(True)
        self._update_notes_lbl.setAlignment(
            Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        self._update_notes_lbl.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)

        notes_scroll = QScrollArea()
        notes_scroll.setWidgetResizable(True)
        notes_scroll.setFrameShape(QFrame.Shape.NoFrame)
        notes_scroll.setMinimumHeight(100)
        notes_scroll.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        notes_scroll.setWidget(self._update_notes_lbl)
        lay.addWidget(notes_scroll, 1)

        # 内部记录版本列表（兼容 populate_versions 空实现）
        self._version_map: dict = {}

        return card

    # ── 状态刷新 ─────────────────────────────────────────────────────
    def _refresh_vendor_buttons(self):
        for vendor, btn in self._vendor_btns.items():
            active = (vendor == self._vendor)
            name   = f"vendor_btn_{vendor}_active" if active else f"vendor_btn_{vendor}"
            btn.setObjectName(name)
            btn.style().unpolish(btn)
            btn.style().polish(btn)

    def _refresh_encoder_labels(self):
        enc = GPU_ENCODERS.get(self._vendor, {})
        info = GPU_VENDORS[self._vendor]
        if self._vendor == "none":
            self._gpu_status_lbl.setText("🖥  当前使用 CPU 软件编码（速度慢但兼容性最好）")
            self._enc_h264_lbl.setText("— (libx264)")
            self._enc_hevc_lbl.setText("— (libx265)")
        else:
            self._gpu_status_lbl.setText(
                f"{info['icon']}  已选择 {info['label']} — "
                f"若 FFmpeg 未编译该编码器转换将失败")
            self._enc_h264_lbl.setText(enc.get("h264", "—"))
            self._enc_hevc_lbl.setText(enc.get("hevc", "—"))

    # ── 事件处理 ─────────────────────────────────────────────────────
    def _set_vendor(self, vendor: str):
        self._vendor = vendor
        self._refresh_vendor_buttons()
        self._refresh_encoder_labels()
        self.gpu_vendor_changed.emit(vendor)

    def _set_theme(self, mode: str):
        self._theme   = mode
        self._is_dark = (mode == "dark")
        self.theme_changed.emit(mode)

    def _choose_bg(self):
        p, _ = QFileDialog.getOpenFileName(
            self, "选择背景图片", "",
            "图片文件 (*.jpg *.jpeg *.png *.bmp *.webp);;所有文件 (*.*)")
        if p:
            self._bg_path = p
            self.bg_lbl.setText(os.path.basename(p))
            self._refresh_preview()
            self.bg_image_changed.emit(p)

    def _clear_bg(self):
        self._bg_path = ""
        self.bg_lbl.setText("未设置")
        self.preview.clear()
        self.bg_image_changed.emit("")
        self.bg_clear_requested.emit()   # 通知 MainWindow 同时关闭每日壁纸

    def _refresh_preview(self):
        if self._bg_path and os.path.isfile(self._bg_path):
            pix = QPixmap(self._bg_path)
            if not pix.isNull():
                self.preview.setPixmap(
                    pix.scaledToHeight(60,
                        Qt.TransformationMode.SmoothTransformation))
                return
        self.preview.clear()

    def _on_blur(self, val: int):
        self._blur = val
        self.blur_val_lbl.setText(f"{val}")
        self.blur_changed.emit(val)

    def _on_mask_opacity(self, val: int):
        self._mask_opacity = val
        self.mask_val_lbl.setText(f"{val}%")
        self.mask_opacity_changed.emit(val)

    def _on_daily_toggle(self):
        self._daily_enabled = not self._daily_enabled
        self._refresh_daily_ui()
        self.daily_wallpaper_toggled.emit(self._daily_enabled)

    def _on_daily_refresh(self):
        self.daily_wallpaper_refresh.emit()

    def _refresh_daily_ui(self):
        if self._daily_enabled:
            self.daily_toggle_btn.setText("禁用每日壁纸")
            self.daily_refresh_btn.setEnabled(True)
        else:
            self.daily_toggle_btn.setText("启用每日壁纸")
            self.daily_refresh_btn.setEnabled(False)
            self.daily_status_lbl.setText("未启用")

    def set_daily_status(self, msg: str):
        """由 MainWindow 调用，更新状态文字。"""
        if hasattr(self, "daily_status_lbl"):
            self.daily_status_lbl.setText(msg)

    def set_daily_bg_preview(self, path: str):
        """壁纸下载完成后更新背景图预览。"""
        if path and os.path.isfile(path):
            self._bg_path = path
            self.bg_lbl.setText(os.path.basename(path))
            self._refresh_preview()

    # ── 更新事件 ─────────────────────────────────────────────────────
    def _refresh_about_txt(self):
        """重新渲染关于标签（版本 + 内联徽标）。"""
        if not hasattr(self, "_about_txt_lbl"):
            return
        badge = f"  {self._about_badge}" if self._about_badge else ""
        self._about_txt_lbl.setText(
            f"<b>Formix（格式转换通）</b>  v{APP_VERSION}{badge} 　·　 基于 FFmpeg 的多媒体批量转换工具<br>"
            "<span style='opacity:0.55'>"
            "视频 · 音频 · 图片 · M3U8 · 批量队列 · GPU 加速"
            "</span>"
        )

    def _on_check_update(self):
        self._check_update_btn.setEnabled(False)
        self._update_status_lbl.setText("正在检查更新…")
        self.check_update_requested.emit()

    def set_update_status(self, msg: str):
        """由 MainWindow 调用，更新检查结果文字，并重新启用按钮。"""
        if hasattr(self, "_update_status_lbl"):
            self._update_status_lbl.setText(msg)
        if hasattr(self, "_check_update_btn"):
            self._check_update_btn.setEnabled(True)

    def set_update_notes(self, notes: str):
        """由 MainWindow 调用，在更新公告区显示版本说明。"""
        if hasattr(self, "_update_notes_lbl"):
            self._update_notes_lbl.setText(notes)

    def set_version_badge(self, has_update: bool, latest_ver: str = ""):
        """由 MainWindow 调用，在版本号旁边显示更新状态括号标注。"""
        if has_update:
            self._about_badge = f"（<span style='color:#e67e22'>有新版本 v{latest_ver} 可更新</span>）"
        else:
            self._about_badge = "（<span style='color:#27ae60'>最新版</span>）"
        self._refresh_about_txt()

    def populate_versions(self, versions: list):
        """保留空实现，降级功能已移除。"""
        pass

    # ── 辅助 ─────────────────────────────────────────────────────────
    @staticmethod
    def _div():
        f = QFrame(); f.setFrameShape(QFrame.Shape.HLine); return f

    @staticmethod
    def _row_label(text: str) -> QLabel:
        lbl = QLabel(text)
        lbl.setObjectName("row_label")
        return lbl