# format_factory/daily_wallpaper.py
"""
每日壁纸服务。

- API  : https://i.xiaofa520.top/?type=json
- 响应 : {"url": "...", "size": "...", "width": ..., "height": ...}
- 缓存 : wallpaper_cache/meta.json  +  wallpaper_cache/<图片文件>
- 策略 :
    · 启动时检查当日缓存，有则直接用，无则请求 API 并下载图片
    · 每天 00:00 自动清除旧缓存（JSON + 图片），再重新获取
    · 手动刷新 / 零点触发时均先清除所有缓存再重新下载
- 线程 : 网络请求 + 图片下载在后台线程完成，结果通过信号通知主线程
"""
import os
import json
import urllib.request
import urllib.error
import urllib.parse
from datetime import date, datetime, timedelta

from PyQt6.QtCore import QObject, pyqtSignal, QTimer, QThread


# ── 缓存路径 ──────────────────────────────────────────────────────────
_CACHE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                          "wallpaper_cache")
_META_FILE = os.path.join(_CACHE_DIR, "meta.json")
_API_URL   = "https://i.xiaofa520.top/?type=json"
_TIMEOUT   = 15  # 秒


def _purge_cache_files():
    """
    删除缓存目录中所有壁纸图片文件及 meta.json。
    可在任意线程调用（仅做文件 I/O）。
    """
    # 先读取 meta 获得图片路径，再删除
    if os.path.isfile(_META_FILE):
        try:
            with open(_META_FILE, "r", encoding="utf-8") as f:
                meta = json.load(f)
            img_path = meta.get("local_path", "")
            if img_path and os.path.isfile(img_path):
                os.remove(img_path)
        except Exception:
            pass
        try:
            os.remove(_META_FILE)
        except OSError:
            pass

    # 保底：删除缓存目录中所有图片文件（防止残留）
    if os.path.isdir(_CACHE_DIR):
        for name in os.listdir(_CACHE_DIR):
            if name == "meta.json":
                continue
            ext = os.path.splitext(name)[1].lower()
            if ext in (".jpg", ".jpeg", ".png", ".webp", ".bmp", ".gif"):
                try:
                    os.remove(os.path.join(_CACHE_DIR, name))
                except OSError:
                    pass


# ── 后台下载线程 ──────────────────────────────────────────────────────
class _FetchThread(QThread):
    """在子线程里完成 API 请求 + 图片下载，不阻塞 UI。"""
    finished = pyqtSignal(str, str)   # (local_path, error_key)

    def run(self):
        os.makedirs(_CACHE_DIR, exist_ok=True)
        try:
            # 1. 请求 API
            req = urllib.request.Request(
                _API_URL,
                headers={"User-Agent": "Mozilla/5.0 FormatFactory/2.1"})
            with urllib.request.urlopen(req, timeout=_TIMEOUT) as resp:
                data = json.loads(resp.read().decode("utf-8"))

            img_url = data.get("url", "").strip()
            if not img_url:
                self.finished.emit("", "no_url")
                return

            # 2. 对 URL 做 percent-encoding
            parsed   = urllib.parse.urlsplit(img_url)
            safe_url = urllib.parse.urlunsplit(
                parsed._replace(
                    path=urllib.parse.quote(parsed.path, safe="/%")))

            # 3. 推断文件名（含日期前缀，防止同名覆盖）
            raw_name = parsed.path.split("/")[-1].split("?")[0]
            ext = os.path.splitext(raw_name)[1].lower()
            if ext not in (".jpg", ".jpeg", ".png", ".webp", ".bmp", ".gif"):
                ext = ".jpg"
            fname      = f"{date.today()}_wallpaper{ext}"
            local_path = os.path.join(_CACHE_DIR, fname)

            # 4. 下载图片
            req2 = urllib.request.Request(
                safe_url,
                headers={"User-Agent": "Mozilla/5.0 FormatFactory/2.1"})
            with urllib.request.urlopen(req2, timeout=_TIMEOUT) as resp2:
                raw_bytes = resp2.read()
            with open(local_path, "wb") as f:
                f.write(raw_bytes)

            # 5. 写 meta.json
            meta = {
                "date":       str(date.today()),
                "url":        img_url,
                "local_path": local_path,
                "size":       data.get("size", ""),
                "width":      data.get("width", 0),
                "height":     data.get("height", 0),
            }
            with open(_META_FILE, "w", encoding="utf-8") as f:
                json.dump(meta, f, ensure_ascii=False, indent=2)

            self.finished.emit(local_path, "")

        except urllib.error.URLError as e:
            reason = str(e.reason).encode("ascii", "replace").decode("ascii")
            self.finished.emit("", f"url_error:{reason}")
        except Exception as e:
            msg = str(e).encode("ascii", "replace").decode("ascii")
            self.finished.emit("", f"error:{msg}")


