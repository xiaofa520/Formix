"""Job planning. Each command writes exclusively inside its job's staging directory."""
if __package__:
    from .runtime_paths import executable
else:
    from runtime_paths import executable
import os
import json
import sys
from pathlib import Path

WORKER = str(Path(__file__).with_name("worker.py"))
MODEL_PROFILES = json.loads((Path(__file__).with_name("assets") / "model-profiles.json").read_text(encoding="utf-8"))
MODEL_REPOS = {key: profile["repo"] for key, profile in MODEL_PROFILES.items()}
LEVELS = ("balanced", "quality", "small")
HARDWARE_H264_CONTAINERS = {"mp4", "mkv", "mov", "avi", "ts", "flv", "3gp"}
HARDWARE_VIDEO_CONTAINERS = HARDWARE_H264_CONTAINERS | {"webm"}
PAGES = {
    "图片提取文字": ["copy", "txt", "md"],
    # Targets are ordered by everyday use, occasional use, then specialist/legacy use.
    "音频转换": ["mp3", "wav", "m4a", "flac", "aac", "ogg", "opus", "aiff", "wma", "ac3", "mp2", "wv", "tta"],
    "视频转换": ["mp4", "mkv", "mov", "avi", "webm", "flv", "ts", "mpeg", "wmv", "3gp", "ogv", "vob", "m3u8"],
    "M3U8 合成": ["mp4", "mkv", "mov", "avi", "webm", "flv", "ts", "mpeg", "wmv", "3gp", "ogv", "vob"],
    "音频压缩": LEVELS,
    "视频压缩": LEVELS,
    "图片压缩": LEVELS,
    "音视频合并": ["mp4", "mkv"],
    "音视频分离": ["audio", "video", "both"],
    "图片转换": ["jpg", "png", "webp", "gif", "bmp", "tiff", "heic", "avif", "ico", "pdf", "svg"],
    "文档转换": ["pdf", "docx", "xlsx", "pptx", "txt", "csv", "html"],
    "PDF 转换": ["docx", "xlsx", "pptx", "JPG · zip", "txt", "md", "html", "csv", "页面图片 · zip"],
}
AUDIO = frozenset(".mp3 .aac .m4a .wav .flac .ogg .oga .opus .aif .aiff .wma .ac3 .amr .mp2 .wv .tta .ape .caf .mka .au .snd .dts".split())
VIDEO = frozenset(".mp4 .mkv .mov .avi .webm .m4v .flv .wmv .mpeg .mpg .ts .mts .m2ts .3gp .ogv .vob .mxf .m2v .f4v".split())
M3U8 = frozenset({".m3u8"})
IMAGE = frozenset(".jpg .jpeg .png .webp .tif .tiff .bmp .gif .avif .heif .heic .svg".split())
IMAGE_CONVERSION = IMAGE | {".ai"}
DOCUMENT = frozenset(".doc .docx .odt .fodt .sxw .rtf .txt .html .htm .xls .xlsx .ods .fods .sxc .csv .ppt .pptx .odp .fodp .sxi".split())
DOCUMENT_FORMATS = {
    "writer": ("pdf", "docx", "txt", "html"),
    "spreadsheet": ("pdf", "xlsx", "csv"),
    "presentation": ("pdf", "pptx"),
}
DOCUMENT_FAMILY = {
    **{suffix: "writer" for suffix in (".doc", ".docx", ".odt", ".fodt", ".sxw", ".rtf", ".txt", ".html", ".htm")},
    **{suffix: "spreadsheet" for suffix in (".xls", ".xlsx", ".ods", ".fods", ".sxc", ".csv")},
    **{suffix: "presentation" for suffix in (".ppt", ".pptx", ".odp", ".fodp", ".sxi")},
}


