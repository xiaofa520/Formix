# format_factory/updater.py
"""
版本检查与更新服务。

- API: https://api.github.com/repos/xiaofa520/Formix/releases/latest
- 响应: GitHub Release JSON
- 策略: 启动时后台检查，有新版本则通过信号通知主线程弹窗提示
"""
import json
import urllib.request
import urllib.error
import os
import shutil
import zipfile
import tarfile
import platform

from PyQt6.QtCore import QObject, pyqtSignal, QThread

_API_URL = "https://api.github.com/repos/xiaofa520/Formix/releases/latest"
_TIMEOUT = 10


def _pick_release_asset(assets: list) -> str:
    system = platform.system()
    machine = platform.machine().lower()

    preferred_tokens = []
    if system == "Windows":
        preferred_tokens = ["win", "arm64"] if "arm" in machine else ["win", "64"]
    elif system == "Darwin":
        preferred_tokens = ["mac", "arm64"] if "arm" in machine else ["mac", "64"]
    elif system == "Linux":
        preferred_tokens = ["linux", "arm64"] if "arm" in machine else ["linux", "64"]

    fallback = ""
    for asset in assets:
        if not isinstance(asset, dict):
            continue
        browser_url = asset.get("browser_download_url", "")
        name = str(asset.get("name", "")).lower()
        if not browser_url:
            continue
        if not fallback and (name.endswith(".zip") or name.endswith(".tar.xz") or name.endswith(".tgz") or name.endswith(".exe")):
            fallback = browser_url
        if all(token in name for token in preferred_tokens):
            return browser_url
    return fallback


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

            versions = []
            if isinstance(data, dict) and data.get("tag_name"):
                assets = data.get("assets", []) or []
                download_url = _pick_release_asset(assets)
                if not download_url:
                    download_url = data.get("zipball_url", "") or data.get("html_url", "")
                versions = [{
                    "version": str(data.get("tag_name", "")).lstrip("vV"),
                    "release_date": str(data.get("published_at", ""))[:10],
                    "update_url": download_url,
                    "html_url": data.get("html_url", ""),
                    "release_notes": data.get("body", ""),
                    "mandatory": False,
                    "min_supported_version": "",
                }]
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


def replace_app_with_archive(archive_path: str, app_root: str):
    temp_root = os.path.join(os.path.dirname(archive_path), "_formix_update_extract")
    if os.path.exists(temp_root):
        shutil.rmtree(temp_root, ignore_errors=True)
    os.makedirs(temp_root, exist_ok=True)

    lower = archive_path.lower()
    if lower.endswith(".zip"):
        with zipfile.ZipFile(archive_path, "r") as zf:
            zf.extractall(temp_root)
    elif lower.endswith(".tar.xz") or lower.endswith(".txz") or lower.endswith(".tar.gz") or lower.endswith(".tgz"):
        with tarfile.open(archive_path, "r:*") as tf:
            tf.extractall(temp_root)
    else:
        raise RuntimeError("当前系统仅支持通过 zip / tar 包更新文件")

    extracted_entries = [os.path.join(temp_root, name) for name in os.listdir(temp_root)]
    dirs = [p for p in extracted_entries if os.path.isdir(p)]
    source_root = dirs[0] if len(dirs) == 1 else temp_root

    for name in os.listdir(source_root):
        src = os.path.join(source_root, name)
        dst = os.path.join(app_root, name)
        if os.path.isdir(src):
            if os.path.exists(dst):
                shutil.rmtree(dst, ignore_errors=True)
            shutil.copytree(src, dst)
        else:
            parent = os.path.dirname(dst)
            if parent:
                os.makedirs(parent, exist_ok=True)
            shutil.copy2(src, dst)

    shutil.rmtree(temp_root, ignore_errors=True)


