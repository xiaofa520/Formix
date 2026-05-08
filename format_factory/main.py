# format_factory/main.py
import sys
import os
import colorsys
import re as _re
import platform
import subprocess
from datetime import datetime, timedelta

from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout,
    QTabWidget, QMessageBox, QLabel
)
from PyQt6.QtCore import Qt, QTimer, QSettings
from PyQt6.QtGui import QPixmap, QPainter, QColor, QImage

from format_factory.config import (
    APP_VERSION, UPDATE_CACHE_DIR, FFMPEG_CACHE_DIR, FFMPEG_DIR,
    has_ffmpeg, get_ffmpeg_download_spec,
)
from format_factory.i18n import resolve_language, tr, LANG_AUTO
from format_factory.ffmpeg_handler import FFmpegHandler
from format_factory.gui_pages.settings_page import (
    SettingsPage, GPU_ENCODERS
)
from format_factory.gui_pages.video_converter import VideoConverterPage
from format_factory.gui_pages.audio_converter import AudioConverterPage
from format_factory.gui_pages.image_converter import ImageConverterPage
from format_factory.gui_pages.m3u8_downloader import M3U8DownloaderPage
from format_factory.gui_pages.av_splitter_page import AVSplitterPage
from format_factory.gui_pages.command_converter import CommandConverterPage
from format_factory.theme import build_stylesheet, LIGHT_THEME, DARK_THEME
from format_factory.daily_wallpaper import DailyWallpaperService
from format_factory.updater import (
    UpdaterService, UpdateDownloaderThread, FFmpegDownloadThread, _parse_version,
    replace_app_with_archive,
)

# CPU codec → GPU role mapping
_CPU_TO_ROLE = {
    "libx264": "h264", "libx265": "hevc",
    "libxvid": "h264", "flv1": "h264",
}


def _as_bool(value) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    return bool(value)


def _is_update_required(info: dict) -> bool:
    if _as_bool(info.get("mandatory", False)):
        return True
    min_supported = str(info.get("min_supported_version", "")).strip()
    return bool(min_supported and _parse_version(APP_VERSION) < _parse_version(min_supported))


