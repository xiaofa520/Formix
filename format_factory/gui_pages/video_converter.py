# format_factory/gui_pages/video_converter.py
import os
from .base_page import BaseConverterPage


class VideoConverterPage(BaseConverterPage):
    def __init__(self, ffmpeg_handler, parent=None):
        super().__init__('video', ffmpeg_handler, parent)

    def _get_file_filter(self):
        return "视频文件 (*.mp4 *.mkv *.avi *.mov *.wmv *.flv *.webm);;所有文件 (*.*)"

    def _start_conversion_process(self):
        output_format = self.output_format_combo.currentText()
        args = self._build_args(output_format)
        for i, input_path in enumerate(self.input_files):
            name = os.path.splitext(os.path.basename(input_path))[0]
            self.log_message(f"[{i+1}] {os.path.basename(input_path)}  →  .{output_format}", "info")
            if output_format == "m3u8":
                # HLS：把 %03d.ts 标记传出去，_submit_next 里处理实际路径
                hls_args = list(args)
                self.conversion_requested.emit(i, input_path, hls_args, name)
            else:
                self.conversion_requested.emit(i, input_path, args, name)
