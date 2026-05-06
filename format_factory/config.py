import platform
import os
import shutil

APP_VERSION = "1.1.0"

def _get_executable_path(exe_name):
    base_dir = os.path.dirname(os.path.abspath(__file__))
    bin_dir  = os.path.join(base_dir, "FFmpeg", "bin")
    system   = platform.system()

    full_exe_name = f"{exe_name}.exe" if system == "Windows" else exe_name

    bundled_path = os.path.join(bin_dir, full_exe_name)
    if os.path.exists(bundled_path) and os.path.isfile(bundled_path):
        print(f"Using bundled {exe_name}: {bundled_path}")
        return bundled_path
    return None

def get_ffmpeg_path():
    path = _get_executable_path("ffmpeg")
    if path is None:
        base_dir = os.path.dirname(os.path.abspath(__file__))
        bin_dir  = os.path.join(base_dir, "FFmpeg", "bin")
        system   = platform.system()
        full_exe_name = "ffmpeg.exe" if system == "Windows" else "ffmpeg"
        raise FileNotFoundError(
            f"ffmpeg 未找到，请确认 '{os.path.join(bin_dir, full_exe_name)}' 存在。")
    return path

def get_ffprobe_path():
    return _get_executable_path("ffprobe")  # 可选，缺失时返回 None

VIDEO_FORMATS      = ["mp4", "m4a", "mkv", "avi", "mov", "webm", "flv", "gif", "m3u8"]
AUDIO_FORMATS      = ["mp3", "m4a", "aac", "wav", "flac", "ogg", "opus"]
IMAGE_FORMATS      = ["jpg", "png", "webp", "bmp", "tiff", "ico"]
M3U8_OUTPUT_FORMATS = ["mp4", "mkv", "avi", "mov", "webm"]

DEFAULT_FFMPEG_ARGS = {
    "video": {
        # H.264 + AAC — universal compatibility
        "mp4":  ["-c:v", "libx264", "-preset", "medium", "-crf", "23",
                 "-c:a", "aac", "-b:a", "192k",
                 "-movflags", "+faststart"],
        "mkv":  ["-c:v", "libx264", "-preset", "medium", "-crf", "23",
                 "-c:a", "aac", "-b:a", "192k"],
        # AVI: use mpeg4 (widely supported) instead of libxvid which
        # requires a separate encoder build; fallback to libxvid if mpeg4 unavailable
        "avi":  ["-c:v", "mpeg4", "-q:v", "4",
                 "-c:a", "libmp3lame", "-q:a", "4"],
        # MOV: H.264 / AAC — drop -tag:v mp4v which clashes with libx264
        "mov":  ["-c:v", "libx264", "-preset", "medium", "-crf", "23",
                 "-c:a", "aac", "-b:a", "192k",
                 "-movflags", "+faststart"],
        "webm": ["-c:v", "libvpx-vp9", "-crf", "30", "-b:v", "0",
                 "-c:a", "libopus", "-b:a", "128k"],
        "flv":  ["-c:v", "libx264", "-preset", "fast", "-crf", "23",
                 "-c:a", "aac", "-b:a", "128k",
                 "-f", "flv"],
        "gif":  ["-vf", "fps=10,scale=320:-1:flags=lanczos", "-loop", "0"],
        "m3u8": ["-c", "copy",
                 "-f", "hls",
                 "-hls_time", "6",
                 "-hls_list_size", "0",
                 "-hls_segment_filename", "%03d.ts"],
    },
    "audio": {
        "mp3":  ["-map", "0:a", "-map", "0:v?", "-c:a", "libmp3lame", "-b:a", "192k", "-c:v", "copy", "-id3v2_version", "3"],
        "m4a":  ["-map", "0:a", "-map", "0:v?", "-c:a", "aac", "-b:a", "192k", "-c:v", "copy"],
        "aac":  ["-c:a", "aac", "-b:a", "192k", "-vn"],
        "wav":  ["-c:a", "pcm_s16le", "-vn"],
        "flac": ["-map", "0:a", "-map", "0:v?", "-c:a", "flac", "-compression_level", "5", "-c:v", "copy"],
        "ogg":  ["-c:a", "libvorbis", "-q:a", "4", "-vn"],
        "opus": ["-c:a", "libopus", "-b:a", "96k", "-vn"],
    },
    "image": {
        "jpg":  ["-q:v", "2"],
        "png":  [],
        "webp": ["-quality", "85"],
        "bmp":  [],
        "tiff": [],
        "ico":  ["-vf", "scale=256:256:flags=lanczos"],
    },
    "m3u8": {
        "default": ["-protocol_whitelist", "file,http,https,tcp,tls,crypto",
                    "-c", "copy"],
    },
}

# 更新缓存目录配置 (放置在本项目下的 updater_cache 文件夹中)
UPDATE_CACHE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "updater_cache")

if __name__ == "__main__":
    print(get_ffmpeg_path())
    print(get_ffprobe_path())