class FFmpegDownloadThread(QThread):
    progress = pyqtSignal(int, int, str)  # bytes_read, total_size, stage
    finished = pyqtSignal(bool, str)      # success, message

    def __init__(self, download_spec: dict, cache_dir: str, install_dir: str, parent=None):
        super().__init__(parent)
        self.download_spec = download_spec or {}
        self.cache_dir = cache_dir
        self.install_dir = install_dir
        self._is_cancelled = False

    def cancel(self):
        self._is_cancelled = True

    def _check_cancelled(self):
        if self._is_cancelled:
            raise RuntimeError("cancelled")

    def _download_one(self, item: dict, index: int, total_items: int) -> str:
        url = item["url"]
        file_name = item.get("filename") or (url.split("/")[-1] or f"ffmpeg_{index}")
        archive_path = os.path.join(self.cache_dir, file_name)

        req = urllib.request.Request(
            url,
            headers={"User-Agent": "Mozilla/5.0 FormatFactory/1.0"})
        with urllib.request.urlopen(req, timeout=20) as response:
            total_size = int(response.info().get("Content-Length", 0))
            bytes_read = 0
            with open(archive_path, "wb") as f:
                while True:
                    self._check_cancelled()
                    chunk = response.read(1024 * 128)
                    if not chunk:
                        break
                    f.write(chunk)
                    bytes_read += len(chunk)
                    stage = f"download:{index}:{total_items}"
                    self.progress.emit(bytes_read, total_size, stage)
        return archive_path

    def _extract_archive(self, archive_path: str, extract_root: str):
        lower = archive_path.lower()
        if lower.endswith(".zip"):
            with zipfile.ZipFile(archive_path, "r") as zf:
                members = zf.infolist()
                total_members = max(len(members), 1)
                for idx, member in enumerate(members, start=1):
                    self._check_cancelled()
                    zf.extract(member, extract_root)
                    self.progress.emit(idx, total_members, "extract")
            return

        if lower.endswith(".tar.xz") or lower.endswith(".txz") or lower.endswith(".tar.gz") or lower.endswith(".tgz"):
            with tarfile.open(archive_path, "r:*") as tf:
                members = tf.getmembers()
                total_members = max(len(members), 1)
                for idx, member in enumerate(members, start=1):
                    self._check_cancelled()
                    tf.extract(member, extract_root)
                    self.progress.emit(idx, total_members, "extract")
            return

        raise RuntimeError(f"不支持的 FFmpeg 压缩格式: {os.path.basename(archive_path)}")

    @staticmethod
    def _find_binary(root_dir: str, exe_name: str) -> str:
        for root, _dirs, files in os.walk(root_dir):
            if exe_name in files:
                return os.path.join(root, exe_name)
        return ""

    @staticmethod
    def _cleanup_cache_dir(cache_dir: str):
        if cache_dir and os.path.exists(cache_dir):
            shutil.rmtree(cache_dir, ignore_errors=True)

    def run(self):
        archive_paths = []
        extract_root = ""
        try:
            os.makedirs(self.cache_dir, exist_ok=True)
            os.makedirs(self.install_dir, exist_ok=True)
            downloads = self.download_spec.get("downloads", [])
            if not downloads:
                raise RuntimeError("未找到可用的 FFmpeg 下载链接")

            total_items = len(downloads)
            for idx, item in enumerate(downloads, start=1):
                archive_paths.append(self._download_one(item, idx, total_items))

            self._check_cancelled()
            self.progress.emit(0, 100, "extract")
            extract_root = os.path.join(self.cache_dir, "_ffmpeg_extract")
            if os.path.exists(extract_root):
                shutil.rmtree(extract_root, ignore_errors=True)
            os.makedirs(extract_root, exist_ok=True)

            dest_bin = os.path.join(self.install_dir, "bin")
            if os.path.exists(dest_bin):
                shutil.rmtree(dest_bin, ignore_errors=True)
            os.makedirs(dest_bin, exist_ok=True)

            for archive_path in archive_paths:
                part_root = os.path.join(extract_root, os.path.basename(archive_path))
                os.makedirs(part_root, exist_ok=True)
                self._extract_archive(archive_path, part_root)

            ffmpeg_name = "ffmpeg.exe" if os.name == "nt" else "ffmpeg"
            ffprobe_name = "ffprobe.exe" if os.name == "nt" else "ffprobe"
            ffplay_name = "ffplay.exe" if os.name == "nt" else "ffplay"
            ffmpeg_src = self._find_binary(extract_root, ffmpeg_name)
            ffprobe_src = self._find_binary(extract_root, ffprobe_name)
            ffplay_src = self._find_binary(extract_root, ffplay_name)

            if not ffmpeg_src:
                raise RuntimeError("压缩包中未找到 FFmpeg 可执行文件")

            shutil.copy2(ffmpeg_src, os.path.join(dest_bin, ffmpeg_name))
            if ffprobe_src:
                shutil.copy2(ffprobe_src, os.path.join(dest_bin, ffprobe_name))
            if ffplay_src:
                shutil.copy2(ffplay_src, os.path.join(dest_bin, ffplay_name))

            if os.name != "nt":
                os.chmod(os.path.join(dest_bin, ffmpeg_name), 0o755)
                ffprobe_dest = os.path.join(dest_bin, ffprobe_name)
                if os.path.exists(ffprobe_dest):
                    os.chmod(ffprobe_dest, 0o755)
                ffplay_dest = os.path.join(dest_bin, ffplay_name)
                if os.path.exists(ffplay_dest):
                    os.chmod(ffplay_dest, 0o755)

            for archive_path in archive_paths:
                if archive_path and os.path.exists(archive_path):
                    os.remove(archive_path)

            self.finished.emit(True, "FFmpeg 下载并安装完成")

        except Exception as e:
            if str(e) == "cancelled":
                self.finished.emit(False, "cancelled")
            else:
                self.finished.emit(False, str(e))
        finally:
            if extract_root and os.path.exists(extract_root):
                shutil.rmtree(extract_root, ignore_errors=True)
            for archive_path in archive_paths:
                if archive_path and os.path.exists(archive_path):
                    try:
                        os.remove(archive_path)
                    except OSError:
                        pass
            self._cleanup_cache_dir(self.cache_dir)


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
