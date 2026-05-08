# Formix User Guide

For release notes, see [CHANGELOG.md](CHANGELOG.md).

## 1. Overview

Formix is a desktop multimedia tool built on FFmpeg. It currently provides:

1. Video conversion
2. Audio conversion
3. Image conversion
4. M3U8 download and remuxing
5. Audio/video splitting
6. Audio/video merging
7. Built-in command page for FFmpeg / FFplay / FFprobe
8. GPU encoding, background customization, daily wallpaper, and online updates

## 2. Before You Start

### 1. Install Python dependencies

Run this in the project root:

```bash
pip install -r requirements.txt
```

### 2. Prepare FFmpeg

The app prefers the bundled FFmpeg tools inside the project directory and does not rely on system PATH by default.

Expected files:

- `format_factory/FFmpeg/bin/ffmpeg.exe`
- `format_factory/FFmpeg/bin/ffprobe.exe`
- `format_factory/FFmpeg/bin/ffplay.exe`

Notes:

- `ffmpeg` is required for conversion.
- `ffprobe` is used for media inspection and format analysis.
- `ffplay` is used by the built-in command page for playback.
- You can also download or update FFmpeg from the Settings page. Archives are downloaded to `format_factory/ffmpeg_cache` and extracted into `format_factory/FFmpeg`.

### 3. Launch

Run from the project root:

```bash
python -m format_factory.main
```

## 3. Main Interface

The main window currently contains these pages:

1. Video
2. Audio
3. Image
4. M3U8
5. AV
6. Command
7. Settings

General behavior:

- The Command page can be disabled from Settings.
- Most conversion pages follow the same workflow: add files, choose format, choose output folder, adjust presets, then start.

Common features:

- Drag and drop files into the list
- Batch processing
- Cancel current and queued tasks
- Copy or clear logs
- No mouse-wheel switching for output format, presets, resolution, language, or background fill mode

## 4. Video Conversion

### Supported output formats

- `mp4`
- `m4a`
- `mkv`
- `avi`
- `mov`
- `webm`
- `flv`
- `gif`
- `m3u8`

### Features

- Common video format conversion
- Optional resolution scaling
- Presets and custom FFmpeg arguments
- HLS playlist output
- Automatic GPU argument injection with CPU fallback when unsupported

### Steps

1. Add video files or a folder
2. Choose an output format
3. Choose a resolution if needed
4. Select a preset or custom arguments
5. Choose an output directory
6. Click Start

## 5. Audio Conversion

### Supported output formats

- `mp3`
- `m4a`
- `aac`
- `wav`
- `flac`
- `ogg`
- `opus`

### Features

- Common audio format conversion
- Audio extraction from media with cover art
- `.ncm` decryption before conversion
- Compatibility fixes for container/codec combinations such as `m4a`, `aac`, and `wav`

### `.ncm` notes

- `.ncm` files are decrypted first, then converted to your target format.
- Temporary files are created in `ncm_cache`.
- The app attempts to clean them up automatically after completion.

## 6. Image Conversion

### Supported output formats

- `jpg`
- `png`
- `webp`
- `bmp`
- `tiff`
- `ico`

### Features

- Common image format conversion
- Quality, compression, and scaling presets
- Icon export support

## 7. M3U8 Download and Remux

### Supported input

- Online `http://` / `https://` M3U8 URLs
- Local `.m3u8` files

### Supported output formats

- `mp4`
- `mkv`
- `avi`
- `mov`
- `webm`

### Features

- Download online M3U8 media
- Remux or convert local M3U8 playlists
- Export directly to common video containers

## 8. Audio/Video Page

This page contains two sub-pages:

1. Split audio and video
2. Merge audio and video

### 1. Split

Features:

- Extract audio only
- Extract video only
- Extract both audio and video

Output naming:

- Audio: `original_name_audio.ext`
- Video: `original_name_video.ext`

### 2. Merge

Features:

- Batch merge one audio file into multiple video files

Output naming:

- `original_video_name_merged.ext`

## 9. Command Page

### Supported commands

- `ffmpeg`
- `ffplay`
- `ffprobe`

### Features

- Run commands directly inside the app
- Supports quoted paths and paths with spaces
- Command history
- `Ctrl + C` to stop the current command
- Mouse drag selection for command output and errors
- Bottom progress bar for `ffmpeg` conversion commands

### Example

```bash
ffmpeg -i "input.mp4" -c:v libx264 "output.mp4"
ffprobe "input.mp4"
ffplay "input.mp4"
```

Notes:

- Only `ffmpeg`, `ffplay`, and `ffprobe` are allowed on this page.
- If `ffplay` or `ffprobe` is missing, the page shows a direct error message.

## 10. Settings

The Settings page includes:

1. Appearance
2. GPU settings
3. About
4. Software update
5. FFmpeg download/update

### 1. Appearance

Available settings:

- Light / Dark / Auto theme
- Language switching
- Command page enable/disable
- Background image
- Background image opacity
- Blur strength
- Background fill mode
- Daily wallpaper

Background fill modes:

- No stretch
- Stretch fill
- Fit
- Cover (crop)

### 2. Language switching

Supported languages:

- Simplified Chinese
- Traditional Chinese
- English
- Japanese
- Korean
- Auto follow system

After switching language, the app shows two options:

- `Exit now`
- `Exit later`

Choosing `Exit now` closes the application immediately.

### 3. Daily wallpaper

Features:

- Fetch wallpaper from an online API
- Cache the current wallpaper locally
- Manual refresh

### 4. GPU settings

Supported options:

- NVIDIA NVENC
- AMD AMF
- Intel Quick Sync
- CPU only

Notes:

- GPU acceleration is mainly for video encoding.
- It only works when the current FFmpeg build includes the required encoder.
- Unsupported presets automatically fall back to CPU.

### 5. Software update

Features:

- Check for new versions
- View release notes
- Download and prepare updates

### 6. FFmpeg download/update

Features:

- Download or update FFmpeg
- Show download and extraction progress
- Extract automatically into `format_factory/FFmpeg`
- Delete downloaded archives after completion

Notes:

- Windows, Linux, and macOS each use platform-specific download resources.
- `ffmpeg`, `ffprobe`, and `ffplay` are handled together.

## 11. Logs

The log area is used to show:

1. Added files
2. Task status
3. FFmpeg commands
4. Encoder information
5. Real-time progress
6. Warnings and errors
7. Success or failure results

## 12. Common Issues

### 1. FFmpeg not found on startup

Check whether these files exist:

- `format_factory/FFmpeg/bin/ffmpeg.exe`
- `format_factory/FFmpeg/bin/ffprobe.exe`
- `format_factory/FFmpeg/bin/ffplay.exe`

If missing, download them from Settings.

### 2. No media info or format detection

Usually this means `ffprobe` is missing.

### 3. `ffplay` does not run on the command page

Usually `ffplay` is not installed locally. Re-download or update the FFmpeg bundle from Settings.

### 4. GPU is selected but not used

Possible reasons:

- The selected preset does not support GPU
- FFmpeg was not built with the required GPU encoder
- The chosen format or codec path is not suitable for GPU encoding

### 5. Conversion failed

Check in this order:

1. Read the last error lines in the log
2. Verify the input file is valid
3. Try a different output format
4. Disable GPU and retry
5. Clear custom arguments and retry

## 13. Dependencies

Main dependencies:

- `PyQt6`
- `mutagen`
- `pycryptodome`

## 14. Document Notes

- This document describes the current version of the app.
- For version history, see [CHANGELOG.md](CHANGELOG.md).
