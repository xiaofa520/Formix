# format_factory/gui_pages/audio_converter.py
import os
import shutil
from .base_page import BaseConverterPage
from .decrypt_ncm import decrypt_ncm


class AudioConverterPage(BaseConverterPage):
    def __init__(self, ffmpeg_handler, parent=None):
        super().__init__("audio", ffmpeg_handler, parent)
        self.cache_dir = os.path.join(os.getcwd(), "ncm_cache")
        self.ncm_cache_files = []
        self.ncm_processing = False

        if self.ffmpeg_handler:
            self.ffmpeg_handler.conversion_finished.connect(self._on_conversion_finished)

    def _get_file_filter(self):
        return "音频文件 (*.mp3 *.wav *.aac *.flac *.ogg *.m4a *.opus *.ncm);;所有文件 (*.*)"

    def _start_conversion_process(self):
        if not self.ffmpeg_handler:
            self.log_message("未找到 FFmpeg，请到设置下载", "error")
            self.start_conversion_button.setEnabled(True)
            self.cancel_conversion_button.setEnabled(False)
            return

        fmt  = self.output_format_combo.currentText()
        args = self._build_args(fmt)

        self.ncm_cache_files = []
        self.ncm_processing = False

        for i, inp in enumerate(self.input_files):
            stem = os.path.splitext(os.path.basename(inp))[0]
            ext = os.path.splitext(inp)[1].lower()

            if ext == '.ncm':
                self.ncm_processing = True
                if not os.path.exists(self.cache_dir):
                    os.makedirs(self.cache_dir)

                self.log_message(f"[{i+1}/{len(self.input_files)}] 解密 {os.path.basename(inp)}...", "info")
                try:
                    decrypted_path = decrypt_ncm(inp, self.cache_dir)
                    if decrypted_path and os.path.exists(decrypted_path):
                        self.ncm_cache_files.append(decrypted_path)

                        decrypted_ext = os.path.splitext(decrypted_path)[1].lower().lstrip('.')
                        if decrypted_ext == fmt.lower():
                            # If format matches, just move to output dir
                            out_path = os.path.join(self.output_dir, os.path.basename(decrypted_path))
                            shutil.copy2(decrypted_path, out_path)
                            self.log_message(
                                f"[{i+1}/{len(self.input_files)}] "
                                f"{os.path.basename(inp)} 解密完成并移动到输出目录", "success")
                            self.ffmpeg_handler.conversion_finished.emit(i, "success", f"'{os.path.basename(out_path)}' ✓")
                        else:
                            # Need conversion
                            self.log_message(
                                f"[{i+1}/{len(self.input_files)}] "
                                f"{os.path.basename(decrypted_path)}  →  .{fmt}", "info")
                            self.conversion_requested.emit(i, decrypted_path, args, stem)
                    else:
                        self.log_message(f"[{i+1}/{len(self.input_files)}] 解密失败: {os.path.basename(inp)}", "error")
                        self.ffmpeg_handler.conversion_finished.emit(i, "failure", "NCM 解密失败")
                except Exception as e:
                    self.log_message(f"[{i+1}/{len(self.input_files)}] 解密发生错误: {str(e)}", "error")
                    self.ffmpeg_handler.conversion_finished.emit(i, "failure", f"NCM 解密错误: {str(e)}")
            else:
                self.log_message(
                    f"[{i+1}/{len(self.input_files)}] "
                    f"{os.path.basename(inp)}  →  .{fmt}", "info")
                self.conversion_requested.emit(i, inp, args, stem)

    def _cleanup_cache(self):
        if not self.ncm_processing:
            return

        try:
            for cache_file in self.ncm_cache_files:
                if os.path.exists(cache_file):
                    os.remove(cache_file)

            if os.path.exists(self.cache_dir) and not os.listdir(self.cache_dir):
                os.rmdir(self.cache_dir)
            self.ncm_cache_files = []
            self.ncm_processing = False
        except Exception as e:
            self.log_message(f"清理缓存失败: {str(e)}", "warning")

    def _on_conversion_finished(self, idx, status, msg):
        # We use a heuristic: if we reach the last index or get cancelled, we clean up.
        # This is not perfect but works since the batch processor handles files sequentially.
        if self.ncm_processing:
            if idx == len(self.input_files) - 1 or status == "cancelled":
                self._cleanup_cache()
