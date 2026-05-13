# format_factory/daily_wallpaper.py
"""
每日壁纸服务。

- API  : 默认 JSON API，支持自定义 JSON / 纯文本 URL API
- 缓存 : wallpaper_cache/meta.json  +  wallpaper_cache/<图片文件>
- 策略 :
    · 启动时根据当前生效策略判断是否复用缓存
    · 刷新天数支持 1-7 天与 manual（仅手动刷新）
    · 切换刷新策略次日生效，当天不立即重判缓存
    · 零点仅推进待生效策略并检查是否到期，不强制清缓存
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
_SUPPORTED_REFRESH_DAYS = {1, 2, 3, 4, 5, 6, 7}
_MANUAL_REFRESH = "manual"
_IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".gif"}
_CONTENT_TYPE_TO_EXT = {
    "image/jpeg": ".jpg",
    "image/jpg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
    "image/bmp": ".bmp",
    "image/gif": ".gif",
}
_PREFERRED_IMAGE_URL_KEYS = (
    "url", "imgurl", "imageurl", "image_url", "acgurl",
    "picurl", "pic_url", "wallpaper_url", "image", "img", "src",
)


def normalize_custom_api_url(value: str) -> tuple[str, str]:
    text = str(value or "").strip()
    if not text:
        return "", ""

    if any(ch.isspace() for ch in text):
        return "", "multiple_links"

    proto_count = text.count("http://") + text.count("https://")
    if proto_count > 1:
        return "", "multiple_links"

    if "://" not in text:
        text = f"http://{text.lstrip('/')}"

    parsed = urllib.parse.urlsplit(text)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return "", "invalid_api_url"

    return urllib.parse.urlunsplit(parsed), ""


def _normalize_api_url(value: str) -> str:
    normalized, _ = normalize_custom_api_url(value)
    return normalized


def _normalize_refresh_days(value):
    if isinstance(value, str):
        text = value.strip().lower()
        if text == _MANUAL_REFRESH:
            return _MANUAL_REFRESH
        if text.isdigit():
            num = int(text)
            if num in _SUPPORTED_REFRESH_DAYS:
                return num
    elif isinstance(value, int) and value in _SUPPORTED_REFRESH_DAYS:
        return value
    return 1


def _iso_to_date(value) -> date | None:
    try:
        return datetime.strptime(str(value), "%Y-%m-%d").date()
    except Exception:
        return None


def _default_meta() -> dict:
    return {
        "date": "",
        "fetched_on": "",
        "url": "",
        "local_path": "",
        "size": "",
        "width": 0,
        "height": 0,
        "api_url": "",
        "effective_refresh_days": 1,
        "pending_refresh_days": None,
        "refresh_days_apply_on": "",
    }


def _read_meta() -> dict:
    if not os.path.isfile(_META_FILE):
        return {}
    try:
        with open(_META_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict):
            return data
    except Exception:
        pass
    return {}


def _write_meta(meta: dict):
    os.makedirs(_CACHE_DIR, exist_ok=True)
    payload = dict(_default_meta())
    payload.update(meta or {})
    with open(_META_FILE, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)


def _guess_image_ext(url: str, content_type: str = "") -> str:
    content_type = str(content_type or "").split(";", 1)[0].strip().lower()
    if content_type in _CONTENT_TYPE_TO_EXT:
        return _CONTENT_TYPE_TO_EXT[content_type]

    parsed = urllib.parse.urlsplit(str(url or "").strip())
    raw_name = parsed.path.split("/")[-1].split("?")[0]
    ext = os.path.splitext(raw_name)[1].lower()
    return ext if ext in _IMAGE_EXTENSIONS else ".jpg"


def _to_int(value, default: int = 0) -> int:
    try:
        return int(str(value).strip())
    except Exception:
        return default


def _is_http_url(value) -> bool:
    text = str(value or "").strip()
    return text.startswith(("http://", "https://"))


def _looks_like_image_url(value) -> bool:
    if not _is_http_url(value):
        return False
    parsed = urllib.parse.urlsplit(str(value).strip())
    ext = os.path.splitext(parsed.path)[1].lower()
    return (not ext) or (ext in _IMAGE_EXTENSIONS)


def _find_scalar_by_keys(data, candidate_keys: tuple[str, ...]):
    if isinstance(data, dict):
        lowered = {str(k).strip().lower(): v for k, v in data.items()}
        for key in candidate_keys:
            if key in lowered:
                return lowered[key]
        for value in data.values():
            found = _find_scalar_by_keys(value, candidate_keys)
            if found not in (None, ""):
                return found
    elif isinstance(data, list):
        for item in data:
            found = _find_scalar_by_keys(item, candidate_keys)
            if found not in (None, ""):
                return found
    return None


def _find_image_url_in_json(data) -> str:
    if isinstance(data, dict):
        lowered = {str(k).strip().lower(): v for k, v in data.items()}

        for key in _PREFERRED_IMAGE_URL_KEYS:
            value = lowered.get(key)
            if _looks_like_image_url(value):
                return str(value).strip()

        for key, value in lowered.items():
            if "url" in key and _looks_like_image_url(value):
                return str(value).strip()

        for value in lowered.values():
            found = _find_image_url_in_json(value)
            if found:
                return found

    elif isinstance(data, list):
        for item in data:
            found = _find_image_url_in_json(item)
            if found:
                return found

    elif _looks_like_image_url(data):
        return str(data).strip()

    return ""


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
    finished = pyqtSignal(int, str, str, dict)   # (request_token, local_path, error_key, fetched_meta)

    def __init__(self, request_token: int, api_url: str, parent=None):
        super().__init__(parent)
        self._request_token = request_token
        self._api_url = _normalize_api_url(api_url)

    def run(self):
        os.makedirs(_CACHE_DIR, exist_ok=True)
        try:
            # 1. 请求 API
            req = urllib.request.Request(
                self._api_url,
                headers={"User-Agent": "Mozilla/5.0 FormatFactory/2.1"})
            with urllib.request.urlopen(req, timeout=_TIMEOUT) as resp:
                content_type = str(resp.headers.get("Content-Type", "") or "")
                final_url = str(resp.geturl() or self._api_url)
                raw_bytes = resp.read()

            size = ""
            width = 0
            height = 0
            img_url = ""
            image_bytes = b""
            image_content_type = ""

            if content_type.lower().startswith("image/"):
                img_url = final_url
                image_bytes = raw_bytes
                image_content_type = content_type
            else:
                raw = raw_bytes.decode("utf-8", errors="replace").strip()
                try:
                    data = json.loads(raw)
                except json.JSONDecodeError:
                    data = None

                if isinstance(data, dict):
                    img_url = _find_image_url_in_json(data)
                    size = str(_find_scalar_by_keys(data, ("size", "ext", "suffix", "format")) or "")
                    width = _to_int(_find_scalar_by_keys(data, ("width", "imgwidth", "imagewidth")))
                    height = _to_int(_find_scalar_by_keys(data, ("height", "imgheight", "imageheight")))
                elif isinstance(data, list):
                    img_url = _find_image_url_in_json(data)
                elif raw.startswith(("http://", "https://")):
                    img_url = raw

            if not img_url:
                self.finished.emit(self._request_token, "", "invalid_response", {})
                return

            # 2. 对 URL 做 percent-encoding
            parsed   = urllib.parse.urlsplit(img_url)
            safe_url = urllib.parse.urlunsplit(
                parsed._replace(
                    path=urllib.parse.quote(parsed.path, safe="/%")))

            # 3. 推断文件名（含日期前缀，防止同名覆盖）
            ext = _guess_image_ext(img_url, image_content_type)
            fname      = f"{date.today()}_wallpaper{ext}"
            local_path = os.path.join(_CACHE_DIR, fname)

            # 4. 下载图片
            if not image_bytes:
                req2 = urllib.request.Request(
                    safe_url,
                    headers={"User-Agent": "Mozilla/5.0 FormatFactory/2.1"})
                with urllib.request.urlopen(req2, timeout=_TIMEOUT) as resp2:
                    raw_bytes = resp2.read()
            else:
                raw_bytes = image_bytes
            with open(local_path, "wb") as f:
                f.write(raw_bytes)

            meta = {
                "date": str(date.today()),
                "fetched_on": str(date.today()),
                "url": img_url,
                "local_path": local_path,
                "size": size,
                "width": width,
                "height": height,
                "api_url": self._api_url,
            }
            self.finished.emit(self._request_token, local_path, "", meta)

        except urllib.error.URLError as e:
            reason = str(e.reason).encode("ascii", "replace").decode("ascii")
            self.finished.emit(self._request_token, "", f"url_error:{reason}", {})
        except Exception as e:
            msg = str(e).encode("ascii", "replace").decode("ascii")
            self.finished.emit(self._request_token, "", f"error:{msg}", {})


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
        self._request_token = 0
        self._pending_refresh = False
        self._api_url = ""
        self._effective_refresh_days = 1
        self._pending_refresh_days = None
        self._refresh_days_apply_on = None

        self._midnight_timer = QTimer(self)
        self._midnight_timer.setSingleShot(True)
        self._midnight_timer.timeout.connect(self._on_midnight)

    def set_api_url(self, api_url: str):
        self._api_url = _normalize_api_url(api_url)

    def load_preferences(self, api_url: str, refresh_days):
        self._api_url = _normalize_api_url(api_url)
        meta = _read_meta()
        if meta:
            self._effective_refresh_days = _normalize_refresh_days(
                meta.get("effective_refresh_days", refresh_days)
            )
            pending = meta.get("pending_refresh_days")
            self._pending_refresh_days = None if pending in (None, "", "None") else _normalize_refresh_days(pending)
            self._refresh_days_apply_on = _iso_to_date(meta.get("refresh_days_apply_on"))
            self._persist_policy_state()
            return
        self._effective_refresh_days = _normalize_refresh_days(refresh_days)
        self._pending_refresh_days = None
        self._refresh_days_apply_on = None
        self._persist_policy_state()

    def set_refresh_policy(self, refresh_days):
        normalized = _normalize_refresh_days(refresh_days)
        if not _read_meta() and not self._enabled and self._pending_refresh_days is None:
            self._effective_refresh_days = normalized
            self._persist_policy_state()
            return
        apply_on = date.today() + timedelta(days=1)
        self._pending_refresh_days = normalized
        self._refresh_days_apply_on = apply_on
        self._persist_policy_state()

    def current_policy(self):
        return {
            "api_url": self._api_url,
            "effective_refresh_days": self._effective_refresh_days,
            "pending_refresh_days": self._pending_refresh_days,
            "refresh_days_apply_on": str(self._refresh_days_apply_on) if self._refresh_days_apply_on else "",
        }

    # ── 公开接口 ──────────────────────────────────────────────────────
    def start(self):
        """启用服务：根据当前生效策略决定是否使用缓存；安排次日零点检查。"""
        self._enabled = True
        self._pending_refresh = False
        self._load_state_from_meta()
        self._promote_pending_policy_if_due()
        self._try_use_cache_or_fetch()
        self._schedule_midnight()

    def stop(self):
        """禁用服务，停止零点定时器（不清缓存）。"""
        self._enabled = False
        self._pending_refresh = False
        self._request_token += 1
        self._midnight_timer.stop()

    def force_refresh(self):
        """
        手动强制刷新：
          1. 清除图片缓存
          2. 重新从当前 API 获取并下载
        """
        self._purge_cached_image_only()
        self._pending_refresh = True
        self._request_token += 1
        if self._fetch():
            self._pending_refresh = False

    def cached_local_path(self) -> str:
        """按当前生效策略返回可复用的本地缓存路径。"""
        meta = _read_meta()
        if not meta:
            return ""
        path = meta.get("local_path", "")
        if not (path and os.path.isfile(path)):
            return ""
        fetched_on = _iso_to_date(meta.get("fetched_on") or meta.get("date"))
        if not fetched_on:
            return ""
        if self._effective_refresh_days == _MANUAL_REFRESH:
            return path
        refresh_days = _normalize_refresh_days(self._effective_refresh_days)
        if not isinstance(refresh_days, int):
            refresh_days = 1
        delta = (date.today() - fetched_on).days
        return path if delta < refresh_days else ""

    # ── 内部 ──────────────────────────────────────────────────────────
    def _try_use_cache_or_fetch(self):
        path = self.cached_local_path()
        if path:
            self.status_changed.emit("cached")
            self.wallpaper_ready.emit(path)
        else:
            self._purge_cached_image_only()
            self._pending_refresh = True
            self._request_token += 1
            if self._fetch():
                self._pending_refresh = False

    def _fetch(self):
        if self._fetch_thread and self._fetch_thread.isRunning():
            return False
        if not self._api_url:
            self.status_changed.emit("fail:no_api")
            self.error_occurred.emit("no_api")
            return False
        self.status_changed.emit("fetching")
        self._fetch_thread = _FetchThread(self._request_token, self._api_url, self)
        self._fetch_thread.finished.connect(self._on_fetch_done)
        self._fetch_thread.start()
        return True

    def _on_fetch_done(self, request_token: int, local_path: str, err: str, fetched_meta: dict):
        if self.sender() is self._fetch_thread:
            self._fetch_thread = None

        if request_token != self._request_token:
            if self._enabled and self._pending_refresh:
                if self._fetch():
                    self._pending_refresh = False
            return

        self._pending_refresh = False
        if not self._enabled:
            return

        if err:
            self.status_changed.emit(f"fail:{err}")
            self.error_occurred.emit(err)
        else:
            meta = dict(_default_meta())
            meta.update(_read_meta())
            meta.update(fetched_meta or {})
            meta["api_url"] = self._api_url
            meta["effective_refresh_days"] = self._effective_refresh_days
            meta["pending_refresh_days"] = self._pending_refresh_days
            meta["refresh_days_apply_on"] = str(self._refresh_days_apply_on) if self._refresh_days_apply_on else ""
            _write_meta(meta)
            self.status_changed.emit("done")
            self.wallpaper_ready.emit(local_path)

    def _schedule_midnight(self):
        now = datetime.now()
        nxt = datetime.combine(now.date() + timedelta(days=1),
                               datetime.min.time())
        ms  = max(int((nxt - now).total_seconds() * 1000), 1000)
        self._midnight_timer.start(ms)

    def _on_midnight(self):
        """零点：推进待生效策略 → 检查缓存是否过期 → 安排下一个零点。"""
        if not self._enabled:
            return
        self._promote_pending_policy_if_due()
        self._try_use_cache_or_fetch()
        self._schedule_midnight()

    def _purge_cached_image_only(self):
        meta = _read_meta()
        local_path = meta.get("local_path", "")
        if local_path and os.path.isfile(local_path):
            try:
                os.remove(local_path)
            except OSError:
                pass
        meta["local_path"] = ""
        meta["url"] = ""
        meta["size"] = ""
        meta["width"] = 0
        meta["height"] = 0
        meta["date"] = ""
        meta["fetched_on"] = ""
        _write_meta(meta)

    def _load_state_from_meta(self):
        meta = _read_meta()
        self._api_url = _normalize_api_url(meta.get("api_url", self._api_url))
        self._effective_refresh_days = _normalize_refresh_days(
            meta.get("effective_refresh_days", self._effective_refresh_days)
        )
        pending = meta.get("pending_refresh_days")
        self._pending_refresh_days = None if pending in (None, "", "None") else _normalize_refresh_days(pending)
        self._refresh_days_apply_on = _iso_to_date(meta.get("refresh_days_apply_on"))

    def _persist_policy_state(self):
        meta = _read_meta()
        meta["api_url"] = self._api_url
        meta["effective_refresh_days"] = self._effective_refresh_days
        meta["pending_refresh_days"] = self._pending_refresh_days
        meta["refresh_days_apply_on"] = str(self._refresh_days_apply_on) if self._refresh_days_apply_on else ""
        _write_meta(meta)

    def _promote_pending_policy_if_due(self):
        if not self._pending_refresh_days or not self._refresh_days_apply_on:
            return
        if date.today() < self._refresh_days_apply_on:
            return
        self._effective_refresh_days = self._pending_refresh_days
        self._pending_refresh_days = None
        self._refresh_days_apply_on = None
        self._persist_policy_state()
