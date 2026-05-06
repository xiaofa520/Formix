# format_factory/gui_pages/image_converter.py
import os
from .base_page import BaseConverterPage


class ImageConverterPage(BaseConverterPage):
    def __init__(self, ffmpeg_handler, parent=None):
        super().__init__("image", ffmpeg_handler, parent)

    def _get_file_filter(self):
        return "图片文件 (*.jpg *.jpeg *.png *.bmp *.tiff *.webp *.ico);;所有文件 (*.*)"

    def _start_conversion_process(self):
        fmt  = self.output_format_combo.currentText()
        args = self._build_args(fmt)
        for i, inp in enumerate(self.input_files):
            stem = os.path.splitext(os.path.basename(inp))[0]
            self.log_message(
                f"[{i+1}/{len(self.input_files)}] "
                f"{os.path.basename(inp)}  →  .{fmt}", "info")
            self.conversion_requested.emit(i, inp, args, stem)