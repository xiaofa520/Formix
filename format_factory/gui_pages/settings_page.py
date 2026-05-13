# format_factory/gui_pages/settings_page.py
"""
设置页  —  手动选择 GPU 厂商（无自动检测），双列布局。
"""
import os
import webbrowser
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QLabel, QPushButton, QComboBox, QFileDialog, QCheckBox,
    QFrame, QSizePolicy, QScrollArea, QButtonGroup, QSlider, QLineEdit,
    QTextBrowser
)
from PyQt6.QtCore import pyqtSignal, Qt, QSize
from PyQt6.QtGui import QPixmap, QFont, QIcon, QPainter
try:
    from PyQt6.QtSvg import QSvgRenderer
except ImportError:  # pragma: no cover - QtSvg may be unavailable in some environments
    QSvgRenderer = None

from .base_page import CardWidget, SectionLabel, NoWheelComboBox, _BTN_H, _CTRL_H
from ..config import APP_VERSION
from ..daily_wallpaper import normalize_custom_api_url
from ..i18n import (
    LANGUAGE_LABELS, LANG_AUTO, LANG_ZH_CN, LANG_ZH_TW,
    LANG_EN, LANG_JA, LANG_KO, tr,
)

# GPU 厂商信息
GPU_VENDORS = {
    "none":   {"label": "不使用 GPU",         "color": "#94a3b8"},
    "nvidia": {"label": "NVIDIA  (NVENC)",    "color": "#76b900"},
    "amd":    {"label": "AMD  (AMF)",         "color": "#ed1c24"},
    "intel":  {"label": "Intel  (Quick Sync)","color": "#0071c5"},
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

PROJECT_URL = "https://github.com/xiaofa520/Formix"
PROJECT_LINK_SVG = """<svg t="1778631030424" class="icon" viewBox="0 0 1024 1024" version="1.1" xmlns="http://www.w3.org/2000/svg" p-id="2541" width="200" height="200"><path d="M950.930286 512q0 143.433143-83.748571 257.974857t-216.283429 158.573714q-15.433143 2.852571-22.601143-4.022857t-7.168-17.115429l0-120.539429q0-55.442286-29.696-81.115429 32.548571-3.437714 58.587429-10.313143t53.686857-22.308571 46.299429-38.034286 30.281143-59.977143 11.702857-86.016q0-69.12-45.129143-117.686857 21.138286-52.004571-4.534857-116.589714-16.018286-5.12-46.299429 6.290286t-52.589714 25.161143l-21.723429 13.677714q-53.174857-14.848-109.714286-14.848t-109.714286 14.848q-9.142857-6.290286-24.283429-15.433143t-47.689143-22.016-49.152-7.68q-25.161143 64.585143-4.022857 116.589714-45.129143 48.566857-45.129143 117.686857 0 48.566857 11.702857 85.723429t29.988571 59.977143 46.006857 38.253714 53.686857 22.308571 58.587429 10.313143q-22.820571 20.553143-28.013714 58.88-11.995429 5.705143-25.746286 8.557714t-32.548571 2.852571-37.449143-12.288-31.744-35.693714q-10.825143-18.285714-27.721143-29.696t-28.306286-13.677714l-11.410286-1.682286q-11.995429 0-16.603429 2.56t-2.852571 6.582857 5.12 7.972571 7.460571 6.875429l4.022857 2.852571q12.580571 5.705143 24.868571 21.723429t17.993143 29.110857l5.705143 13.165714q7.460571 21.723429 25.161143 35.108571t38.253714 17.115429 39.716571 4.022857 31.744-1.974857l13.165714-2.267429q0 21.723429 0.292571 50.834286t0.292571 30.866286q0 10.313143-7.460571 17.115429t-22.820571 4.022857q-132.534857-44.032-216.283429-158.573714t-83.748571-257.974857q0-119.442286 58.88-220.306286t159.744-159.744 220.306286-58.88 220.306286 58.88 159.744 159.744 58.88 220.306286z" fill="#444444" p-id="2542"></path></svg>"""


class SettingsPage(QWidget):
    # ── 所有信号必须在类体顶层 ───────────────────────────────────────
    theme_changed        = pyqtSignal(str)
    blur_changed         = pyqtSignal(int)
    mask_opacity_changed = pyqtSignal(int)
    bg_fill_mode_changed = pyqtSignal(str)
    bg_image_changed     = pyqtSignal(str)
    bg_clear_requested   = pyqtSignal()     # 用户点击 ✕ 清除背景（含关闭每日壁纸）
    command_line_toggled = pyqtSignal(bool)
    language_changed     = pyqtSignal(str)
    gpu_vendor_changed   = pyqtSignal(str)
    daily_wallpaper_toggled = pyqtSignal(bool)
    daily_wallpaper_refresh = pyqtSignal()
    daily_wallpaper_api_changed = pyqtSignal(str)
    daily_wallpaper_refresh_days_changed = pyqtSignal(object)
    check_update_requested  = pyqtSignal()
    download_ffmpeg_requested = pyqtSignal()

    def __init__(self, current_theme="light", current_blur=0,
                 current_bg="", gpu_vendor="none",
                 current_bg_fill_mode="cover",
                 command_line_enabled=False,
                 daily_enabled=False, mask_opacity=20,
                 current_language=LANG_AUTO,
                 daily_api_url="",
                 daily_refresh_days=1,
                 parent=None):
        super().__init__(parent)
        self._theme        = current_theme
        self._blur         = current_blur          # 0-20
        self._mask_opacity = mask_opacity          # 背景图片透明度
        self._bg_path      = current_bg
        self._bg_fill_mode = current_bg_fill_mode
        self._command_line_enabled = command_line_enabled
        self._vendor       = gpu_vendor
        self._is_dark      = (current_theme == "dark")
        self._daily_enabled = daily_enabled
        self._daily_api_url = str(daily_api_url or "").strip()
        self._daily_refresh_days = daily_refresh_days if daily_refresh_days in {1, 2, 3, 4, 5, 6, 7, "manual"} else 1
        self._ffmpeg_action = "下载"
        self._language     = current_language or LANG_AUTO
        self._update_status_overridden = False
        self._ffmpeg_status_overridden = False
        self._init_ui()
        self._refresh_daily_ui()
        self._refresh_daily_controls_visibility()
        self.set_language(self._language)

    # ── Public ───────────────────────────────────────────────────────
    def set_theme(self, mode: str, bg_colors: dict = None, resolved_mode: str = None):
        self._theme = mode
        actual_mode = resolved_mode or ("dark" if mode == "dark" else "light")
        self._is_dark = (actual_mode == "dark")
        self._refresh_theme_buttons()
        self._refresh_command_toggle()

    def set_language(self, language: str):
        self._language = language or LANG_AUTO
        if hasattr(self, "language_combo"):
            idx = self.language_combo.findData(self._language)
            if idx >= 0 and idx != self.language_combo.currentIndex():
                self.language_combo.blockSignals(True)
                self.language_combo.setCurrentIndex(idx)
                self.language_combo.blockSignals(False)
        self._retranslate_ui()

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

        # ── 第一行：外观  +  GPU/FFmpeg（左右并排）
        row1 = QHBoxLayout(); row1.setSpacing(10)
        row1.addWidget(self._build_appearance_card(), 5)
        gpu_stack = QVBoxLayout()
        gpu_stack.setContentsMargins(0, 0, 0, 0)
        gpu_stack.setSpacing(10)
        gpu_stack.addWidget(self._build_gpu_card(), 0)
        gpu_stack.addWidget(self._build_ffmpeg_card(), 0)
        row1.addLayout(gpu_stack, 5)
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

        self._appearance_section = SectionLabel("外观")
        lay.addWidget(self._appearance_section)

        # 主题切换
        self._theme_row_lbl = self._row_label("颜色模式")
        lay.addWidget(self._theme_row_lbl)
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

        self.auto_btn = QPushButton("自动")
        self.auto_btn.setObjectName("toggle_auto")
        self.auto_btn.setFixedHeight(_BTN_H)
        self.auto_btn.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.auto_btn.clicked.connect(lambda: self._set_theme("auto"))

        t_row.addWidget(self.light_btn, 1)
        t_row.addWidget(self.dark_btn,  1)
        t_row.addWidget(self.auto_btn,  1)
        lay.addLayout(t_row)
        self._refresh_theme_buttons()

        lay.addWidget(self._div())

        # 语言切换
        self._language_row_lbl = self._row_label("语言")
        lay.addWidget(self._language_row_lbl)
        lang_row = QHBoxLayout(); lang_row.setSpacing(8); lang_row.setContentsMargins(0,0,0,0)
        self.language_combo = NoWheelComboBox()
        self.language_combo.addItem(LANGUAGE_LABELS[LANG_AUTO], LANG_AUTO)
        self.language_combo.addItem(LANGUAGE_LABELS[LANG_ZH_CN], LANG_ZH_CN)
        self.language_combo.addItem(LANGUAGE_LABELS[LANG_ZH_TW], LANG_ZH_TW)
        self.language_combo.addItem(LANGUAGE_LABELS[LANG_EN], LANG_EN)
        self.language_combo.addItem(LANGUAGE_LABELS[LANG_JA], LANG_JA)
        self.language_combo.addItem(LANGUAGE_LABELS[LANG_KO], LANG_KO)
        self.language_combo.currentIndexChanged.connect(self._on_language_changed)
        lang_row.addWidget(self.language_combo, 1)
        lay.addLayout(lang_row)

        lay.addWidget(self._div())

        # 命令行页面开关
        self._command_section_lbl = self._row_label("命令行页面")
        lay.addWidget(self._command_section_lbl)
        cmd_row = QHBoxLayout(); cmd_row.setSpacing(8); cmd_row.setContentsMargins(0,0,0,0)
        self.command_line_chk = QCheckBox("已禁用")
        self.command_line_chk.setObjectName("command_line_switch")
        self.command_line_chk.setChecked(self._command_line_enabled)
        self.command_line_chk.toggled.connect(self._on_command_line_toggled)
        cmd_row.addWidget(self.command_line_chk)
        cmd_row.addStretch()
        lay.addLayout(cmd_row)

        lay.addWidget(self._div())

        # 毛玻璃模糊强度（滑块 0-20）
        self._blur_row_lbl = self._row_label("毛玻璃模糊")
        lay.addWidget(self._blur_row_lbl)
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
        self.blur_hint = QLabel("需先设置背景图")
        self.blur_hint.setObjectName("section_title")
        blur_row.addWidget(self.blur_slider, 1)
        blur_row.addWidget(self.blur_val_lbl)
        blur_row.addWidget(self.blur_hint)
        self.blur_slider.valueChanged.connect(self._on_blur)
        lay.addLayout(blur_row)

        lay.addWidget(self._div())

        # 背景图片透明度（可调）
        self._mask_row_lbl = self._row_label("背景图片透明度")
        lay.addWidget(self._mask_row_lbl)
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
        self.mask_hint = QLabel("0=不显示  100=完全显示")
        self.mask_hint.setObjectName("section_title")
        mask_row.addWidget(self.mask_slider, 1)
        mask_row.addWidget(self.mask_val_lbl)
        mask_row.addWidget(self.mask_hint)
        self.mask_slider.valueChanged.connect(self._on_mask_opacity)
        lay.addLayout(mask_row)

        lay.addWidget(self._div())

        # 背景图片
        self._bg_section = SectionLabel("背景图片")
        lay.addWidget(self._bg_section)
        bg_row = QHBoxLayout(); bg_row.setSpacing(6); bg_row.setContentsMargins(0,0,0,0)

        self.bg_lbl = QLabel("未设置")
        self.bg_lbl.setObjectName("section_title")
        self.bg_lbl.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self.bg_lbl.setMaximumWidth(180)

        self.choose_btn = QPushButton("选择图片")
        self.choose_btn.setFixedHeight(_BTN_H)
        self.choose_btn.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self.choose_btn.clicked.connect(self._choose_bg)

        self.clear_btn = QPushButton("清空")
        self.clear_btn.setObjectName("danger")
        self.clear_btn.setFixedSize(72, _BTN_H)
        self.clear_btn.setToolTip("清空背景图片")
        self.clear_btn.clicked.connect(self._clear_bg)

        bg_row.addWidget(self.bg_lbl, 1)
        bg_row.addWidget(self.choose_btn)
        bg_row.addWidget(self.clear_btn)
        lay.addLayout(bg_row)

        mode_row = QHBoxLayout(); mode_row.setSpacing(8); mode_row.setContentsMargins(0,0,0,0)
        self.mode_lbl = QLabel("背景填充模式")
        self.mode_lbl.setObjectName("section_title")
        self.bg_fill_mode_combo = NoWheelComboBox()
        self.bg_fill_mode_combo.addItem("无拉伸", "none")
        self.bg_fill_mode_combo.addItem("拉伸填充", "stretch")
        self.bg_fill_mode_combo.addItem("等比适应", "fit")
        self.bg_fill_mode_combo.addItem("等比填充(裁剪)", "cover")
        idx = self.bg_fill_mode_combo.findData(self._bg_fill_mode)
        self.bg_fill_mode_combo.setCurrentIndex(idx if idx >= 0 else 3)
        self.bg_fill_mode_combo.currentIndexChanged.connect(self._on_bg_fill_mode_changed)
        mode_row.addWidget(self.mode_lbl)
        mode_row.addWidget(self.bg_fill_mode_combo, 1)
        lay.addLayout(mode_row)

        lay.addWidget(self._div())

        # ── 每日壁纸 ──────────────────────────────────────────────
        self._daily_section = SectionLabel("每日壁纸")
        lay.addWidget(self._daily_section)

        self.daily_info = QLabel("自动每天零点从 API 获取一张壁纸作为背景图")
        self.daily_info.setObjectName("section_title")
        self.daily_info.setWordWrap(True)
        lay.addWidget(self.daily_info)

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

        self._daily_api_row_lbl = self._row_label("壁纸 API")
        lay.addWidget(self._daily_api_row_lbl)
        self.daily_api_edit = QLineEdit()
        self.daily_api_edit.setMinimumHeight(_CTRL_H)
        self.daily_api_edit.setPlaceholderText("https://example.com/wallpaper-api")
        self.daily_api_edit.setText(self._daily_api_url)
        self.daily_api_edit.editingFinished.connect(self._on_daily_api_changed)
        lay.addWidget(self.daily_api_edit)

        self._daily_refresh_days_wrap = QWidget()
        refresh_row = QHBoxLayout(self._daily_refresh_days_wrap); refresh_row.setSpacing(8); refresh_row.setContentsMargins(0,0,0,0)
        self._daily_refresh_days_lbl = QLabel("刷新天数")
        self._daily_refresh_days_lbl.setObjectName("section_title")
        self.daily_refresh_days_combo = NoWheelComboBox()
        self.daily_refresh_days_combo.addItem("1 天", 1)
        self.daily_refresh_days_combo.addItem("2 天", 2)
        self.daily_refresh_days_combo.addItem("3 天", 3)
        self.daily_refresh_days_combo.addItem("4 天", 4)
        self.daily_refresh_days_combo.addItem("5 天", 5)
        self.daily_refresh_days_combo.addItem("6 天", 6)
        self.daily_refresh_days_combo.addItem("7 天", 7)
        self.daily_refresh_days_combo.addItem("永久", "manual")
        idx = self.daily_refresh_days_combo.findData(self._daily_refresh_days)
        self.daily_refresh_days_combo.setCurrentIndex(idx if idx >= 0 else 0)
        self.daily_refresh_days_combo.currentIndexChanged.connect(self._on_daily_refresh_days_changed)
        refresh_row.addWidget(self._daily_refresh_days_lbl)
        refresh_row.addWidget(self.daily_refresh_days_combo, 1)
        lay.addWidget(self._daily_refresh_days_wrap)

        self.daily_status_lbl = QLabel("未启用")
        self.daily_status_lbl.setObjectName("section_title")
        self.daily_status_lbl.setWordWrap(True)
        lay.addWidget(self.daily_status_lbl)
        lay.addStretch()

        if self._bg_path and os.path.isfile(self._bg_path):
            self.bg_lbl.setText(os.path.basename(self._bg_path))

        return card

    # ── GPU 设置卡片 ─────────────────────────────────────────────────
    def _build_gpu_card(self) -> CardWidget:
        card = CardWidget()
        lay  = card.layout()
        lay.setSpacing(12)

        self._gpu_section = SectionLabel("GPU 硬件加速")
        lay.addWidget(self._gpu_section)

        # 说明文字
        self._gpu_info_lbl = QLabel(
            "选择显卡厂商后，视频转换将自动使用 GPU 编码器，\n"
            "速度提升 3–10×。需要 FFmpeg 编译了对应编码器。"
        )
        self._gpu_info_lbl.setObjectName("section_title")
        self._gpu_info_lbl.setWordWrap(True)
        lay.addWidget(self._gpu_info_lbl)

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

        # 当前状态标签
        self._gpu_status_lbl = QLabel()
        self._gpu_status_lbl.setWordWrap(True)
        self._gpu_status_lbl.setObjectName("section_title")
        lay.addWidget(self._gpu_status_lbl)
        lay.addWidget(self._div())

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
        lay.addWidget(self._div())

        self._project_link_card = QFrame()
        self._project_link_card.setObjectName("gpu_link_card")
        project_row = QHBoxLayout(self._project_link_card)
        project_row.setContentsMargins(10, 8, 10, 8)
        project_row.setSpacing(8)
        self._project_link_hint = QLabel("项目地址")
        self._project_link_hint.setObjectName("section_title")
        self._project_link_btn = QPushButton()
        self._project_link_btn.setObjectName("icon_link_button")
        self._project_link_btn.setToolTip(PROJECT_URL)
        self._project_link_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._project_link_btn.setFixedSize(32, 32)
        self._project_link_btn.setIcon(self._make_project_link_icon())
        self._project_link_btn.setIconSize(QSize(18, 18))
        self._project_link_btn.clicked.connect(lambda: webbrowser.open(PROJECT_URL))
        project_row.addWidget(self._project_link_hint)
        project_row.addStretch()
        project_row.addWidget(self._project_link_btn)
        lay.addWidget(self._project_link_card)

        lay.addStretch()

        # 初始刷新
        self._refresh_vendor_buttons()
        self._refresh_encoder_labels()
        return card

    def _make_vendor_btn(self, vendor: str) -> QPushButton:
        info = GPU_VENDORS[vendor]
        label = tr(self._language, "gpu_none_label") if vendor == "none" else info["label"]
        btn  = QPushButton(label)
        btn.setFixedHeight(38)
        btn.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        btn.setObjectName(f"vendor_btn_{vendor}")
        btn.clicked.connect(lambda _=False, v=vendor: self._set_vendor(v))
        return btn

    @staticmethod
    def _make_project_link_icon() -> QIcon:
        if QSvgRenderer is not None:
            renderer = QSvgRenderer(bytearray(PROJECT_LINK_SVG, "utf-8"))
            if renderer.isValid():
                pixmap = QPixmap(64, 64)
                pixmap.fill(Qt.GlobalColor.transparent)
                painter = QPainter(pixmap)
                renderer.render(painter)
                painter.end()
                return QIcon(pixmap)
        icon_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "assets",
            "logo.ico",
        )
        if os.path.isfile(icon_path):
            return QIcon(icon_path)
        return QIcon()

    # ── 关于卡片 ─────────────────────────────────────────────────────
    def _build_about_card(self) -> CardWidget:
        card = CardWidget()
        lay  = card.layout()
        lay.setSpacing(10)

        self._about_section = SectionLabel("关于")
        lay.addWidget(self._about_section)

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

        self._update_section = SectionLabel("软件更新")
        lay.addWidget(self._update_section)

        # 按钮行
        update_row = QHBoxLayout()
        update_row.setSpacing(6)
        update_row.setContentsMargins(0, 0, 0, 0)

        self._check_update_btn = QPushButton("检查更新")
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
        self._update_notes_title = self._row_label("更新公告")
        lay.addWidget(self._update_notes_title)
        self._update_notes_lbl = QTextBrowser()
        self._update_notes_lbl.setObjectName("update_notes_browser")
        self._update_notes_lbl.setOpenExternalLinks(True)
        self._update_notes_lbl.setReadOnly(True)
        self._update_notes_lbl.setFrameShape(QFrame.Shape.NoFrame)
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

    def _build_ffmpeg_card(self) -> CardWidget:
        card = CardWidget()
        lay = card.layout()
        lay.setSpacing(10)

        self._ffmpeg_section = SectionLabel("FFmpeg")
        lay.addWidget(self._ffmpeg_section)

        self._ffmpeg_status_lbl = QLabel("正在检查 FFmpeg 状态…")
        self._ffmpeg_status_lbl.setObjectName("section_title")
        self._ffmpeg_status_lbl.setWordWrap(True)
        lay.addWidget(self._ffmpeg_status_lbl)

        ff_row = QHBoxLayout()
        ff_row.setSpacing(6)
        ff_row.setContentsMargins(0, 0, 0, 0)

        self._download_ffmpeg_btn = QPushButton("下载 FFmpeg")
        self._download_ffmpeg_btn.setFixedHeight(_BTN_H)
        self._download_ffmpeg_btn.setSizePolicy(
            QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self._download_ffmpeg_btn.clicked.connect(self._on_download_ffmpeg)

        self._ffmpeg_hint_lbl = QLabel("下载到缓存目录后自动解压到 format_factory/FFmpeg")
        self._ffmpeg_hint_lbl.setObjectName("section_title")
        self._ffmpeg_hint_lbl.setWordWrap(True)
        self._ffmpeg_hint_lbl.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)

        ff_row.addWidget(self._download_ffmpeg_btn)
        ff_row.addWidget(self._ffmpeg_hint_lbl, 1)
        lay.addLayout(ff_row)

        return card

    # ── 状态刷新 ─────────────────────────────────────────────────────
    def _refresh_vendor_buttons(self):
        for vendor, btn in self._vendor_btns.items():
            active = (vendor == self._vendor)
            if vendor == "none":
                btn.setText(tr(self._language, "gpu_none_label"))
            name   = f"vendor_btn_{vendor}_active" if active else f"vendor_btn_{vendor}"
            btn.setObjectName(name)
            btn.style().unpolish(btn)
            btn.style().polish(btn)

    def _refresh_encoder_labels(self):
        enc = GPU_ENCODERS.get(self._vendor, {})
        info = GPU_VENDORS[self._vendor]
        if self._vendor == "none":
            self._gpu_status_lbl.setText(tr(self._language, "gpu_cpu_status"))
            self._enc_h264_lbl.setText("— (libx264)")
            self._enc_hevc_lbl.setText("— (libx265)")
        else:
            self._gpu_status_lbl.setText(
                tr(self._language, "gpu_selected_status", label=info["label"]))
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
        self._refresh_theme_buttons()
        self.theme_changed.emit(mode)

    def _refresh_theme_buttons(self):
        if not all(hasattr(self, name) for name in ("light_btn", "dark_btn", "auto_btn")):
            return
        mapping = {
            "light_btn": ("toggle_light", "toggle_light_active", self._theme == "light"),
            "dark_btn": ("toggle_dark", "toggle_dark_active", self._theme == "dark"),
            "auto_btn": ("toggle_auto", "toggle_auto_active", self._theme == "auto"),
        }
        for attr, (idle_name, active_name, selected) in mapping.items():
            btn = getattr(self, attr)
            want = active_name if selected else idle_name
            if btn.objectName() != want:
                btn.setObjectName(want)
                btn.style().unpolish(btn)
                btn.style().polish(btn)
                btn.update()

    def _choose_bg(self):
        p, _ = QFileDialog.getOpenFileName(
            self, "选择背景图片", "",
            "图片文件 (*.jpg *.jpeg *.png *.bmp *.webp);;所有文件 (*.*)")
        if p:
            self._bg_path = p
            self.bg_lbl.setText(os.path.basename(p))
            self.bg_image_changed.emit(p)

    def _clear_bg(self):
        self._bg_path = ""
        self.bg_lbl.setText("未设置")
        self.bg_image_changed.emit("")
        self.bg_clear_requested.emit()   # 通知 MainWindow 同时关闭每日壁纸

    def _on_blur(self, val: int):
        self._blur = val
        self.blur_val_lbl.setText(f"{val}")
        self.blur_changed.emit(val)

    def _on_mask_opacity(self, val: int):
        self._mask_opacity = val
        self.mask_val_lbl.setText(f"{val}%")
        self.mask_opacity_changed.emit(val)

    def _on_bg_fill_mode_changed(self, idx: int):
        mode = self.bg_fill_mode_combo.itemData(idx)
        if not mode:
            mode = "cover"
        self._bg_fill_mode = mode
        self.bg_fill_mode_changed.emit(mode)

    def _on_language_changed(self, idx: int):
        if not hasattr(self, "language_combo"):
            return
        lang = self.language_combo.itemData(idx) or LANG_AUTO
        self._language = lang
        self.language_changed.emit(lang)

    def _on_daily_toggle(self):
        self._daily_enabled = not self._daily_enabled
        self._refresh_daily_ui()
        self._refresh_daily_controls_visibility()
        self.daily_wallpaper_toggled.emit(self._daily_enabled)

    def _on_daily_refresh(self):
        self._apply_daily_api_value()
        self.daily_wallpaper_refresh.emit()

    def _on_daily_api_changed(self):
        self._apply_daily_api_value()

    def _apply_daily_api_value(self) -> str:
        if not hasattr(self, "daily_api_edit"):
            return ""
        value = self.daily_api_edit.text().strip()

        normalized, err = normalize_custom_api_url(value)
        if value and err:
            if err == "multiple_links":
                self.set_daily_status("❌ 壁纸 API 只能填写一个链接，不能包含空格或多个地址。")
            else:
                self.set_daily_status("❌ 壁纸 API 格式无效，请输入单个 http/https 链接。")
            self.daily_api_edit.blockSignals(True)
            self.daily_api_edit.setText(self._daily_api_url)
            self.daily_api_edit.blockSignals(False)
            return self._daily_api_url

        if normalized == self._daily_api_url:
            return normalized

        self._daily_api_url = normalized
        self.daily_api_edit.blockSignals(True)
        self.daily_api_edit.setText(normalized)
        self.daily_api_edit.blockSignals(False)
        self._refresh_daily_controls_visibility()
        self.daily_wallpaper_api_changed.emit(normalized)
        return normalized

    def _on_daily_refresh_days_changed(self, idx: int):
        if not hasattr(self, "daily_refresh_days_combo"):
            return
        value = self.daily_refresh_days_combo.itemData(idx)
        self._daily_refresh_days = value if value in {1, 2, 3, 4, 5, 6, 7, "manual"} else 1
        self.daily_wallpaper_refresh_days_changed.emit(self._daily_refresh_days)

    def _refresh_daily_ui(self):
        if self._daily_enabled:
            self.daily_toggle_btn.setText(tr(self._language, "daily_disable"))
            self.daily_refresh_btn.setEnabled(True)
            self.daily_status_lbl.setText(tr(self._language, "daily_status_on"))
        else:
            self.daily_toggle_btn.setText(tr(self._language, "daily_enable"))
            self.daily_refresh_btn.setEnabled(False)
            self.daily_status_lbl.setText(tr(self._language, "daily_status_off"))
        if hasattr(self, "daily_refresh_btn"):
            self.daily_refresh_btn.setText(tr(self._language, "daily_refresh"))

    def _refresh_daily_controls_visibility(self):
        has_api = bool(self._daily_api_url.strip())
        visible = bool(self._daily_enabled and has_api)
        if hasattr(self, "_daily_refresh_days_wrap"):
            self._daily_refresh_days_wrap.setVisible(visible)

    def set_daily_status(self, msg: str):
        """由 MainWindow 调用，更新状态文字。"""
        if hasattr(self, "daily_status_lbl"):
            self.daily_status_lbl.setText(msg)

    def set_daily_api_url(self, api_url: str):
        self._daily_api_url = str(api_url or "").strip()
        if hasattr(self, "daily_api_edit"):
            self.daily_api_edit.blockSignals(True)
            self.daily_api_edit.setText(self._daily_api_url)
            self.daily_api_edit.blockSignals(False)
        self._refresh_daily_controls_visibility()

    def set_daily_refresh_days(self, refresh_days):
        self._daily_refresh_days = refresh_days if refresh_days in {1, 2, 3, 4, 5, 6, 7, "manual"} else 1
        if hasattr(self, "daily_refresh_days_combo"):
            idx = self.daily_refresh_days_combo.findData(self._daily_refresh_days)
            self.daily_refresh_days_combo.blockSignals(True)
            self.daily_refresh_days_combo.setCurrentIndex(idx if idx >= 0 else 0)
            self.daily_refresh_days_combo.blockSignals(False)

    def set_daily_bg_preview(self, path: str):
        """壁纸下载完成后更新背景图预览。"""
        if path and os.path.isfile(path):
            self._bg_path = path
            self.bg_lbl.setText(os.path.basename(path))

    def set_bg_fill_mode(self, mode: str):
        if not hasattr(self, "bg_fill_mode_combo"):
            return
        mode = mode if mode in {"stretch", "none", "fit", "cover"} else "cover"
        self._bg_fill_mode = mode
        idx = self.bg_fill_mode_combo.findData(mode)
        if idx >= 0 and idx != self.bg_fill_mode_combo.currentIndex():
            self.bg_fill_mode_combo.blockSignals(True)
            self.bg_fill_mode_combo.setCurrentIndex(idx)
            self.bg_fill_mode_combo.blockSignals(False)

    def set_command_line_enabled(self, enabled: bool):
        self._command_line_enabled = bool(enabled)
        self._refresh_command_toggle()

    def _on_command_line_toggled(self, enabled: bool):
        self._command_line_enabled = enabled
        self.command_line_toggled.emit(enabled)

    def _refresh_command_toggle(self):
        if hasattr(self, "command_line_chk"):
            self.command_line_chk.blockSignals(True)
            self.command_line_chk.setChecked(self._command_line_enabled)
            self.command_line_chk.setText(
                tr(self._language, "command_enabled")
                if self._command_line_enabled else tr(self._language, "command_disabled")
            )
            self.command_line_chk.blockSignals(False)

    def _retranslate_ui(self):
        lang = self._language
        if hasattr(self, "_appearance_section"):
            self._appearance_section.setText(tr(lang, "settings_appearance"))
        if hasattr(self, "_theme_row_lbl"):
            self._theme_row_lbl.setText(tr(lang, "theme_label"))
        if hasattr(self, "light_btn"):
            self.light_btn.setText(tr(lang, "theme_light"))
        if hasattr(self, "dark_btn"):
            self.dark_btn.setText(tr(lang, "theme_dark"))
        if hasattr(self, "auto_btn"):
            self.auto_btn.setText(tr(lang, "theme_auto"))
        if hasattr(self, "_language_row_lbl"):
            self._language_row_lbl.setText(tr(lang, "language_label"))
        if hasattr(self, "language_combo"):
            items = [
                (LANG_AUTO, tr(lang, "language_auto")),
                (LANG_ZH_CN, LANGUAGE_LABELS[LANG_ZH_CN]),
                (LANG_ZH_TW, LANGUAGE_LABELS[LANG_ZH_TW]),
                (LANG_EN, LANGUAGE_LABELS[LANG_EN]),
                (LANG_JA, LANGUAGE_LABELS[LANG_JA]),
                (LANG_KO, LANGUAGE_LABELS[LANG_KO]),
            ]
            self.language_combo.blockSignals(True)
            self.language_combo.clear()
            for value, text in items:
                self.language_combo.addItem(text, value)
            idx = self.language_combo.findData(self._language)
            self.language_combo.setCurrentIndex(idx if idx >= 0 else 0)
            self.language_combo.blockSignals(False)
        if hasattr(self, "_command_section_lbl"):
            self._command_section_lbl.setText(tr(lang, "command_section"))
        self._refresh_command_toggle()
        if hasattr(self, "_blur_row_lbl"):
            self._blur_row_lbl.setText(tr(lang, "blur_label"))
        if hasattr(self, "blur_hint"):
            self.blur_hint.setText(tr(lang, "blur_hint"))
        if hasattr(self, "_mask_row_lbl"):
            self._mask_row_lbl.setText(tr(lang, "bg_opacity_label"))
        if hasattr(self, "mask_hint"):
            self.mask_hint.setText(tr(lang, "bg_opacity_hint"))
        if hasattr(self, "_bg_section"):
            self._bg_section.setText(tr(lang, "bg_image_label"))
        if hasattr(self, "choose_btn"):
            self.choose_btn.setText(tr(lang, "choose_image"))
        if hasattr(self, "clear_btn"):
            self.clear_btn.setText(tr(lang, "clear_image"))
            self.clear_btn.setToolTip(tr(lang, "clear_image_tip"))
        if hasattr(self, "mode_lbl"):
            self.mode_lbl.setText(tr(lang, "bg_fill_mode_label"))
        if hasattr(self, "bg_fill_mode_combo"):
            current = self._bg_fill_mode
            self.bg_fill_mode_combo.blockSignals(True)
            self.bg_fill_mode_combo.clear()
            self.bg_fill_mode_combo.addItem(tr(lang, "fill_none"), "none")
            self.bg_fill_mode_combo.addItem(tr(lang, "fill_stretch"), "stretch")
            self.bg_fill_mode_combo.addItem(tr(lang, "fill_fit"), "fit")
            self.bg_fill_mode_combo.addItem(tr(lang, "fill_cover"), "cover")
            idx = self.bg_fill_mode_combo.findData(current)
            self.bg_fill_mode_combo.setCurrentIndex(idx if idx >= 0 else 3)
            self.bg_fill_mode_combo.blockSignals(False)
        if hasattr(self, "_daily_section"):
            self._daily_section.setText(tr(lang, "daily_wallpaper"))
        if hasattr(self, "daily_info"):
            self.daily_info.setText(tr(lang, "daily_wallpaper_info"))
        if hasattr(self, "_daily_api_row_lbl"):
            self._daily_api_row_lbl.setText("壁纸 API" if lang != LANG_EN else "Wallpaper API")
        if hasattr(self, "daily_api_edit"):
            self.daily_api_edit.setPlaceholderText(
                "https://example.com/wallpaper-api"
                if lang == LANG_EN else "https://example.com/wallpaper-api"
            )
        if hasattr(self, "_daily_refresh_days_lbl"):
            self._daily_refresh_days_lbl.setText("刷新天数" if lang != LANG_EN else "Refresh days")
        if hasattr(self, "daily_refresh_days_combo"):
            current = self._daily_refresh_days
            items = [
                ("1 天" if lang != LANG_EN else "1 day", 1),
                ("2 天" if lang != LANG_EN else "2 days", 2),
                ("3 天" if lang != LANG_EN else "3 days", 3),
                ("4 天" if lang != LANG_EN else "4 days", 4),
                ("5 天" if lang != LANG_EN else "5 days", 5),
                ("6 天" if lang != LANG_EN else "6 days", 6),
                ("7 天" if lang != LANG_EN else "7 days", 7),
                ("永久" if lang != LANG_EN else "Permanent", "manual"),
            ]
            self.daily_refresh_days_combo.blockSignals(True)
            self.daily_refresh_days_combo.clear()
            for text, value in items:
                self.daily_refresh_days_combo.addItem(text, value)
            idx = self.daily_refresh_days_combo.findData(current)
            self.daily_refresh_days_combo.setCurrentIndex(idx if idx >= 0 else 0)
            self.daily_refresh_days_combo.blockSignals(False)
        if hasattr(self, "_project_link_hint"):
            self._project_link_hint.setText("项目地址" if lang != LANG_EN else "Project")
        if hasattr(self, "_project_link_btn"):
            self._project_link_btn.setToolTip(PROJECT_URL)
        self._refresh_daily_ui()
        self._refresh_daily_controls_visibility()
        if hasattr(self, "_gpu_section"):
            self._gpu_section.setText(tr(lang, "settings_gpu"))
        if hasattr(self, "_gpu_info_lbl"):
            self._gpu_info_lbl.setText(tr(lang, "gpu_info"))
        self._refresh_encoder_labels()
        if hasattr(self, "_about_section"):
            self._about_section.setText(tr(lang, "settings_about"))
        self._refresh_about_txt()
        if hasattr(self, "_update_section"):
            self._update_section.setText(tr(lang, "settings_update"))
        if hasattr(self, "_check_update_btn"):
            self._check_update_btn.setText(tr(lang, "check_update"))
        if hasattr(self, "_update_status_lbl") and not self._update_status_overridden:
            self._update_status_lbl.setText(tr(lang, "check_update_prompt"))
        if hasattr(self, "_update_notes_title"):
            self._update_notes_title.setText(tr(lang, "update_notes"))
        if hasattr(self, "_ffmpeg_section"):
            self._ffmpeg_section.setText(tr(lang, "settings_ffmpeg"))
        if hasattr(self, "_ffmpeg_status_lbl") and not self._ffmpeg_status_overridden:
            self._ffmpeg_status_lbl.setText(tr(lang, "ffmpeg_status_checking"))
        if hasattr(self, "_download_ffmpeg_btn"):
            self._download_ffmpeg_btn.setText(
                tr(lang, "ffmpeg_update") if self._ffmpeg_action == "更新"
                else tr(lang, "ffmpeg_download"))
        if hasattr(self, "_ffmpeg_hint_lbl"):
            self._ffmpeg_hint_lbl.setText(
                tr(lang, "ffmpeg_hint_update") if self._ffmpeg_action == "更新"
                else tr(lang, "ffmpeg_hint_download"))

    # ── 更新事件 ─────────────────────────────────────────────────────
    def _refresh_about_txt(self):
        """重新渲染关于标签（版本 + 内联徽标）。"""
        if not hasattr(self, "_about_txt_lbl"):
            return
        badge = f"  {self._about_badge}" if self._about_badge else ""
        desc = tr(self._language, "about_desc").replace("\n", "<br>")
        caps = tr(self._language, "about_caps").replace("\n", "<br>")
        self._about_txt_lbl.setText(
            f"<b>{tr(self._language, 'app_title')}</b>  v{APP_VERSION}{badge} 　·　 {desc}<br>"
            "<span style='opacity:0.55'>"
            f"{caps}"
            "</span>"
        )

    def set_ffmpeg_action(self, action: str):
        self._ffmpeg_action = action if action in {"下载", "更新"} else "下载"
        if hasattr(self, "_download_ffmpeg_btn"):
            self._download_ffmpeg_btn.setText(
                tr(self._language, "ffmpeg_update")
                if self._ffmpeg_action == "更新" else tr(self._language, "ffmpeg_download"))
        if hasattr(self, "_ffmpeg_hint_lbl"):
            if self._ffmpeg_action == "更新":
                self._ffmpeg_hint_lbl.setText(tr(self._language, "ffmpeg_hint_update"))
            else:
                self._ffmpeg_hint_lbl.setText(tr(self._language, "ffmpeg_hint_download"))

    def _on_check_update(self):
        self._check_update_btn.setEnabled(False)
        self._update_status_lbl.setText("正在检查更新…")
        self.check_update_requested.emit()

    def _on_download_ffmpeg(self):
        self._download_ffmpeg_btn.setEnabled(False)
        self._ffmpeg_status_lbl.setText(f"正在准备{self._ffmpeg_action} FFmpeg…")
        self.download_ffmpeg_requested.emit()

    def set_update_status(self, msg: str):
        """由 MainWindow 调用，更新检查结果文字，并重新启用按钮。"""
        self._update_status_overridden = True
        if hasattr(self, "_update_status_lbl"):
            self._update_status_lbl.setText(msg)
        if hasattr(self, "_check_update_btn"):
            self._check_update_btn.setEnabled(True)

    def set_update_notes(self, notes: str):
        """由 MainWindow 调用，在更新公告区显示版本说明。"""
        if hasattr(self, "_update_notes_lbl"):
            self._update_notes_lbl.setMarkdown(notes or "")

    def set_ffmpeg_status(self, msg: str, downloading: bool = False):
        self._ffmpeg_status_overridden = True
        if hasattr(self, "_ffmpeg_status_lbl"):
            self._ffmpeg_status_lbl.setText(msg)
        if hasattr(self, "_download_ffmpeg_btn"):
            self._download_ffmpeg_btn.setEnabled(not downloading)

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
