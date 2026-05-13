# format_factory/gui_pages/image_converter.py
import os
from .base_page import BaseConverterPage


class ImageConverterPage(BaseConverterPage):
    _ICO_MAX_SOURCE_BYTES = 64 * 1024 * 1024
    _ICO_MAX_SOURCE_DIMENSION = 4096

    def __init__(self, ffmpeg_handler, parent=None):
        super().__init__("image", ffmpeg_handler, parent)

    def _get_file_filter(self):
        return "图片文件 (*.jpg *.jpeg *.png *.bmp *.tiff *.webp *.ico);;所有文件 (*.*)"

    def _start_conversion_process(self):
        if not self.ffmpeg_handler:
            self.log_message("未找到 FFmpeg，请到设置下载", "error")
            self.start_conversion_button.setEnabled(True)
            self.cancel_conversion_button.setEnabled(False)
            return

        fmt  = self.output_format_combo.currentText()
        args = self._build_args(fmt)
        for i, inp in enumerate(self.input_files):
            stem = os.path.splitext(os.path.basename(inp))[0]
            cur_args = list(args)
            if fmt == "ico":
                cur_args = self._ico_safe_args(inp, cur_args)
            self.log_message(
                f"[{i+1}/{len(self.input_files)}] "
                f"{os.path.basename(inp)}  →  .{fmt}", "info")
            self.conversion_requested.emit(i, inp, cur_args, stem)

    def _ico_safe_args(self, inp: str, args: list) -> list:
        try:
            size = os.path.getsize(inp)
        except OSError:
            size = 0

        info = self.file_media_info.get(inp, {})
        max_dim = 0
        for stream in info.get("streams", []):
            if stream.get("codec_type") != "video":
                continue
            width = stream.get("width") or 0
            height = stream.get("height") or 0
            if isinstance(width, int) and isinstance(height, int):
                max_dim = max(max_dim, width, height)

        target = self._extract_ico_scale_from_args(args) or self._recommended_ico_target(max_dim)
        if size <= self._ICO_MAX_SOURCE_BYTES and max_dim <= self._ICO_MAX_SOURCE_DIMENSION:
            return args

        if max_dim <= 0:
            self.log_message(f"{os.path.basename(inp)} 尺寸未知，无法为 ICO 自动压缩。", "warning")
            return args

        if not target:
            target = 256

        self.log_message(
            f"{os.path.basename(inp)} 过大，已自动按 {target}x{target} 无损尺寸缩放后再生成 ICO。",
            "warning",
        )
        new_args = []
        replaced = False
        i = 0
        while i < len(args):
            tok = args[i]
            if tok == "-vf" and i + 1 < len(args):
                if not replaced:
                    new_args.extend(["-vf", f"scale={target}:{target}:flags=lanczos"])
                    replaced = True
                i += 2
                continue
            new_args.append(tok)
            i += 1
        if not replaced:
            new_args.extend(["-vf", f"scale={target}:{target}:flags=lanczos"])
        return new_args

    @staticmethod
    def _recommended_ico_target(max_dim: int) -> int:
        if max_dim >= 256:
            return 256
        if max_dim >= 128:
            return 128
        if max_dim >= 64:
            return 64
        if max_dim >= 32:
            return 32
        return 16
