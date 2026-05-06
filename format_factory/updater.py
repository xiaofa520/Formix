# format_factory/updater.py
"""
版本检查与更新服务。

- API: https://formix.xiaofa520.cn/updates/versions.json
- 响应: 版本列表数组，每项含 version/release_date/update_url/release_notes/mandatory/min_supported_version
- 策略: 启动时后台检查，有新版本则通过信号通知主线程弹窗提示
- 降级: 从版本列表里取最新5个（除当前版本）供用户自选降级
"""
import json
import urllib.request
import urllib.error
import os

from PyQt6.QtCore import QObject, pyqtSignal, QThread

_API_URL = "https://formix.xiaofa520.cn/updates/versions.json"
_TIMEOUT = 10


def _parse_version(v: str) -> tuple:
    """把 '1.2.3' 转成 (1, 2, 3) 便于比较大小。"""
    try:
        return tuple(int(x) for x in str(v).strip().split("."))
    except Exception:
        return (0, 0, 0)


# ── 后台检查线程 ──────────────────────────────────────────────────────
class _CheckThread(QThread):
    """在子线程里请求版本 API，不阻塞 UI。"""
    finished = pyqtSignal(list, str)   # (versions_list, error_ascii)

    def run(self):
        try:
            req = urllib.request.Request(
                _API_URL,
                headers={"User-Agent": "Mozilla/5.0 FormatFactory/1.0"})
            with urllib.request.urlopen(req, timeout=_TIMEOUT) as resp:
                raw = resp.read().decode("utf-8").strip()

            # 严格解析：响应必须是合法 JSON，否则直接报错
            try:
                data = json.loads(raw)
            except json.JSONDecodeError:
                self.finished.emit([], "error:invalid_json")
                return

            # 支持根对象是列表或含 "versions" 键的对象
            if isinstance(data, list):
                versions = data
            elif isinstance(data, dict):
                versions = data.get("versions", [data])
            else:
                versions = []
            self.finished.emit(versions, "")
        except urllib.error.URLError as e:
            reason = str(e.reason).encode("ascii", "replace").decode("ascii")
            self.finished.emit([], f"url_error:{reason}")
        except Exception as e:
            msg = str(e).encode("ascii", "replace").decode("ascii")
            self.finished.emit([], f"error:{msg}")

# ── 后台下载线程 ──────────────────────────────────────────────────────
class UpdateDownloaderThread(QThread):
    """在后台下载安装包，提供进度回调。"""
    progress = pyqtSignal(int, int) # bytes_read, total_size
    finished = pyqtSignal(str, str) # file_path, error_msg

    def __init__(self, url: str, save_dir: str, parent=None):
        super().__init__(parent)
        self.url = url
        self.save_dir = save_dir
        self._is_cancelled = False

    def cancel(self):
        self._is_cancelled = True

    def run(self):
        try:
            if not os.path.exists(self.save_dir):
                os.makedirs(self.save_dir, exist_ok=True)

            # 解析文件名
            file_name = self.url.split("/")[-1]
            if not file_name:
                file_name = "Formix_Update.exe"

            save_path = os.path.join(self.save_dir, file_name)

            req = urllib.request.Request(
                self.url,
                headers={"User-Agent": "Mozilla/5.0 FormatFactory/1.0"}
            )
            with urllib.request.urlopen(req, timeout=15) as response:
                total_size = int(response.info().get("Content-Length", 0))
                bytes_read = 0
                chunk_size = 8192

                with open(save_path, "wb") as f:
                    while True:
                        if self._is_cancelled:
                            f.close()
                            if os.path.exists(save_path):
                                os.remove(save_path)
                            self.finished.emit("", "cancelled")
                            return

                        chunk = response.read(chunk_size)
                        if not chunk:
                            break
                        f.write(chunk)
                        bytes_read += len(chunk)

                        if total_size > 0:
                            self.progress.emit(bytes_read, total_size)

            self.finished.emit(save_path, "")

        except Exception as e:
            self.finished.emit("", str(e))


# ── 主服务对象 ────────────────────────────────────────────────────────
class UpdaterService(QObject):
    """
    使用方式:
        svc = UpdaterService(current_version="1.0.0")
        svc.update_available.connect(lambda info: ...)   # 有新版本
        svc.versions_loaded.connect(lambda lst: ...)     # 版本列表已加载
        svc.check()                                      # 开始检查
    """
    update_available = pyqtSignal(dict)   # 最新版本 info dict
    versions_loaded  = pyqtSignal(list)   # 全部版本列表（已排序，最新在前）
    check_failed     = pyqtSignal(str)    # ASCII 错误描述

    def __init__(self, current_version: str = "1.0.0", parent=None):
        super().__init__(parent)
        self._current    = current_version
        self._thread     = None
        self._all_versions: list = []

    # ── 公开接口 ──────────────────────────────────────────────────────
    def check(self):
        """启动后台线程检查版本。"""
        if self._thread and self._thread.isRunning():
            return
        self._thread = _CheckThread(self)
        self._thread.finished.connect(self._on_done)
        self._thread.start()

    def all_versions(self) -> list:
        """返回已加载的版本列表（最新在前），最多5个。"""
        return self._all_versions[:5]

    # ── 内部 ──────────────────────────────────────────────────────────
    def _on_done(self, versions: list, err: str):
        if err:
            self.check_failed.emit(err)
            return

        # 按版本号从大到小排序
        try:
            versions = sorted(versions,
                              key=lambda v: _parse_version(v.get("version", "0")),
                              reverse=True)
        except Exception:
            pass

        self._all_versions = versions[:5]
        self.versions_loaded.emit(self._all_versions)

        if not versions:
            return

        latest = versions[0]
        latest_ver = latest.get("version", "0")
        if _parse_version(latest_ver) > _parse_version(self._current):
            self.update_available.emit(latest)