def media_threads():
    cores = (getattr(os, "process_cpu_count", os.cpu_count)() or 2)
    import psutil
    free_gib = psutil.virtual_memory().available // (1024 ** 3)
    return max(1, min(cores // 2, free_gib or 1, 8))


def document_targets_for_sources(sources):
    """Return formats supported by every selected document, excluding no-op outputs."""
    suffixes = [Path(source).suffix.lower() for source in sources]
    if not suffixes:
        return list(PAGES["文档转换"])
    compatible = None
    for suffix in suffixes:
        family = DOCUMENT_FAMILY.get(suffix)
        targets = set(DOCUMENT_FORMATS.get(family, ())) - {suffix.lstrip(".")}
        compatible = targets if compatible is None else compatible & targets
    return [target for target in PAGES["文档转换"] if target in (compatible or set())]


def lossless_video_args(container, encoder=None):
    """Never silently use a lossy preset for a format-only conversion."""
    if container == "webm":
        return ["-c:v", "libvpx-vp9", "-lossless", "1", "-pix_fmt", "+"]
    if container not in {"mp4", "mkv", "mov", "avi", "ts", "m3u8"}:
        raise ValueError("目标格式无法直接封装当前编码，且未提供可靠的无损转码方式；请改用 MKV 或 MP4。原文件未修改。")
    if encoder == "h264_nvenc":
        return ["-c:v", encoder, "-preset", "p1", "-tune", "lossless", "-rc", "constqp", "-qp", "0", "-pix_fmt", "+"]
    return ["-c:v", "libx264", "-preset", "veryfast", "-crf", "0", "-pix_fmt", "+"]


def hardware_video_args(encoder, quality=26):
    if encoder == "h264_nvenc":
        return ["-c:v", encoder, "-preset", "p4", "-cq", str(quality), "-b:v", "0"]
    if encoder == "h264_qsv":
        return ["-c:v", encoder, "-global_quality", str(quality)]
    if encoder == "h264_amf":
        return ["-c:v", encoder, "-quality", "balanced", "-qp_i", str(quality), "-qp_p", str(quality)]
    if encoder == "h264_videotoolbox":
        return ["-c:v", encoder, "-q:v", str(max(1, min(100, 100 - quality * 2)))]
    if encoder == "h264_vaapi":
        return ["-vf", "format=nv12,hwupload", "-c:v", encoder, "-qp", str(quality)]
    if encoder == "vp9_qsv":
        return ["-c:v", encoder, "-global_quality", str(quality)]
    if encoder == "vp9_vaapi":
        return ["-vf", "format=nv12,hwupload", "-c:v", encoder, "-global_quality", str(quality)]
    return ["-c:v", "libx264", "-crf", str(quality)]


LOSSLESS_AUDIO = {".wav", ".aiff", ".aif", ".flac", ".ape", ".wv", ".tta", ".caf", ".au", ".snd"}


def compression_profile(page, suffix):
    suffix = suffix.lower()
    if page == "音频压缩":
        if suffix in LOSSLESS_AUDIO:
            return "audio_lossless"
        if suffix in {".ogg", ".oga"}:
            return "audio_vorbis"
        if suffix == ".opus":
            return "audio_opus"
        if suffix == ".amr":
            return "audio_speech"
        if suffix in {".dts", ".mka"}:
            return "audio_surround"
        if suffix == ".ac3":
            return "audio_ac3"
        if suffix == ".mp2":
            return "audio_mp2"
        return "audio_bitrate"
    if page == "视频压缩":
        return {".webm": "video_vp9", ".ogv": "video_theora"}.get(suffix, "video_h264")
    if page == "图片压缩":
        if suffix == ".png":
            return "image_png"
        if suffix in {".jpg", ".jpeg"}:
            return "image_jpeg"
        return "image_webp"
    return "generic"


def compression_options_for_sources(page, sources):
    modes = ("balanced", "quality", "small")
    profiles = {compression_profile(page, Path(source).suffix) for source in sources}
    if len(profiles) != 1 or "generic" in profiles:
        return [(mode, "") for mode in modes]
    profile = next(iter(profiles))
    details_by_profile = {
        "audio_lossless": {"quality": "FLAC L3", "balanced": "FLAC L6", "small": "FLAC L8"},
        "audio_vorbis": {"quality": "Vorbis Q6", "balanced": "Vorbis Q4", "small": "Vorbis Q2"},
        "audio_opus": {"quality": "96 kb/s", "balanced": "64 kb/s", "small": "48 kb/s"},
        "audio_speech": {"quality": "24 kb/s", "balanced": "16 kb/s", "small": "12 kb/s"},
        "audio_surround": {"quality": "160 kb/s", "balanced": "112 kb/s", "small": "80 kb/s"},
        "audio_ac3": {"quality": "448 kb/s", "balanced": "256 kb/s", "small": "128 kb/s"},
        "audio_mp2": {"quality": "256 kb/s", "balanced": "192 kb/s", "small": "128 kb/s"},
        "audio_bitrate": {"quality": "192 kb/s", "balanced": "128 kb/s", "small": "96 kb/s"},
        "video_vp9": {"quality": "VP9 CRF 28", "balanced": "VP9 CRF 35", "small": "VP9 CRF 42"},
        "video_theora": {"quality": "Theora Q7", "balanced": "Theora Q5", "small": "Theora Q3"},
        "video_h264": {"quality": "H.264 CRF 23", "balanced": "H.264 CRF 28", "small": "H.264 CRF 34"},
        "image_png": {"quality": "PNG L3", "balanced": "PNG L6", "small": "PNG L9"},
        "image_jpeg": {"quality": "JPEG Q90", "balanced": "JPEG Q75", "small": "JPEG Q55"},
        "image_webp": {"quality": "WebP Q90", "balanced": "WebP Q75", "small": "WebP Q55"},
    }
    details = details_by_profile.get(profile)
    return [(mode, details[mode] if details else "") for mode in modes]


def audio_compression_target(suffix):
    suffix = suffix.lower()
    if suffix in LOSSLESS_AUDIO:
        return "flac"
    if suffix in {".amr", ".dts", ".mka"}:
        return "opus"
    return suffix.lstrip(".") or "m4a"


def image_compression_target(suffix):
    suffix = suffix.lower()
    return "jpg" if suffix in {".jpg", ".jpeg"} else "png" if suffix == ".png" else "webp"


def hardware_codec_for(page, src, option):
    if page == "音视频合并":
        return "h264"
    if page == "视频压缩":
        suffix = Path(src).suffix.lower()
        return "vp9" if suffix == ".webm" else "h264" if suffix != ".ogv" else None
    if page in {"视频转换", "M3U8 合成"}:
        if page == "视频转换" and option == "m3u8":
            return "h264"
        if option == "webm":
            return "vp9"
        if option in HARDWARE_H264_CONTAINERS:
            return "h264"
    return None


INPUT_TYPES = {
    "图片提取文字": frozenset(".png .jpg .jpeg .bmp .webp .tif .tiff".split()),
    "音频转换": AUDIO | {".ncm"}, "音频压缩": AUDIO,
    "视频转换": VIDEO, "视频压缩": VIDEO, "音视频合并": VIDEO, "音视频分离": VIDEO,
    "M3U8 合成": M3U8,
    "图片转换": IMAGE_CONVERSION, "图片压缩": IMAGE,
    "文档转换": DOCUMENT,
    "PDF 转换": frozenset({".pdf"}),
}

def plan(page, src, option, audio, stage, models, hardware_encoder=None, hardware_device=None,
         reduced_metadata=False, compression_params=None, hardware_decode=False):
    compression_params = compression_params or {}
    if page == "图片提取文字" or (page == "PDF 转换" and "recognition_model" in compression_params):
        selected = compression_params.get("recognition_model", "pp-ocrv5-mobile" if page == "图片提取文字" else models.name)
        if selected not in MODEL_PROFILES:
            raise ValueError("不支持的识别模型")
        models = models.parent / selected
    if page == "图片提取文字":
        out = stage / ("result.md" if option == "md" else "result.txt")
        return [sys.executable, "-X", "utf8", WORKER, "image-ocr", str(src), str(out), str(models), option], out
    ext = option
    compression_params = compression_params or {}
    preserve_metadata = (True if page in {"音频压缩", "视频压缩", "图片压缩"}
                         else compression_params.get("preserve_metadata", True))
    try:
        custom_bitrate = max(0, min(512, int(compression_params.get("bitrate", 0))))
    except (TypeError, ValueError):
        custom_bitrate = 0
    if custom_bitrate:
        custom_bitrate = max(32, custom_bitrate)

    def bitrate_or(default, maximum=None):
        if not custom_bitrate:
            return default
        rate = min(custom_bitrate, maximum) if maximum else custom_bitrate
        return f"{rate}k"

    def supported_bitrate_or(default, supported):
        requested = custom_bitrate or int(default.removesuffix("k"))
        return f"{min(supported, key=lambda rate: abs(rate - requested))}k"
    source = str(src)
    copy_video = page == "视频转换" and not compression_params.get("video_transcode", False)
    playlist_input = page == "M3U8 合成"
    metadata_args = (["-map_metadata", "-1", "-map_metadata:s", "-1", "-map_chapters", "-1"]
                     if reduced_metadata or not preserve_metadata else ["-map_metadata", "0:g", "-map_chapters", "0"])
    if hardware_encoder and hardware_encoder.endswith("_vaapi") and hardware_device:
        args = ["-vaapi_device", hardware_device]
    else:
        args = []
    cuda_frames = hardware_decode and hardware_encoder == "h264_nvenc" and not copy_video
    if cuda_frames:
        args += ["-hwaccel", "cuda", "-hwaccel_output_format", "cuda"]
    if playlist_input:
        # The worker rewrites every URI into its private, verified cache first.
        args += ["-protocol_whitelist", "file,crypto", "-allowed_extensions", "ALL", "-f", "hls"]
        args += ["-i", source]
    else:
        args += ["-i", source]
    if page == "音频压缩":
        suffix = Path(src).suffix.lower()
        ext = audio_compression_target(suffix)
        args += ["-map", "0:a:0", "-vn"]
        if compression_params.get("detail") == "mono":
            args += ["-ac", "1"]
        if ext == "flac":
            args += ["-c:a", "flac", "-compression_level", {"quality": "3", "balanced": "6", "small": "8"}[option]]
        elif ext in {"m4a", "aac"}:
            args += ["-c:a", "aac", "-b:a", bitrate_or({"quality": "192k", "balanced": "128k", "small": "96k"}[option])]
        elif ext == "mp3":
            args += ["-c:a", "libmp3lame", "-b:a", bitrate_or({"quality": "192k", "balanced": "128k", "small": "96k"}[option], 320)]
        elif ext in {"ogg", "oga"}:
            if custom_bitrate:
                args += ["-c:a", "libvorbis", "-b:a", bitrate_or("", 500)]
            else:
                args += ["-c:a", "libvorbis", "-q:a", {"quality": "6", "balanced": "4", "small": "2"}[option]]
        elif ext == "opus":
            bitrates = {".amr": {"quality": "24k", "balanced": "16k", "small": "12k"},
                        ".dts": {"quality": "160k", "balanced": "112k", "small": "80k"},
                        ".mka": {"quality": "160k", "balanced": "112k", "small": "80k"}}
            args += ["-c:a", "libopus", "-application", "voip" if suffix == ".amr" else "audio", "-b:a",
                     bitrate_or(bitrates.get(suffix, {"quality": "96k", "balanced": "64k", "small": "48k"})[option], 510)]
        elif ext == "wma":
            args += ["-c:a", "wmav2", "-b:a", bitrate_or({"quality": "192k", "balanced": "128k", "small": "96k"}[option], 192)]
        elif ext == "ac3":
            args += ["-c:a", "ac3", "-b:a", supported_bitrate_or(
                {"quality": "448k", "balanced": "256k", "small": "128k"}[option],
                (32, 40, 48, 56, 64, 80, 96, 112, 128, 160, 192, 224, 256, 320, 384, 448, 512, 576, 640))]
        elif ext == "mp2":
            args += ["-c:a", "mp2", "-b:a", supported_bitrate_or(
                {"quality": "256k", "balanced": "192k", "small": "128k"}[option],
                (32, 48, 56, 64, 80, 96, 112, 128, 160, 192, 224, 256, 320, 384))]
        else:
            args += ["-c:a", "aac", "-b:a", bitrate_or({"quality": "192k", "balanced": "128k", "small": "96k"}[option], 512)]
    elif page == "视频压缩":
        suffix = Path(src).suffix.lower()
        args += ["-map", "0:V:0", "-map", "0:a?"]
        resolution = compression_params.get("height", compression_params.get("detail", "original"))
        try:
            height = int(resolution) if resolution != "original" else 0
        except (TypeError, ValueError):
            height = 0
        width_value = compression_params.get("width", "original")
        try:
            width = int(width_value) if width_value != "original" else 0
        except (TypeError, ValueError):
            width = 0
        if width > 0 or height > 0:
            width = max(144, min(7680, width)) if width > 0 else 0
            height = max(144, min(4320, height)) if height > 0 else 0
            width_expr = f"min(iw\\,{width})" if width else "iw"
            height_expr = f"min(ih\\,{height})" if height else "ih"
            scaler = "scale_cuda" if cuda_frames else "scale"
            args += ["-vf", f"{scaler}=w='{width_expr}':h='{height_expr}':force_original_aspect_ratio=decrease:force_divisible_by=2"]
        if suffix == ".webm":
            ext = "webm"
            crf = {"quality": "28", "balanced": "35", "small": "42"}[option]
            args += hardware_video_args(hardware_encoder, int(crf)) if hardware_encoder else ["-c:v", "libvpx-vp9", "-crf", crf, "-b:v", "0"]
            args += ["-c:a", "libopus", "-b:a", {"quality": "160k", "balanced": "112k", "small": "80k"}[option]]
        elif suffix == ".ogv":
            ext = "ogv"
            args += ["-c:v", "libtheora", "-q:v", {"quality": "7", "balanced": "5", "small": "3"}[option],
                     "-c:a", "libvorbis", "-q:a", {"quality": "5", "balanced": "3", "small": "1"}[option]]
        else:
            ext = "mp4"
            crf = {"quality": "23", "balanced": "28", "small": "34"}[option]
            args += hardware_video_args(hardware_encoder, int(crf)) if hardware_encoder else ["-c:v", "libx264", "-crf", crf]
            args += ["-c:a", "aac"]
    elif page == "图片压缩":
        ext = image_compression_target(Path(src).suffix)
        out = stage / ("result." + ext)
        return [sys.executable, "-X", "utf8", WORKER, "compress-image", str(src), str(out), option,
                compression_params.get("detail", "original"), "1" if preserve_metadata else "0"], out
    elif page == "音视频合并":
        args += ["-i", str(audio), "-map", "0:v:0", "-map", "1:a:0"]
        args += hardware_video_args(hardware_encoder) if hardware_encoder else ["-c:v", "libx264"]
        args += ["-c:a", "aac", "-shortest"]
    elif page == "音视频分离":
        mode = option if option in {"audio", "video", "both"} else "audio"
        selected = compression_params.get("split_format", {"audio": "m4a", "video": "mp4", "both": "m4a+mp4"}[mode])
        ext = selected.split("+")[0]
        codecs = {"m4a": "aac", "mp3": "libmp3lame", "wav": "pcm_s16le",
                  "flac": "flac", "aac": "aac", "ogg": "libvorbis", "opus": "libopus"}
        video_codecs = {"mp4": "libx264", "mkv": "libx264", "mov": "libx264", "avi": "mpeg4", "webm": "libvpx-vp9"}
        if mode == "video":
            if ext not in video_codecs:
                raise ValueError("不支持的视频提取格式")
            args += ["-map", "0:V:0", "-an", "-sn", "-dn", "-c:v", video_codecs[ext]]
        elif ext not in codecs:
            raise ValueError("不支持的音频提取格式")
        else:
            if mode == "both":
                video_ext = selected.split("+")[-1]
                if video_ext not in video_codecs:
                    raise ValueError("不支持的视频提取格式")
                args += ["-map", "0:V:0", "-an", "-sn", "-dn", "-c:v", video_codecs[video_ext],
                         *metadata_args, "-threads", str(media_threads()), str(stage / ("video." + video_ext))]
            args += ["-map", "0:a:0", "-vn", "-sn", "-dn", "-c:a", codecs[ext]]
    elif page == "音频转换":
        args += ["-map", "0:a:0", "-vn"]
    elif page == "视频转换" and ext == "m3u8":
        stem = Path(source).stem
        out_dir = stage / stem
        out_dir.mkdir()
        playlist = stage / (stem + ".m3u8")
        segments = out_dir / (stem + "_%05d.ts")
        args += ["-map", "0:V:0", "-map", "0:a?"]
        args += ["-c:v", "copy"] if copy_video else lossless_video_args(ext, hardware_encoder)
        threads = str(media_threads())
        args += metadata_args + ["-threads", threads, "-c:a", "copy",
                 "-f", "hls", "-hls_time", "6", "-hls_playlist_type", "vod",
                 "-hls_segment_filename", str(segments), str(playlist)]
        exe = executable("ffmpeg")
        if not exe:
            raise ValueError("请安装 FFmpeg 并将其加入 PATH")
        return [exe, "-hide_banner", "-loglevel", "level+info", "-nostdin", "-progress",
                "pipe:2", "-nostats", "-filter_threads", threads, "-threads", threads, *args], playlist
    elif page in ("视频转换", "M3U8 合成"):
        args += ["-map", "0:V:0", "-map", "0:a?"]
        video_profiles = {
            "avi": ["-c:v", "mpeg4", "-c:a", "libmp3lame"],
            "flv": ["-c:v", "flv1", "-c:a", "libmp3lame"],
            "webm": ["-c:v", "libvpx-vp9", "-crf", "33", "-b:v", "0", "-c:a", "libopus"],
            "ogv": ["-c:v", "libtheora", "-c:a", "libvorbis"],
            "wmv": ["-c:v", "wmv2", "-c:a", "wmav2"],
            "mpeg": ["-c:v", "mpeg2video", "-c:a", "mp2"],
            "vob": ["-c:v", "mpeg2video", "-c:a", "mp2"],
            "3gp": ["-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac"],
        }
        if page == "视频转换":
            args += ["-c", "copy"] if copy_video else lossless_video_args(ext, hardware_encoder) + ["-c:a", "copy"]
        elif hardware_encoder and ext in HARDWARE_VIDEO_CONTAINERS:
            args += hardware_video_args(hardware_encoder)
            args += ["-c:a", "libopus" if ext == "webm" else "aac"]
        else:
            args += video_profiles.get(ext, ["-c:v", "libx264", "-c:a", "aac"])
    elif page == "文档转换":
        exe = executable("soffice")
        if not exe:
            if sys.platform != "win32":
                raise ValueError("请安装 LibreOffice，或将 soffice 加入 PATH")
            program = [sys.executable, "-X", "utf8", WORKER, "office"]
        else:
            program = [exe]
        out = stage/(src.stem+"."+ext)
        command = [*program,"-env:UserInstallation="+(stage/"profile").as_uri(),"--headless","--convert-to",ext,"--outdir",str(stage),str(src)]
        return [sys.executable,"-X","utf8",WORKER,"office-convert",str(out),*command], out
    elif page == "图片转换" and Path(src).suffix.lower() == ".ai":
        ext = option.split()[-1].lower()
        out = stage/("result."+ext)
        if ext == "pdf":
            return [sys.executable, "-X", "utf8", WORKER, "ai-pdf", str(src), str(out)], out
        if ext == "svg":
            return [sys.executable, "-X", "utf8", WORKER, "ai-svg", str(src), str(out)], out
        sizes = compression_params.get("icon_sizes", [32, 64, 128])
        return [sys.executable, "-X", "utf8", WORKER, "ai-image", str(src), str(out), json.dumps(sizes)], out
    elif page in ("图片转换", "PDF 转换"):
        ext = option.split()[-1].lower()
        out = stage/("result."+ext)
        if page == "图片转换" and ext == "ico":
            sizes = compression_params.get("icon_sizes", [32, 64, 128])
            return [sys.executable, "-X", "utf8", WORKER, "image", str(src), str(out), str(models), json.dumps(sizes)], out
        if page == "PDF 转换" and option == "JPG · zip":
            return [sys.executable, "-X", "utf8", WORKER, "pdf", str(src), str(out), str(models), "JPEG"], out
        return [sys.executable, "-X", "utf8", WORKER, "image" if page=="图片转换" else "pdf",str(src),str(out),str(models)], out
    else:
        raise ValueError(page)
    exe = executable("ffmpeg")
    if not exe:
        raise ValueError("请安装 FFmpeg 并将其加入 PATH")
    args += metadata_args
    if not reduced_metadata and preserve_metadata:
        if page in {"音频转换", "音频压缩"} or (page == "音视频分离" and option != "video"):
            # Vorbis and Opus often store artist and album on the audio stream.
            args += ["-map_metadata:s:a:0", "0:s:a:0"]
        elif page == "视频压缩":
            # Preserve camera/encoder tags carried on the selected video stream.
            args += ["-map_metadata:s:v:0", "0:s:v:0"]
        if ext in {"mp4", "mov"}:
            args += ["-movflags", "+use_metadata_tags"]
        if page == "音视频合并":
            args += ["-map_metadata:s:v:0", "0:s:v:0", "-map_metadata:s:a:0", "1:s:a:0",
                     "-map_metadata:s:a:0", "1:g"]
    out = stage/("result."+ext)
    threads = str(media_threads())
    command = [exe,"-hide_banner","-loglevel","level+info","-nostdin","-progress","pipe:2","-nostats","-filter_threads",threads,"-threads",threads,*args,"-threads",threads,str(out)]
    if Path(src).suffix.lower() == ".ncm":
        if __package__:
            from .runtime_paths import ncm_cache_dir
        else:
            from runtime_paths import ncm_cache_dir
        return [sys.executable, "-X", "utf8", WORKER, "ncm", str(src), str(ncm_cache_dir()), *command], out
    if playlist_input:
        command = [sys.executable,"-X","utf8",WORKER,"hls",str(stage/"hls-input"),*command]
    return command,out