def _detect_system_theme() -> str:
    system = platform.system()
    try:
        if system == "Windows":
            import winreg

            for path, value_name in (
                (r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize", "AppsUseLightTheme"),
                (r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize", "SystemUsesLightTheme"),
            ):
                try:
                    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, path) as key:
                        value, _ = winreg.QueryValueEx(key, value_name)
                        return "light" if int(value) else "dark"
                except OSError:
                    pass
        elif system == "Darwin":
            proc = subprocess.run(
                ["defaults", "read", "-g", "AppleInterfaceStyle"],
                capture_output=True,
                text=True,
                check=False,
            )
            return "dark" if "Dark" in (proc.stdout or "") else "light"
        elif system == "Linux":
            proc = subprocess.run(
                ["gsettings", "get", "org.gnome.desktop.interface", "color-scheme"],
                capture_output=True,
                text=True,
                check=False,
            )
            out = (proc.stdout or "").strip().lower()
            if "dark" in out:
                return "dark"
            if "light" in out:
                return "light"
    except Exception:
        pass
    return "light"


# ══════════════════════════════════════════════════════════════════
#  Average-color analyser  (pure Qt, no PIL)
# ══════════════════════════════════════════════════════════════════
def analyze_image_colors(path: str) -> dict:
    """
    计算图片的平均颜色（取代原来的主色调计算）。
    返回平均颜色的色相、RGB，以及其互补色。
    """
    empty = {"is_dark": False, "complement_hex": "",
             "accent_hex": "", "avg_hue": -1.0,
             "avg_r": 128, "avg_g": 128, "avg_b": 128}
    if not path or not os.path.isfile(path):
        return empty

    img = QImage(path)
    if img.isNull():
        return empty

    small = img.scaled(60, 60,
                       Qt.AspectRatioMode.IgnoreAspectRatio,
                       Qt.TransformationMode.SmoothTransformation)

    rt = gt = bt = n = 0

    for y in range(small.height()):
        for x in range(small.width()):
            c = QColor(small.pixel(x, y))
            rt += c.red(); gt += c.green(); bt += c.blue()
            n += 1

    if n == 0:
        return empty

    ar, ag, ab_ = rt//n, gt//n, bt//n
    bright   = (ar*299 + ag*587 + ab_*114) / 1000
    is_dark  = bright < 128

    # 计算平均颜色的 HSV
    h, s, _ = colorsys.rgb_to_hsv(ar/255, ag/255, ab_/255)

    # 如果饱和度极低（黑白灰图片），色相无效
    avg_hue = h if s > 0.05 else -1.0

    # 计算互补色（色相相差 180 度即 0.5）
    comp_hue = (h + 0.5) % 1.0

    if is_dark:
        cc = QColor.fromHsvF(comp_hue, 0.55, 0.94)
        ac = QColor.fromHsvF((comp_hue+0.08)%1.0, 0.75, 0.98)
    else:
        cc = QColor.fromHsvF(comp_hue, 0.65, 0.38)
        ac = QColor.fromHsvF((comp_hue+0.08)%1.0, 0.80, 0.50)

    return {"is_dark": is_dark,
            "complement_hex": cc.name(),
            "accent_hex": ac.name(),
            "avg_hue": avg_hue,
            "avg_bright": bright,
            "avg_r": ar, "avg_g": ag, "avg_b": ab_}


# ══════════════════════════════════════════════════════════════════
#  Background widget
# ══════════════════════════════════════════════════════════════════
class BackgroundWidget(QWidget):
    """
    用 paintEvent 直接绘制三层，彻底解决 QLabel 叠加时 alpha 不穿透的问题：
      1. 清晰背景图
      2. 高斯模糊层（离屏渲染到 QPixmap，叠加在背景上）
      3. 纯色半透明遮罩（覆盖在图片上方）
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        self._pixmap     = None
        self._bg_cache   = None    # (w, h) → QPixmap
        self._blur_cache = None    # (w, h, r) → QPixmap
        self._fill_mode  = "cover"
        self._dark          = False
        self._blur_r        = 0
        self._bg_opacity     = 50
        self._mask_alpha     = 51
        self._avg_bright    = 128
        self._avg_r = self._avg_g = self._avg_b = 128
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.setAttribute(Qt.WidgetAttribute.WA_OpaquePaintEvent, False)

    # ── 公开接口 ──────────────────────────────────────────────────────
    def set_image(self, path: str):
        self._pixmap     = QPixmap(path) if (path and os.path.isfile(path)) else None
        self._bg_cache   = None
        self._blur_cache = None
        self.update()

    def set_fill_mode(self, mode: str):
        mode = mode if mode in {"stretch", "none", "fit", "cover"} else "cover"
        if mode != self._fill_mode:
            self._fill_mode = mode
            self._bg_cache = None
            self._blur_cache = None
        self.update()

    def set_blur(self, level: int):
        new_r = max(0, int(level))
        if new_r != self._blur_r:
            self._blur_r    = new_r
            self._blur_cache = None
        self.update()

    def set_bg_opacity(self, pct: int):
        self._bg_opacity = max(0, min(100, int(pct)))
        self.update()

    def set_dark(self, dark: bool):
        self._dark = dark
        self.update()

    def set_mask_alpha(self, alpha: int):
        self._mask_alpha = max(0, min(255, int(alpha)))
        self.update()

    def set_mask_color(self, dark: bool):
        self._dark = dark
        self.update()

    def set_bg_colors(self, colors: dict):
        self._avg_bright = colors.get("avg_bright", 128)
        self._avg_r      = colors.get("avg_r", 128)
        self._avg_g      = colors.get("avg_g", 128)
        self._avg_b      = colors.get("avg_b", 128)
        self.update()

    # ── 离屏高斯模糊 ──────────────────────────────────────────────────
    @staticmethod
    def _offscreen_blur(src: "QPixmap", sigma: float) -> "QPixmap":
        from PyQt6.QtWidgets import QGraphicsScene, QGraphicsPixmapItem, QGraphicsBlurEffect
        from PyQt6.QtCore import QRectF

        w, h   = src.width(), src.height()
        pad    = int(sigma * 3) + 2
        pw, ph = w + pad * 2, h + pad * 2

        scene = QGraphicsScene()
        scene.setSceneRect(QRectF(0, 0, pw, ph))

        item = QGraphicsPixmapItem(src)
        item.setPos(pad, pad)
        scene.addItem(item)

        fx = QGraphicsBlurEffect()
        fx.setBlurRadius(sigma)
        fx.setBlurHints(QGraphicsBlurEffect.BlurHint.QualityHint)
        item.setGraphicsEffect(fx)

        padded = QPixmap(pw, ph)
        padded.fill(Qt.GlobalColor.transparent)
        p = QPainter(padded)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        scene.render(p)
        p.end()

        return padded.copy(pad, pad, w, h)

    # ── 内部 ──────────────────────────────────────────────────────────
    def _bg_alpha(self) -> float:
        return max(0.0, min(1.0, self._bg_opacity / 100.0))

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self._bg_cache   = None
        self._blur_cache = None
        self.update()

    def _render_base_pixmap(self, w: int, h: int) -> QPixmap:
        if not self._pixmap:
            return QPixmap()

        pix = QPixmap(w, h)
        pix.fill(Qt.GlobalColor.transparent)
        p = QPainter(pix)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)

        if self._fill_mode == "stretch":
            scaled = self._pixmap.scaled(
                w, h,
                Qt.AspectRatioMode.IgnoreAspectRatio,
                Qt.TransformationMode.SmoothTransformation)
            p.drawPixmap(0, 0, scaled)
        elif self._fill_mode == "none":
            x = (w - self._pixmap.width()) // 2
            y = (h - self._pixmap.height()) // 2
            p.drawPixmap(x, y, self._pixmap)
        elif self._fill_mode == "fit":
            scaled = self._pixmap.scaled(
                w, h,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation)
            x = (w - scaled.width()) // 2
            y = (h - scaled.height()) // 2
            p.drawPixmap(x, y, scaled)
        else:
            scaled = self._pixmap.scaled(
                w, h,
                Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                Qt.TransformationMode.SmoothTransformation)
            x = (scaled.width() - w) // 2
            y = (scaled.height() - h) // 2
            p.drawPixmap(-x, -y, scaled)

        p.end()
        return pix

    def paintEvent(self, e):
        if not self._pixmap:
            return

        w, h = self.width(), self.height()
        if w <= 0 or h <= 0:
            return

        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)

        # ── 层 1：清晰背景 ────────────────────────────────────────────
        bg_key = (w, h, self._fill_mode)
        if self._bg_cache is None or self._bg_cache[0] != bg_key:
            pix = self._render_base_pixmap(w, h)
            self._bg_cache   = (bg_key, pix)
            self._blur_cache = None

        bg_alpha = self._bg_alpha()
        if bg_alpha > 0:
            painter.setOpacity(bg_alpha)
            painter.drawPixmap(0, 0, self._bg_cache[1])
            painter.setOpacity(1.0)

        # ── 层 2：高斯模糊（blur_r > 0 时才叠加） ────────────────────
        if self._blur_r > 0 and bg_alpha > 0:
            blur_key = (w, h, self._blur_r, self._fill_mode)
            if self._blur_cache is None or self._blur_cache[0] != blur_key:
                blurred = self._offscreen_blur(
                    self._bg_cache[1], sigma=float(self._blur_r))
                self._blur_cache = (blur_key, blurred)
            painter.setOpacity(bg_alpha)
            painter.drawPixmap(0, 0, self._blur_cache[1])
            painter.setOpacity(1.0)

        # ── 层 3：纯色遮罩，始终绘制在图片上方 ───────────────────────
        mask_color = QColor(0, 0, 0, self._mask_alpha) if self._dark else QColor(255, 255, 255, self._mask_alpha)
        painter.fillRect(0, 0, w, h, mask_color)

        painter.end()


# ══════════════════════════════════════════════════════════════════
#  GPU arg injection  (no detection, purely table-driven)
# ══════════════════════════════════════════════════════════════════
def apply_gpu_args(base_args: list, vendor: str, output_fmt: str) -> tuple:
    """
    Replace CPU codec args with GPU equivalents based on chosen vendor.
    Returns (final_args, fallback_reason).
    fallback_reason is "" when GPU is used, or a description when CPU fallback occurs.
    """
    if vendor == "none" or output_fmt == "gif":
        return base_args, ""

    enc = GPU_ENCODERS.get(vendor, {})
    if not enc.get("h264"):
        return base_args, ""

    supported = enc.get("supported_roles", {"h264", "hevc"})

    result   = list(base_args)
    replaced = False
    i = 0
    while i < len(result):
        if result[i] in ("-c:v", "-vcodec") and i+1 < len(result):
            role = _CPU_TO_ROLE.get(result[i+1])
            if role is None:
                # e.g. libvpx-vp9 / prores — GPU cannot encode this
                return base_args, f"编码器 {result[i+1]} 不支持 GPU 加速，已自动使用 CPU"
            if role not in supported:
                return base_args, f"当前 GPU 不支持 {role.upper()} 编码，已自动使用 CPU"
            gpu_codec = enc.get(role)
            if gpu_codec:
                result[i+1] = gpu_codec
                replaced = True
                i += 2; continue
        i += 1

    if not replaced:
        # No explicit -c:v; inject at front if there are quality flags
        if any(a in base_args for a in ("-preset", "-crf", "-q:v")):
            if "h264" in supported:
                result = ["-c:v", enc["h264"]] + result
                replaced = True

    if replaced and enc.get("extra"):
        for j, tok in enumerate(result):
            if tok in ("-c:v", "-vcodec") and j+1 < len(result):
                result = result[:j+2] + enc["extra"] + result[j+2:]
                break

    # GPU encoders (AMF/NVENC/QSV) do NOT support x264 -preset values.
    # Strip -preset <value> pairs from the result when GPU is active.
    if replaced:
        filtered = []
        k = 0
        while k < len(result):
            if result[k] == "-preset" and k + 1 < len(result):
                k += 2  # drop both "-preset" and its value
            else:
                filtered.append(result[k])
                k += 1
        result = filtered

    # GPU encoders (nvenc/amf/qsv) only accept YUV420P.
    if replaced and "-pix_fmt" not in result:
        result = result + ["-pix_fmt", "yuv420p"]

    return result, ""


# ══════════════════════════════════════════════════════════════════
#  Main Window
# ══════════════════════════════════════════════════════════════════
class MainWindow(QMainWindow):
    _FFMPEG_UPDATE_AFTER_DAYS = 30

    def __init__(self):
        super().__init__()
        self._language_pref = "auto"
        self._language = resolve_language(self._language_pref)
        self.setWindowTitle(tr(self._language, "app_title"))
        self.setMinimumSize(860, 600)
        self.resize(1080, 720)
        self._app_start_time = datetime.now()

        _icon_path = os.path.join(
            os.path.dirname(os.path.abspath(__file__)), "assets", "logo.ico")
        if os.path.isfile(_icon_path):
            from PyQt6.QtGui import QIcon
            self.setWindowIcon(QIcon(_icon_path))

        self._s              = QSettings("Formix", "App")
        self._theme_name     = self._s.value("theme",         "light")
        self._system_theme_name = _detect_system_theme()
        self._blur_level     = int(self._s.value("blur",      0))
        self._bg_opacity     = int(self._s.value("mask_opacity", 50))
        self._bg_path        = self._s.value("bg_path",       "")
        self._user_bg_path   = self._s.value("user_bg_path",  "")  # 用户手动选择的背景
        self._bg_fill_mode   = self._s.value("bg_fill_mode",  "cover")
        self._command_line_enabled = self._s.value("command_line_enabled", False, type=bool)
        self._language_pref   = self._s.value("language", "auto")
        self._language        = resolve_language(self._language_pref)
        self._bg_colors      = {}
        self._gpu_vendor     = self._s.value("gpu_vendor",    "none")
        self._daily_enabled  = self._s.value("daily_wp",      False, type=bool)
        self._ffmpeg_ready   = False

        try:
            self.ffmpeg_handler = FFmpegHandler()
            self._ffmpeg_ready = True
        except FileNotFoundError as e:
            self.ffmpeg_handler = None
            self._ffmpeg_ready = False
            self._ffmpeg_missing_reason = str(e)

        # Batch state
        self._batch_page    = None
        self._batch_files   = []
        self._batch_fmt     = ""
        self._batch_dir     = ""
        self._batch_args    = []
        self._batch_idx     = 0
        self._batch_done    = 0
        self._batch_total   = 0
        self._batch_success = 0
        self._batch_fail    = 0
        self.current_page   = None

        self._init_ui()
        self._connect_signals()
        self._update_ffmpeg_status_ui()
        self._init_ffmpeg_action_timer()

        # 启动时把已保存的 GPU vendor 同步到各页面预设标注
        if self._gpu_vendor != "none":
            for pg in (self.video_page, self.audio_page,
                       self.image_page, self.m3u8_page):
                if hasattr(pg, "args_panel"):
                    pg.args_panel.set_gpu_vendor(self._gpu_vendor)

        if self._bg_path:
            self._bg_colors = analyze_image_colors(self._bg_path)
            self._bg.set_bg_colors(self._bg_colors)
        self._bg.set_fill_mode(self._bg_fill_mode)
        self._bg.set_mask_color(self._effective_theme_name() == "dark")
        self._bg.set_mask_alpha(51)
        self._bg.set_bg_opacity(self._bg_opacity)
        self._apply_theme()
        self._init_system_theme_timer()

        # ── 每日壁纸服务 ──────────────────────────────────────────────
        self._wallpaper_svc = DailyWallpaperService(self)
        self._wallpaper_svc.wallpaper_ready.connect(self._on_wallpaper_ready)
        self._wallpaper_svc.status_changed.connect(self._on_wallpaper_status)
        self._wallpaper_svc.error_occurred.connect(self._on_wallpaper_error)
        if self._daily_enabled:
            self._wallpaper_svc.start()

        # ── 自动更新服务 ──────────────────────────────────────────────
        self._updater_svc = UpdaterService(current_version=APP_VERSION, parent=self)
        self._updater_svc.update_available.connect(self._on_update_available)
        self._updater_svc.versions_loaded.connect(self._on_versions_loaded)
        self._updater_svc.check_failed.connect(self._on_update_check_failed)

        # 启动时清理缓存的安装包
        self._cleanup_update_cache()

        # 启动时后台静默检查
        self._updater_svc.check()

    def _init_ffmpeg_action_timer(self):
        self._ffmpeg_action_timer = QTimer(self)
        self._ffmpeg_action_timer.timeout.connect(self._refresh_ffmpeg_action_ui)
        self._ffmpeg_action_timer.start(60 * 1000)
        self._refresh_ffmpeg_action_ui()

    def _ffmpeg_should_show_update(self) -> bool:
        return datetime.now() - self._app_start_time >= timedelta(days=self._FFMPEG_UPDATE_AFTER_DAYS)

    def _ffmpeg_action_text(self) -> str:
        return "更新" if self._ffmpeg_should_show_update() else "下载"

    def _tr(self, key: str, **kwargs) -> str:
        return tr(self._language, key, **kwargs)

    def _localized_ffmpeg_action_label(self) -> str:
        return self._tr("ffmpeg_update") if self._ffmpeg_action_text() == "更新" else self._tr("ffmpeg_download")

    def _apply_language(self):
        self._language = resolve_language(self._language_pref or LANG_AUTO)
        self.setWindowTitle(self._tr("app_title"))
        if hasattr(self, "tab_widget"):
            self.tab_widget.setTabText(self.tab_widget.indexOf(self.video_page), self._tr("tab_video"))
            self.tab_widget.setTabText(self.tab_widget.indexOf(self.audio_page), self._tr("tab_audio"))
            self.tab_widget.setTabText(self.tab_widget.indexOf(self.image_page), self._tr("tab_image"))
            self.tab_widget.setTabText(self.tab_widget.indexOf(self.m3u8_page), self._tr("tab_m3u8"))
            self.tab_widget.setTabText(self.tab_widget.indexOf(self.av_page), self._tr("tab_av"))
            self.tab_widget.setTabText(self.tab_widget.indexOf(self.command_page), self._tr("tab_command"))
            self.tab_widget.setTabText(self.tab_widget.indexOf(self.settings_page), self._tr("tab_settings"))
        for page_name in (
            "video_page",
            "audio_page",
            "image_page",
            "m3u8_page",
            "av_page",
            "command_page",
        ):
            page = getattr(self, page_name, None)
            if page is not None and hasattr(page, "set_language"):
                page.set_language(self._language_pref)
        if hasattr(self, "settings_page") and self.settings_page is not None:
            self.settings_page.set_language(self._language_pref)
            self.settings_page.set_ffmpeg_action(self._ffmpeg_action_text())
        if hasattr(self, "statusBar"):
            self._update_ffmpeg_status_ui()

    def _effective_theme_name(self) -> str:
        if self._theme_name == "auto":
            self._system_theme_name = _detect_system_theme()
            return self._system_theme_name
        return self._theme_name

    def _init_system_theme_timer(self):
        self._system_theme_timer = QTimer(self)
        self._system_theme_timer.timeout.connect(self._on_system_theme_tick)
        self._system_theme_timer.start(5000)

    def _on_system_theme_tick(self):
        if self._theme_name != "auto":
            return
        current = _detect_system_theme()
        if current != self._system_theme_name:
            self._system_theme_name = current
            self._apply_theme()

    def _refresh_ffmpeg_action_ui(self, update_status: bool = True):
        action = self._ffmpeg_action_text()
        if hasattr(self, "settings_page") and self.settings_page is not None:
            self.settings_page.set_ffmpeg_action(action)
        if update_status:
            self._update_ffmpeg_status_ui(refresh_action=False)

    def _cleanup_update_cache(self):
        import shutil
        if os.path.exists(UPDATE_CACHE_DIR):
            try:
                shutil.rmtree(UPDATE_CACHE_DIR)
            except Exception as e:
                print(f"Failed to cleanup update cache: {e}")

    # ── UI ──────────────────────────────────────────────────────────
    def _init_ui(self):
        self._central = QWidget()
        self._central.setObjectName("qt_centralwidget")
        self.setCentralWidget(self._central)

        self._bg = BackgroundWidget(self._central)
        self._bg.set_image(self._bg_path)
        self._bg.set_fill_mode(self._bg_fill_mode)
        self._bg.set_blur(self._blur_level)
        self._bg.set_dark(self._effective_theme_name() == "dark")
        self._bg.lower()

        root = QVBoxLayout(self._central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        self.tab_widget = QTabWidget()
        root.addWidget(self.tab_widget)

        self.video_page    = VideoConverterPage(ffmpeg_handler=self.ffmpeg_handler)
        self.audio_page    = AudioConverterPage(ffmpeg_handler=self.ffmpeg_handler)
        self.image_page    = ImageConverterPage(ffmpeg_handler=self.ffmpeg_handler)
        self.m3u8_page     = M3U8DownloaderPage(ffmpeg_handler=self.ffmpeg_handler)
        self.av_page       = AVSplitterPage(ffmpeg_handler=self.ffmpeg_handler)
        self.command_page  = CommandConverterPage(ffmpeg_handler=self.ffmpeg_handler)
        self.settings_page = SettingsPage(
            current_theme  = self._theme_name,
            current_blur   = self._blur_level,
            current_bg     = self._bg_path,
            gpu_vendor     = self._gpu_vendor,
            current_bg_fill_mode = self._bg_fill_mode,
            command_line_enabled = self._command_line_enabled,
            daily_enabled  = self._daily_enabled,
            mask_opacity   = self._bg_opacity,
            current_language = self._language_pref)

        self.tab_widget.addTab(self.video_page,    "")
        self.tab_widget.addTab(self.audio_page,    "")
        self.tab_widget.addTab(self.image_page,    "")
        self.tab_widget.addTab(self.m3u8_page,     "")
        self.tab_widget.addTab(self.av_page,       "")
        self.tab_widget.addTab(self.command_page,  "")
        self.tab_widget.addTab(self.settings_page, "")
        self._command_tab_index = self.tab_widget.indexOf(self.command_page)
        self._apply_command_line_enabled(self._command_line_enabled)
        self._apply_language()

        self.current_page = self.video_page
        self.tab_widget.currentChanged.connect(self._on_tab_changed)

    def resizeEvent(self, e):
        super().resizeEvent(e)
        if hasattr(self, '_bg'):
            self._bg.setGeometry(0, 0,
                                 self._central.width(),
                                 self._central.height())

    # ── Signals ─────────────────────────────────────────────────────
    def _connect_signals(self):
        for pg in (self.video_page, self.audio_page,
                   self.image_page, self.m3u8_page, self.command_page):
            pg.conversion_requested.connect(self._on_batch_start)
            pg.cancel_conversion_signal.connect(self._on_cancel)

        # av_page：分离走 conversion_requested，合成走 merge_requested
        self.av_page.conversion_requested.connect(self._on_av_split_task)
        self.av_page.merge_requested.connect(self._on_av_merge_task)
        self.av_page.cancel_conversion_signal.connect(self._on_cancel)

        self._connect_ffmpeg_handler_signals()

        self.settings_page.theme_changed.connect(self._on_theme_changed)
        self.settings_page.blur_changed.connect(self._on_blur_changed)
        self.settings_page.mask_opacity_changed.connect(self._on_mask_opacity_changed)
        self.settings_page.bg_fill_mode_changed.connect(self._on_bg_fill_mode_changed)
        self.settings_page.command_line_toggled.connect(self._on_command_line_toggled)
        self.settings_page.language_changed.connect(self._on_language_changed)
        self.settings_page.bg_image_changed.connect(self._on_bg_changed)
        self.settings_page.bg_clear_requested.connect(self._on_bg_clear_requested)
        self.settings_page.gpu_vendor_changed.connect(self._on_gpu_vendor_changed)
        self.settings_page.daily_wallpaper_toggled.connect(self._on_daily_toggled)
        self.settings_page.daily_wallpaper_refresh.connect(self._on_daily_refresh)
        self.settings_page.check_update_requested.connect(self._on_check_update_requested)
        self.settings_page.download_ffmpeg_requested.connect(self._on_download_ffmpeg_requested)

    def _on_tab_changed(self, i):
        pg = self.tab_widget.widget(i)
        if pg is not self.settings_page:
            self.current_page = pg
            if pg is self.command_page and hasattr(pg, "focus_terminal"):
                pg.focus_terminal()

    # ── Batch ────────────────────────────────────────────────────────
    def _on_batch_start(self, idx, inp, args, stem):
        pg = self.current_page
        if not pg: return
        if not self._ensure_ffmpeg_ready(pg):
            return
        if idx == 0:
            self._batch_page  = pg
            self._batch_files = list(pg.input_files)
            self._batch_fmt   = pg.output_format_combo.currentText()
            self._batch_dir   = pg.output_dir
            self._batch_args  = args
            self._batch_total   = len(self._batch_files)
            self._batch_idx     = 0
            self._batch_done    = 0
            self._batch_success = 0
            self._batch_fail    = 0
            pg.overall_progress_bar.setValue(0)
            pg.overall_progress_bar.setFormat(
                f"总进度: (0/{self._batch_total})  0%")
            self._submit_next()

    def _submit_next(self):
        pg = self._batch_page
        if not pg or self._batch_idx >= self._batch_total:
            return
        i    = self._batch_idx
        inp  = self._batch_files[i]
        stem = os.path.splitext(os.path.basename(inp))[0]
        self._batch_idx += 1

        # M3U8：m3u8 播放列表和 ts 切片统一放在 {stem}_segments 子目录
        if self._batch_fmt == "m3u8":
            seg_dir = os.path.join(self._batch_dir, stem + "_segments")
            os.makedirs(seg_dir, exist_ok=True)
            out = os.path.join(seg_dir, f"{stem}.m3u8")
            # 把参数里的 %03d.ts 替换为子目录绝对路径
            final_args = []
            for a in self._batch_args:
                if a == "%03d.ts":
                    final_args.append(os.path.join(seg_dir, "%03d.ts"))
                else:
                    final_args.append(a)
        else:
            out_name = pg.build_output_path(inp, self._batch_fmt) \
                if hasattr(pg, "build_output_path") else f"{stem}.{self._batch_fmt}"
            out = os.path.join(self._batch_dir, out_name)
            final_args = self._batch_args

        in_size = ""
        try:
            sz = os.path.getsize(inp)
            in_size = f"  ({sz/1024/1024:.1f} MB)" if sz > 1024*1024 \
                      else f"  ({sz/1024:.0f} KB)"
        except OSError:
            pass

        # GPU injection（基于当前 final_args，不覆盖 m3u8 里已处理的路径）
        if self._gpu_vendor != "none":
            new_args, fallback_reason = apply_gpu_args(
                final_args, self._gpu_vendor, self._batch_fmt)
            if fallback_reason:
                # GPU 不支持此预设，自动回退 CPU，记录提示
                pg.log_ffmpeg_line(i, "warning",
                    f"已自动切换 CPU 编码: {fallback_reason}")
            elif new_args != final_args:
                final_args = new_args
                enc = GPU_ENCODERS.get(self._gpu_vendor, {})
                pg.log_ffmpeg_line(i, "encoder",
                    f"GPU 加速: {enc.get('h264','')}  ({enc.get('label','')})")
            # fallback_reason 有值时 new_args == final_args，继续用 CPU 参数

        pg.log_message(
            f"[{i+1}/{self._batch_total}]  排队: "
            f"{os.path.basename(inp)}{in_size}  →  {os.path.basename(out)}",
            "info")
        self.ffmpeg_handler.convert_file(i, inp, out, final_args)

    def _on_cancel(self):
        if self.ffmpeg_handler:
            self.ffmpeg_handler.cancel_conversion()

    # ── AV Splitter / Merger ─────────────────────────────────────────
    def _on_av_split_task(self, idx: int, inp: str, args: list, stem: str):
        """
        分离任务：stem 由 SplitTab 构建，格式为 "{原始名}_audio" 或 "{原始名}_video"。
        扩展名从 split_tab 当前 combo 读取，拼出完整输出路径后直接送入 handler。
        """
        tab     = self.av_page.split_tab
        out_dir = tab._out_dir
        ext     = (tab._audio_fmt_combo.currentText()
                   if stem.endswith("_audio")
                   else tab._video_fmt_combo.currentText())
        out = os.path.join(out_dir, f"{stem}.{ext}")

        self._batch_page  = self.av_page
        self._batch_total = tab._total
        if self._ensure_ffmpeg_ready(self.av_page):
            self.ffmpeg_handler.convert_file(idx, inp, out, args)

    def _on_av_merge_task(self, idx: int, video: str, audio: str,
                          out: str, args: list):
        """
        合成任务：ffmpeg 需要两个 -i 输入。
        handler._run 构建的命令为：ffmpeg -y -i <inp> <args> <out>
        在 args 最前面注入 "-i audio"，命令就变为：
          ffmpeg -y -i video -i audio <merge_args> out
        """
        self._batch_page  = self.av_page
        self._batch_total = self.av_page.merge_tab._total
        full_args = ["-i", audio] + args
        if self._ensure_ffmpeg_ready(self.av_page):
            self.ffmpeg_handler.convert_file(idx, video, out, full_args)

    def _on_log_line(self, idx, kind, text):
        if self._batch_page:
            self._batch_page.log_ffmpeg_line(idx, kind, text)

    def _on_started(self, idx, path):
        pg = self._batch_page
        if pg:
            if pg is self.command_page:
                pg.log_message("[1/1]  ▶ 开始执行 FFmpeg 命令", "info")
            else:
                pg.log_message(
                    f"[{idx+1}/{self._batch_total}]  ▶ 开始转换: "
                    f"{os.path.basename(path)}", "info")

    def _on_progress(self, idx, msg, pct):
        pg = self._batch_page
        if pg:
            pg.update_overall_progress(idx, self._batch_total, pct)
            self.statusBar().showMessage(
                f"[{idx+1}/{self._batch_total}] {msg} {pct}%")

    def _on_finished(self, idx, status, msg):
        pg = self._batch_page
        if not pg: return
        kind = {"success":"success","cancelled":"warning",
                "failure":"error"}.get(status, "info")
        display_msg = msg
        if status == "success":
            self._batch_success += 1
            m = _re.search(r"'([^']+)' ✓$", msg)
            if m and self._batch_dir:
                out_path = os.path.join(self._batch_dir, m.group(1))
                try:
                    sz = os.path.getsize(out_path)
                    sz_str = f"{sz/1024/1024:.2f} MB" if sz > 1024*1024 \
                             else f"{sz/1024:.0f} KB"
                    display_msg = msg.replace(" ✓", f"  [{sz_str}] ✓")
                except OSError:
                    pass
        elif status == "failure":
            self._batch_fail += 1

        pg.log_message(f"[{idx+1}/{self._batch_total}]  {display_msg}", kind)

        if status == "success":
            pg.update_overall_progress(idx, self._batch_total, 100)

        self._batch_done += 1

        if status != "cancelled" and self._batch_idx < self._batch_total:
            # av_page 任务由各子 tab 自己管理批次，不走 _submit_next
            if pg is not self.av_page:
                self._submit_next(); return

        if self._batch_done >= self._batch_total or status == "cancelled":
            if status == "cancelled":
                pg.log_message("⏹  转换已取消", "warning")
                self.statusBar().showMessage("已取消")
            else:
                s = self._batch_success
                f = self._batch_fail
                t = self._batch_total
                if f == 0:
                    summary = f"✅  全部 {t} 个文件转换完成"
                    pg.log_message(summary, "success")
                    self.statusBar().showMessage("所有任务完成")
                elif s == 0:
                    summary = f"❌  {t} 个文件全部转换失败"
                    pg.log_message(summary, "error")
                    self.statusBar().showMessage("转换失败")
                else:
                    summary = f"⚠  完成: {s} 个成功，{f} 个失败（共 {t} 个）"
                    pg.log_message(summary, "warning")
                    self.statusBar().showMessage(f"{s} 成功 / {f} 失败")

            # av_page 用自己的 on_finished 更新按钮/进度
            if pg is self.av_page:
                pg.on_finished(idx, status, display_msg)
            else:
                pg.overall_progress_bar.setValue(100)
                pg.overall_progress_bar.setFormat("总进度: 100%")
                pg.start_conversion_button.setEnabled(True)
                pg.cancel_conversion_button.setEnabled(False)
            self._batch_page = None

    # ── GPU ─────────────────────────────────────────────────────────
    def _on_gpu_vendor_changed(self, vendor: str):
        self._gpu_vendor = vendor
        self._s.setValue("gpu_vendor", vendor)
        # 通知所有转换页面刷新预设标注
        for pg in (self.video_page, self.audio_page,
                   self.image_page, self.m3u8_page):
            if hasattr(pg, "args_panel"):
                pg.args_panel.set_gpu_vendor(vendor)
        self.statusBar().showMessage(
            f"{self._tr('gpu_setting_updated')}  ·  {self._vendor_status_text()}", 4000)

    def _vendor_status_text(self) -> str:
        from format_factory.gui_pages.settings_page import GPU_VENDORS
        info = GPU_VENDORS.get(self._gpu_vendor, GPU_VENDORS["none"])
        return self._tr("gpu_none_label") if self._gpu_vendor == "none" else info["label"]

    def _ensure_ffmpeg_ready(self, page=None) -> bool:
        if self.ffmpeg_handler is not None and self._ffmpeg_ready:
            return True
        action = self._localized_ffmpeg_action_label()
        msg = f"{self._tr('status_no_ffmpeg', action=action)}  {self._tr('ffmpeg_install_path', path='format_factory/FFmpeg/bin')}"
        self._batch_page = None
        target = page or self.current_page
        if target and hasattr(target, "log_message"):
            target.log_message(msg, "error")
        if target is self.av_page and getattr(self.av_page, "_batch_page", None):
            active = self.av_page._batch_page
            if hasattr(active, "_cancel_btn"):
                active._cancel_btn.setEnabled(False)
            if hasattr(active, "_update_state"):
                active._update_state()
        self.statusBar().showMessage(self._tr("status_no_ffmpeg", action=action), 5000)
        self._update_ffmpeg_status_ui()
        return False

    def _update_ffmpeg_status_ui(self, refresh_action: bool = True):
        self._ffmpeg_ready = has_ffmpeg()
        if refresh_action:
            self._refresh_ffmpeg_action_ui(update_status=False)
        action = self._localized_ffmpeg_action_label()
        if self._ffmpeg_ready:
            self.settings_page.set_ffmpeg_status(
                self._tr("status_ffmpeg_ready"), downloading=False)
        else:
            self.settings_page.set_ffmpeg_status(
                f"{self._tr('status_no_ffmpeg', action=action)}  {self._tr('ffmpeg_install_path', path='format_factory/FFmpeg/bin')}", downloading=False)
        vendor_lbl = self._vendor_status_text()
        ffmpeg_lbl = self._tr("status_ffmpeg_ready") if self._ffmpeg_ready else self._tr("status_no_ffmpeg", action=action)
        self.statusBar().showMessage(f"{self._tr('status_ready')}  ·  {vendor_lbl}  ·  {ffmpeg_lbl}")

    # ── Close ────────────────────────────────────────────────────────
    def closeEvent(self, event):
        """关闭窗口时，终止仍在运行的 FFmpeg / FFprobe 后退出。"""
        if self.ffmpeg_handler:
            self.ffmpeg_handler.shutdown()
        if hasattr(self, "_wallpaper_svc"):
            self._wallpaper_svc.stop()
        event.accept()

    # ── Daily Wallpaper ──────────────────────────────────────────────
    def _on_bg_clear_requested(self):
        """
        用户点击背景图片的 ✕ 按钮：
          1. 清空背景
          2. 若每日壁纸正在运行，自动关闭并同步 UI
        """
        if self._daily_enabled:
            self._daily_enabled = False
            self._s.setValue("daily_wp", False)
            self._wallpaper_svc.stop()
            self.settings_page._daily_enabled = False
            self.settings_page._refresh_daily_ui()

    def _on_daily_toggled(self, enabled: bool):
        self._daily_enabled = enabled
        self._s.setValue("daily_wp", enabled)
        if enabled:
            self._wallpaper_svc.start()
        else:
            self._wallpaper_svc.stop()
            # 恢复用户手动选择的背景（没选过则为空）
            restore = self._user_bg_path if (
                self._user_bg_path and os.path.isfile(self._user_bg_path)
            ) else ""
            self._bg_path = restore
            self._s.setValue("bg_path", restore)
            self._bg.set_image(restore)
            self._bg.set_fill_mode(self._bg_fill_mode)
            self._bg_colors = analyze_image_colors(restore) if restore else {}
            self._bg.set_bg_colors(self._bg_colors)
            self._apply_theme()
            if restore:
                self.settings_page._bg_path = restore
                self.settings_page.bg_lbl.setText(os.path.basename(restore))
            else:
                self.settings_page._bg_path = ""
                self.settings_page.bg_lbl.setText("未设置")

    def _on_daily_refresh(self):
        """手动刷新：清除缓存 + 重新获取（force_refresh 内部已包含清缓存）。"""
        self._wallpaper_svc.force_refresh()

    def _on_wallpaper_status(self, key: str):
        _MAP = {
            "cached":   "已加载今日壁纸",
            "fetching": "正在获取每日壁纸…",
            "done":     "今日壁纸已更新",
        }
        if key.startswith("fail:"):
            raw = key[5:]
            if raw.startswith("url_error:"):
                msg = f"网络错误: {raw[10:]}"
            elif raw == "no_url":
                msg = "API 返回数据中没有 url 字段"
            else:
                msg = f"请求失败: {raw}"
            self.settings_page.set_daily_status(f"❌ 获取失败: {msg}")
        else:
            self.settings_page.set_daily_status(_MAP.get(key, key))

    def _on_wallpaper_error(self, key: str):
        if key.startswith("url_error:"):
            msg = f"网络错误: {key[10:]}"
        elif key == "no_url":
            msg = "API 返回数据中没有 url 字段"
        elif key.startswith("error:"):
            msg = f"请求异常: {key[6:]}"
        else:
            msg = key
        self.settings_page.set_daily_status(f"❌ {msg}")

    def _on_wallpaper_ready(self, local_path: str):
        """
        壁纸已下载到本地，直接应用为背景（不修改 _user_bg_path）。
        wallpaper_ready 信号现在携带本地路径，无需再在主线程下载。
        """
        if not local_path or not os.path.isfile(local_path):
            return
        self._bg_path = local_path
        self._s.setValue("bg_path", local_path)
        self._bg.set_image(local_path)
        self._bg.set_fill_mode(self._bg_fill_mode)
        self._bg_colors = analyze_image_colors(local_path)
        self._bg.set_bg_colors(self._bg_colors)
        self._apply_theme()
        self.settings_page.set_daily_bg_preview(local_path)
        self.statusBar().showMessage("🌅 每日壁纸已更新", 4000)

    # ── Updater ──────────────────────────────────────────────────────
    def _on_check_update_requested(self):
        """用户点击"检查更新"按钮，启动后台检查。"""
        self._updater_svc.check()

    def _on_update_available(self, info: dict):
        """有新版本时弹窗提示，并在设置页显示状态。"""
        ver   = info.get("version", "?")
        date  = info.get("release_date", "")
        notes = info.get("release_notes", "")
        url   = info.get("update_url", "") or info.get("html_url", "") or info.get("zipball_url", "")
        required_update = _is_update_required(info)

        status = f"{'🚨' if required_update else '🆕'} 发现新版本 v{ver}"
        if date:
            status += f"  ({date})"
        if required_update:
            status += "  ·  需要更新"
        self.settings_page.set_update_status(status)
        self.settings_page.set_version_badge(True, ver)
        # 公告由 _on_versions_loaded 统一渲染（新版本+当前版本）

        # 检查是否用户选择过“不再显示”该版本的更新弹窗
        ignored_version = self._s.value("ignored_update_version", "")
        if ignored_version == ver and not required_update:
            return  # 如果该版本已经被忽略，直接返回不显示弹窗

        msg = f"发现新版本 <b>v{ver}</b>"
        if date:
            msg += f"  ({date})"
        if notes:
            msg += f"<br><br>更新说明：{notes}"
        if required_update:
            msg += "<br><br><b>此版本需要更新，当前版本已不再受支持。</b>"
        if url:
            msg += "<br><br>是否前往下载？"

        from PyQt6.QtWidgets import QCheckBox

        box = QMessageBox(self)
        box.setWindowTitle("发现新版本")
        box.setTextFormat(Qt.TextFormat.RichText)
        box.setText(msg)

        # 添加“不再显示”复选框
        cb_ignore = None
        if not required_update:
            cb_ignore = QCheckBox("不再显示此版本的更新提示")
            box.setCheckBox(cb_ignore)

        if url:
            if required_update:
                box.setStandardButtons(QMessageBox.StandardButton.Yes)
                box.button(QMessageBox.StandardButton.Yes).setText("立即下载")
            else:
                box.setStandardButtons(
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
                box.setDefaultButton(QMessageBox.StandardButton.Yes)
                box.button(QMessageBox.StandardButton.Yes).setText("立即下载")
                box.button(QMessageBox.StandardButton.No).setText("稍后再说")
        else:
            box.setStandardButtons(QMessageBox.StandardButton.Ok)

        result = box.exec()

        # 如果用户勾选了“不再显示”，保存该版本号到设置中
        if cb_ignore is not None and cb_ignore.isChecked():
            self._s.setValue("ignored_update_version", ver)

        if result == QMessageBox.StandardButton.Yes and url:
            self._start_internal_download(url, ver)

    def _start_internal_download(self, url: str, ver: str):
        """开始内部下载更新包并显示进度条"""
        from PyQt6.QtWidgets import QProgressDialog
        import os

        self._dl_progress = QProgressDialog(f"正在下载更新 v{ver}... (0%)", "取消", 0, 100, self)
        self._dl_progress.setWindowTitle("下载更新")
        # 修改为非模态，不阻塞主窗口操作
        self._dl_progress.setWindowModality(Qt.WindowModality.NonModal)
        self._dl_progress.setAutoClose(True)
        self._dl_progress.setAutoReset(True)
        self._dl_progress.setValue(0)

        # 固定进度条窗口大小，防止因为文本改变导致窗口一直闪烁和变形
        self._dl_progress.setFixedSize(350, 120)

        self._dl_thread = UpdateDownloaderThread(url, UPDATE_CACHE_DIR, self)

        def on_progress(bytes_read, total_size):
            if total_size > 0:
                percent = int(bytes_read * 100 / total_size)
                self._dl_progress.setLabelText(f"正在下载更新 v{ver}... ({percent}%)")
                self._dl_progress.setValue(percent)

        def on_finished(save_path, error_msg):
            self._dl_progress.close()
            if error_msg:
                if error_msg != "cancelled":
                    QMessageBox.warning(self, "下载失败", f"更新下载失败:\n{error_msg}")
            elif save_path and os.path.exists(save_path):
                self._on_download_complete(save_path)

        def on_cancel():
            self._dl_thread.cancel()

        self._dl_thread.progress.connect(on_progress)
        self._dl_thread.finished.connect(on_finished)
        self._dl_progress.canceled.connect(on_cancel)

        self._dl_thread.start()
        self._dl_progress.show()

    def _on_download_complete(self, save_path: str):
        """下载完成，准备运行安装包"""
        import platform
        import subprocess

        system = platform.system()
        if system in {"Darwin", "Linux"}:
            try:
                app_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
                replace_app_with_archive(save_path, app_root)
                QMessageBox.information(self, "更新完成", "已替换应用文件，请重新启动软件。")
            except Exception as e:
                QMessageBox.critical(self, "更新失败", f"无法替换应用文件:\n{str(e)}\n\n文件保存在: {save_path}")
                return
            from PyQt6.QtWidgets import QApplication
            QApplication.quit()
            return

        msg = QMessageBox(self)
        msg.setWindowTitle("下载完成")
        msg.setText("更新包下载完成，准备安装。软件将立即关闭。")
        msg.setStandardButtons(QMessageBox.StandardButton.Ok)
        msg.exec()

        try:
            if system == "Windows":
                # Windows 下使用 os.startfile 或 subprocess
                os.startfile(save_path)
        except Exception as e:
            QMessageBox.critical(self, "执行失败", f"无法自动运行安装包:\n{str(e)}\n\n文件保存在: {save_path}")
            return

        # 启动安装包后，退出当前应用
        from PyQt6.QtWidgets import QApplication
        QApplication.quit()

    def _on_versions_loaded(self, versions: list):
        """版本列表加载完成；构建更新公告（新版本在上，当前版本在下）。"""
        self.settings_page.populate_versions(versions)
        if not versions:
            self.settings_page.set_update_status("版本列表为空，请稍后重试")
            self.settings_page.set_update_notes("")
            return

        cur_tuple = _parse_version(APP_VERSION)
        latest_ver = versions[0].get("version", "")

        if _parse_version(latest_ver) <= cur_tuple:
            self.settings_page.set_update_status(
                f"✅ 当前已是最新版本 v{APP_VERSION}")
            self.settings_page.set_version_badge(False)

        # ── 构建公告：高于当前版本的在上，当前版本在下 ──────────────────
        newer_parts  = []
        current_part = None
        for v in versions:
            ver   = v.get("version", "")
            date  = v.get("release_date", "")
            notes = v.get("release_notes", "")
            if not ver:
                continue
            header = f"<b>v{ver}</b>"
            if date:
                header += f"  <span style='opacity:0.6'>({date})</span>"
            body = notes.replace("\n", "<br>") if notes else ""
            block = header + (f"<br>{body}" if body else "")
            if _parse_version(ver) > cur_tuple:
                newer_parts.append(block)
            elif _parse_version(ver) == cur_tuple:
                current_part = block

        sections = []
        if newer_parts:
            sections.append("<br><hr>".join(newer_parts))
        if current_part:
            label = "<span style='opacity:0.55'>当前版本</span>"
            if sections:
                sections.append(f"<hr>{label}<br>{current_part}")
            else:
                sections.append(f"{label}<br>{current_part}")

        self.settings_page.set_update_notes("<br>".join(sections))

    def _on_update_check_failed(self, err: str):
        """版本检查失败，翻译为中文后显示在设置页。"""
        if err.startswith("url_error:"):
            msg = f"网络错误: {err[10:]}"
        elif err.startswith("error:"):
            msg = f"检查失败: {err[6:]}"
        else:
            msg = f"检查失败: {err}"
        self.settings_page.set_update_status(f"❌ {msg}")

    def _on_download_ffmpeg_requested(self):
        from PyQt6.QtWidgets import QProgressDialog

        if self._ffmpeg_ready and self.ffmpeg_handler is not None:
            self.settings_page.set_ffmpeg_status("已检测到 FFmpeg，无需重复更新。", downloading=False)
            return

        action = self._ffmpeg_action_text()

        self._ffmpeg_progress = QProgressDialog(f"正在{action} FFmpeg... (0%)", "取消", 0, 100, self)
        self._ffmpeg_progress.setWindowTitle(f"{action} FFmpeg")
        self._ffmpeg_progress.setWindowModality(Qt.WindowModality.NonModal)
        self._ffmpeg_progress.setAutoClose(True)
        self._ffmpeg_progress.setAutoReset(True)
        self._ffmpeg_progress.setValue(0)
        self._ffmpeg_progress.setFixedSize(360, 120)

        self._ffmpeg_dl_thread = FFmpegDownloadThread(
            get_ffmpeg_download_spec(), FFMPEG_CACHE_DIR, FFMPEG_DIR, self)

        def on_progress(done, total, stage):
            if stage.startswith("download"):
                percent = int(done * 100 / total) if total > 0 else 0
                self._ffmpeg_progress.setLabelText(f"正在{action} FFmpeg... ({percent}%)")
                self._ffmpeg_progress.setValue(percent)
                self.settings_page.set_ffmpeg_status(
                    f"正在{action} FFmpeg... {percent}%", downloading=True)
            else:
                percent = int(done * 100 / total) if total > 0 else 0
                self._ffmpeg_progress.setLabelText(f"正在解压 FFmpeg... ({percent}%)")
                self._ffmpeg_progress.setValue(percent)
                self.settings_page.set_ffmpeg_status(
                    f"正在解压 FFmpeg... {percent}%", downloading=True)

        def on_finished(success, message):
            self._ffmpeg_progress.close()
            if not success:
                if message != "cancelled":
                    QMessageBox.warning(self, f"FFmpeg{action}失败", f"FFmpeg{action}失败：\n{message}")
                    self.settings_page.set_ffmpeg_status(
                        f"FFmpeg{action}失败：{message}", downloading=False)
                else:
                    self.settings_page.set_ffmpeg_status(f"已取消 FFmpeg{action}。", downloading=False)
                return

            try:
                self.ffmpeg_handler = FFmpegHandler()
                self._ffmpeg_ready = True
            except FileNotFoundError as e:
                self.ffmpeg_handler = None
                self._ffmpeg_ready = False
                QMessageBox.warning(self, "FFmpeg 安装异常", str(e))
                self.settings_page.set_ffmpeg_status(str(e), downloading=False)
                return

            self._attach_ffmpeg_handler_to_pages()
            self._connect_ffmpeg_handler_signals()
            self._update_ffmpeg_status_ui()
            self.statusBar().showMessage(f"FFmpeg{action}并安装完成", 5000)
            QMessageBox.information(self, f"{action}完成", f"FFmpeg 已{action.lower()}并安装完成。")

        def on_cancel():
            self._ffmpeg_dl_thread.cancel()

        self._ffmpeg_dl_thread.progress.connect(on_progress)
        self._ffmpeg_dl_thread.finished.connect(on_finished)
        self._ffmpeg_progress.canceled.connect(on_cancel)

        self.settings_page.set_ffmpeg_status(f"正在准备{action} FFmpeg…", downloading=True)
        self._ffmpeg_dl_thread.start()
        self._ffmpeg_progress.show()

    def _connect_ffmpeg_handler_signals(self):
        if not self.ffmpeg_handler:
            return
        try:
            self.ffmpeg_handler.conversion_started.disconnect(self._on_started)
        except Exception:
            pass
        try:
            self.ffmpeg_handler.progress_update.disconnect(self._on_progress)
        except Exception:
            pass
        try:
            self.ffmpeg_handler.conversion_finished.disconnect(self._on_finished)
        except Exception:
            pass
        try:
            self.ffmpeg_handler.log_line.disconnect(self._on_log_line)
        except Exception:
            pass
        self.ffmpeg_handler.conversion_started.connect(self._on_started)
        self.ffmpeg_handler.progress_update.connect(self._on_progress)
        self.ffmpeg_handler.conversion_finished.connect(self._on_finished)
        self.ffmpeg_handler.log_line.connect(self._on_log_line)

    def _attach_ffmpeg_handler_to_pages(self):
        handler = self.ffmpeg_handler
        if not handler:
            return

        for pg in (self.video_page, self.audio_page, self.image_page, self.m3u8_page):
            pg.ffmpeg_handler = handler
            try:
                handler.file_info_ready.connect(pg.handle_file_info_ready)
            except Exception:
                pass

        self.command_page.attach_ffmpeg_handler(handler)

        self.audio_page.ffmpeg_handler = handler
        try:
            handler.conversion_finished.connect(self.audio_page._on_conversion_finished)
        except Exception:
            pass

        self.av_page._handler = handler
        self.av_page.split_tab._handler = handler
        self.av_page.merge_tab._handler = handler
        try:
            handler.file_info_ready.connect(self.av_page.split_tab._on_file_info)
        except Exception:
            pass

    # ── Theme ────────────────────────────────────────────────────────
    def _on_theme_changed(self, mode):
        self._theme_name = mode
        self._s.setValue("theme", mode)
        self._apply_theme()

    def _on_blur_changed(self, level):
        self._blur_level = level
        self._s.setValue("blur", level)
        self._bg.set_blur(level)
        self._apply_theme()

    def _on_mask_opacity_changed(self, pct: int):
        self._bg_opacity = pct
        self._s.setValue("mask_opacity", pct)
        self._bg.set_bg_opacity(pct)

    def _on_language_changed(self, language: str):
        self._language_pref = language or LANG_AUTO
        self._s.setValue("language", self._language_pref)
        self._apply_language()
        box = QMessageBox(self)
        box.setIcon(QMessageBox.Icon.Information)
        box.setWindowTitle(self._tr("language_restart_title"))
        box.setText(self._tr("language_restart_msg"))
        now_btn = box.addButton(self._tr("language_restart_now"), QMessageBox.ButtonRole.AcceptRole)
        box.addButton(self._tr("language_restart_later"), QMessageBox.ButtonRole.RejectRole)
        box.exec()
        if box.clickedButton() is now_btn:
            self.close()

    def _apply_command_line_enabled(self, enabled: bool):
        enabled = bool(enabled)
        self._command_line_enabled = enabled
        if hasattr(self, "settings_page") and self.settings_page is not None:
            self.settings_page.set_command_line_enabled(enabled)
        if hasattr(self, "command_page") and self.command_page is not None:
            self.command_page.setEnabled(enabled)
        if hasattr(self, "tab_widget") and hasattr(self, "_command_tab_index"):
            if hasattr(self.tab_widget, "setTabVisible"):
                self.tab_widget.setTabVisible(self._command_tab_index, enabled)
            else:
                self.tab_widget.setTabEnabled(self._command_tab_index, enabled)
            if not enabled and self.tab_widget.currentIndex() == self._command_tab_index:
                self.tab_widget.setCurrentWidget(self.video_page)
                self.current_page = self.video_page

    def _on_command_line_toggled(self, enabled: bool):
        self._s.setValue("command_line_enabled", bool(enabled))
        self._apply_command_line_enabled(enabled)
        state = self._tr("command_enabled") if enabled else self._tr("command_disabled")
        self.statusBar().showMessage(f"{self._tr('command_section')}{state}", 4000)

    def _on_bg_fill_mode_changed(self, mode: str):
        mode = mode if mode in {"stretch", "none", "fit", "cover"} else "cover"
        self._bg_fill_mode = mode
        self._s.setValue("bg_fill_mode", mode)
        self._bg.set_fill_mode(mode)

    def _on_bg_changed(self, path):
        # 用户手动选择了背景图片，若每日壁纸正在运行则自动关闭
        if path and self._daily_enabled:
            self._daily_enabled = False
            self._s.setValue("daily_wp", False)
            self._wallpaper_svc.stop()
            self.settings_page._daily_enabled = False
            self.settings_page._refresh_daily_ui()

        self._bg_path = path
        self._s.setValue("bg_path", path)
        self._bg.set_image(path)
        self._bg.set_fill_mode(self._bg_fill_mode)
        self._bg_colors = analyze_image_colors(path) if path else {}
        self._bg.set_bg_colors(self._bg_colors)
        self._apply_theme()
        # 记录用户手动选择的背景（每日壁纸不走这里，不会覆盖）
        self._user_bg_path = path
        self._s.setValue("user_bg_path", path)

    def _apply_theme(self):
        actual_mode = self._effective_theme_name()
        theme  = LIGHT_THEME if actual_mode == "light" else DARK_THEME
        has_bg = bool(self._bg_path and os.path.isfile(self._bg_path))
        ss     = build_stylesheet(theme, actual_mode, has_bg, self._bg_colors)
        self.setStyleSheet(ss)
        self._bg.set_dark(actual_mode == "dark")
        self._bg.set_mask_color(actual_mode == "dark")
        mode = actual_mode
        for pg in (self.video_page, self.audio_page,
                   self.image_page, self.m3u8_page,
                   self.command_page,
                   self.av_page):
            pg.set_theme(mode, self._bg_colors)
        self.settings_page.set_theme(self._theme_name, self._bg_colors, resolved_mode=actual_mode)


# ══════════════════════════════════════════════════════════════════
def run_app():
    app = QApplication(sys.argv)
    app.setApplicationName("格式转换通")
    app.setOrganizationName("Formix")
    w = MainWindow()
    w.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    sys.path.insert(0, os.path.dirname(os.path.dirname(
        os.path.abspath(__file__))))
    run_app()