# ── 主服务对象 ────────────────────────────────────────────────────────
class DailyWallpaperService(QObject):
    """
    使用方式：
        svc = DailyWallpaperService()
        svc.wallpaper_ready.connect(lambda local_path: ...)
        svc.status_changed.connect(lambda key: ...)
        svc.error_occurred.connect(lambda msg: ...)
        svc.start()

    信号：
        wallpaper_ready(str)  — 图片本地路径（已下载完成）
        status_changed(str)   — "fetching" / "cached" / "done" / "fail:…"
        error_occurred(str)   — 错误描述
    """
    wallpaper_ready = pyqtSignal(str)
    status_changed  = pyqtSignal(str)
    error_occurred  = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._enabled      = False
        self._fetch_thread = None

        self._midnight_timer = QTimer(self)
        self._midnight_timer.setSingleShot(True)
        self._midnight_timer.timeout.connect(self._on_midnight)

    # ── 公开接口 ──────────────────────────────────────────────────────
    def start(self):
        """启用服务：有今日缓存直接用，否则重新获取；安排次日零点触发。"""
        self._enabled = True
        self._try_use_cache_or_fetch()
        self._schedule_midnight()

    def stop(self):
        """禁用服务，停止零点定时器（不清缓存）。"""
        self._enabled = False
        self._midnight_timer.stop()

    def force_refresh(self):
        """
        手动强制刷新：
          1. 清除所有缓存（JSON + 图片文件）
          2. 重新从 API 获取并下载
        """
        _purge_cache_files()
        self._fetch()

    def cached_local_path(self) -> str:
        """返回今天已缓存的本地图片路径，不存在则返回空字符串。"""
        if not os.path.isfile(_META_FILE):
            return ""
        try:
            with open(_META_FILE, "r", encoding="utf-8") as f:
                meta = json.load(f)
        except Exception:
            return ""
        if meta.get("date") != str(date.today()):
            return ""
        path = meta.get("local_path", "")
        return path if (path and os.path.isfile(path)) else ""

    # ── 内部 ──────────────────────────────────────────────────────────
    def _try_use_cache_or_fetch(self):
        path = self.cached_local_path()
        if path:
            self.status_changed.emit("cached")
            self.wallpaper_ready.emit(path)
        else:
            _purge_cache_files()   # 清除过期缓存
            self._fetch()

    def _fetch(self):
        if self._fetch_thread and self._fetch_thread.isRunning():
            return
        self.status_changed.emit("fetching")
        self._fetch_thread = _FetchThread(self)
        self._fetch_thread.finished.connect(self._on_fetch_done)
        self._fetch_thread.start()

    def _on_fetch_done(self, local_path: str, err: str):
        if err:
            self.status_changed.emit(f"fail:{err}")
            self.error_occurred.emit(err)
        else:
            self.status_changed.emit("done")
            self.wallpaper_ready.emit(local_path)

    def _schedule_midnight(self):
        now = datetime.now()
        nxt = datetime.combine(now.date() + timedelta(days=1),
                               datetime.min.time())
        ms  = max(int((nxt - now).total_seconds() * 1000), 1000)
        self._midnight_timer.start(ms)

    def _on_midnight(self):
        """零点：清除旧缓存 → 重新获取 → 安排下一个零点。"""
        if not self._enabled:
            return
        _purge_cache_files()
        self._fetch()
        self._schedule_midnight()