import os
import platform

APP_VERSION = "1.2.0"
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
FFMPEG_DIR = os.path.join(BASE_DIR, "FFmpeg")
FFMPEG_BIN_DIR = os.path.join(FFMPEG_DIR, "bin")
FFMPEG_CACHE_DIR = os.path.join(BASE_DIR, "ffmpeg_cache")
FFMPEG_DOWNLOAD_PAGE_URL = "https://ffmpeg.org/download.html"
UPDATE_CACHE_DIR = os.path.join(BASE_DIR, "updater_cache")


def _normalized_machine() -> str:
    machine = platform.machine().lower()
    if machine in {"x86_64", "amd64"}:
        return "x86_64"
    if machine in {"aarch64", "arm64"}:
        return "arm64"
    if machine in {"i386", "i686", "x86"}:
        return "x86"
    return machine or "x86_64"


def _get_executable_path(exe_name):
    system = platform.system()
    full_exe_name = f"{exe_name}.exe" if system == "Windows" else exe_name
    bundled_path = os.path.join(FFMPEG_BIN_DIR, full_exe_name)
    if os.path.exists(bundled_path) and os.path.isfile(bundled_path):
        print(f"Using bundled {exe_name}: {bundled_path}")
        return bundled_path
    return None


def get_ffmpeg_missing_message(exe_name: str = "", action_verb: str = "下载"):
    if not exe_name:
        system = platform.system()
        exe_name = "ffmpeg.exe" if system == "Windows" else "ffmpeg"
    return (
        f"未找到 FFmpeg，请到设置 {action_verb}。缺失文件: "
        f"'{os.path.join(FFMPEG_BIN_DIR, exe_name)}'"
    )


def get_ffmpeg_download_spec() -> dict:
    system = platform.system()
    machine = _normalized_machine()

    if system == "Windows":
        asset = "ffmpeg-master-latest-winarm64-gpl.zip" if machine == "arm64" else "ffmpeg-master-latest-win64-gpl.zip"
        return {
            "platform": system,
            "downloads": [{
                "url": f"https://github.com/BtbN/FFmpeg-Builds/releases/latest/download/{asset}",
                "filename": asset,
            }],
        }

    if system == "Linux":
        asset = "ffmpeg-release-arm64-static.tar.xz" if machine == "arm64" else "ffmpeg-release-amd64-static.tar.xz"
        return {
            "platform": system,
            "downloads": [{
                "url": f"https://johnvansickle.com/ffmpeg/releases/{asset}",
                "filename": asset,
            }],
        }

    if system == "Darwin":
        return {
            "platform": system,
            "downloads": [
                {
                    "url": "https://evermeet.cx/ffmpeg/getrelease/zip",
                    "filename": "ffmpeg-macos.zip",
                },
                {
                    "url": "https://evermeet.cx/ffmpeg/getrelease/ffprobe/zip",
                    "filename": "ffprobe-macos.zip",
                },
                {
                    "url": "https://evermeet.cx/ffmpeg/getrelease/ffplay/zip",
                    "filename": "ffplay-macos.zip",
                },
            ],
        }

    raise RuntimeError(f"当前系统暂不支持自动下载 FFmpeg: {system} / {machine}")


def get_ffmpeg_path(required: bool = True):
    path = _get_executable_path("ffmpeg")
    if path is None and required:
        system = platform.system()
        full_exe_name = "ffmpeg.exe" if system == "Windows" else "ffmpeg"
        raise FileNotFoundError(get_ffmpeg_missing_message(full_exe_name))
    return path


def get_ffprobe_path(required: bool = False):
    path = _get_executable_path("ffprobe")
    if path is None and required:
        system = platform.system()
        full_exe_name = "ffprobe.exe" if system == "Windows" else "ffprobe"
        raise FileNotFoundError(get_ffmpeg_missing_message(full_exe_name))
    return path


def get_ffplay_path(required: bool = False):
    path = _get_executable_path("ffplay")
    if path is None and required:
        system = platform.system()
        full_exe_name = "ffplay.exe" if system == "Windows" else "ffplay"
        raise FileNotFoundError(get_ffmpeg_missing_message(full_exe_name))
    return path


def has_ffmpeg() -> bool:
    return get_ffmpeg_path(required=False) is not None


VIDEO_FORMATS = ["mp4", "m4a", "mkv", "avi", "mov", "webm", "flv", "gif", "m3u8"]
AUDIO_FORMATS = ["mp3", "m4a", "aac", "wav", "flac", "ogg", "opus"]
IMAGE_FORMATS = ["jpg", "png", "webp", "bmp", "tiff", "ico"]
M3U8_OUTPUT_FORMATS = ["mp4", "mkv", "avi", "mov", "webm"]

DEFAULT_FFMPEG_ARGS = {
    "video": {
        "mp4": ["-c:v", "libx264", "-preset", "medium", "-crf", "23",
                "-c:a", "aac", "-b:a", "192k",
                "-movflags", "+faststart"],
        "mkv": ["-c:v", "libx264", "-preset", "medium", "-crf", "23",
                "-c:a", "aac", "-b:a", "192k"],
        "avi": ["-c:v", "mpeg4", "-q:v", "4",
                "-c:a", "libmp3lame", "-q:a", "4"],
        "mov": ["-c:v", "libx264", "-preset", "medium", "-crf", "23",
                "-c:a", "aac", "-b:a", "192k",
                "-movflags", "+faststart"],
        "webm": ["-c:v", "libvpx-vp9", "-crf", "30", "-b:v", "0",
                 "-c:a", "libopus", "-b:a", "128k"],
        "flv": ["-c:v", "libx264", "-preset", "fast", "-crf", "23",
                "-c:a", "aac", "-b:a", "128k",
                "-f", "flv"],
        "gif": ["-vf", "fps=10,scale=320:-1:flags=lanczos", "-loop", "0"],
        "m3u8": ["-c", "copy",
                 "-f", "hls",
                 "-hls_time", "6",
                 "-hls_list_size", "0",
                 "-hls_segment_filename", "%03d.ts"],
    },
    "audio": {
        "mp3": ["-map", "0:a", "-map", "0:v?", "-c:a", "libmp3lame", "-b:a", "192k", "-c:v", "copy", "-id3v2_version", "3"],
        "m4a": ["-map", "0:a", "-map", "0:v?", "-c:a", "aac", "-b:a", "192k", "-c:v", "copy"],
        "aac": ["-c:a", "aac", "-b:a", "192k", "-vn"],
        "wav": ["-c:a", "pcm_s16le", "-vn"],
        "flac": ["-map", "0:a", "-map", "0:v?", "-c:a", "flac", "-compression_level", "5", "-c:v", "copy"],
        "ogg": ["-c:a", "libvorbis", "-q:a", "4", "-vn"],
        "opus": ["-c:a", "libopus", "-b:a", "96k", "-vn"],
    },
    "image": {
        "jpg": ["-q:v", "2"],
        "png": [],
        "webp": ["-quality", "85"],
        "bmp": [],
        "tiff": [],
        "ico": ["-vf", "scale=256:256:flags=lanczos"],
    },
    "m3u8": {
        "default": ["-protocol_whitelist", "file,http,https,tcp,tls,crypto",
                    "-c", "copy"],
    },
}


if __name__ == "__main__":
    print(get_ffmpeg_path())
    print(get_ffprobe_path())
    print(get_ffplay_path())
