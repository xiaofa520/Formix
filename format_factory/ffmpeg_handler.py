# format_factory/ffmpeg_handler.py
"""
FFmpegHandler  —  serial queue, batch safe.

• convert_file()  puts each task in a Queue; a single worker thread
  drains it one‑by‑one, emitting signals to the GUI thread safely.
• cancel_conversion()  drains the queue and terminates the running
  subprocess; the worker then emits "cancelled" for any in‑flight task.
"""
import subprocess
import threading
import queue
import os
import re
import json

from PyQt6.QtCore import QObject, pyqtSignal
from format_factory.config import get_ffmpeg_path, get_ffprobe_path


def _is_stats_line(line: str) -> bool:
    """
    Return True for noisy FFmpeg encoder-statistics lines that should be
    excluded from error summaries shown to the user.
    Examples:
      [libx264 @ 0x…] mb P I16..4: …
      [aac @ 0x…] Qavg: nan
      kb/s:6598.03
    """
    s = line.strip()
    if re.match(r"\[(?:libx264|libx265|aac|libmp3lame|libvorbis|libopus|"
                r"libvpx|mpeg4|flv)\s*@\s*[0-9a-fA-Fx]+\]", s):
        return True
    if re.match(r"(?:kb/s:|Conversion failed!|frame=|fps=|bitrate=|speed=)", s):
        return True
    return False


class FFmpegHandler(QObject):
    progress_update     = pyqtSignal(int, str, int)   # idx, msg, pct
    conversion_finished = pyqtSignal(int, str, str)   # idx, status, msg
    conversion_started  = pyqtSignal(int, str)         # idx, path
    file_info_ready     = pyqtSignal(str, dict, str)   # path, info, err
    log_line            = pyqtSignal(int, str, str)    # idx, kind, text
    # kind: "meta"=媒体信息  "encoder"=编码器行  "progress"=实时进度  "warn"=警告

    def __init__(self):
        super().__init__()
        self.ffmpeg_path  = get_ffmpeg_path()
        self.ffprobe_path = get_ffprobe_path()
        if not self.ffmpeg_path:
            raise FileNotFoundError(
                "FFmpeg executable not found. Please check config.")

        self._q           = queue.Queue()
        self._proc        = None          # current subprocess
        self._cancel      = threading.Event()
        self._worker      = None
        self._lock        = threading.Lock()

    # ── public ──────────────────────────────────────────────────────
    def convert_file(self, idx: int, inp: str, out: str, args: list):
        """Enqueue one task. Worker auto‑starts if idle."""
        self._q.put((idx, inp, out, args))
        self._start_worker()

    def cancel_conversion(self):
        """Cancel in‑flight task and drain queue."""
        # drain pending
        while True:
            try:
                self._q.get_nowait()
                self._q.task_done()
            except queue.Empty:
                break
        self._cancel.set()
        with self._lock:
            if self._proc:
                try:
                    self._proc.terminate()
                except Exception:
                    pass

    def get_file_info_ffprobe(self, path: str):
        if not self.ffprobe_path:
            self.file_info_ready.emit(path, {},
                "FFprobe not found.")
            return
        cmd = [self.ffprobe_path, "-v", "quiet",
               "-print_format", "json",
               "-show_format", "-show_streams", path]
        t = threading.Thread(target=self._probe, args=(path, cmd), daemon=True)
        t.start()

    # ── worker ──────────────────────────────────────────────────────
    def _start_worker(self):
        with self._lock:
            if self._worker and self._worker.is_alive():
                return
            self._worker = threading.Thread(
                target=self._loop, daemon=True)
            self._worker.start()

    def _loop(self):
        while True:
            try:
                task = self._q.get(timeout=0.5)
            except queue.Empty:
                break   # nothing left — exit; next enqueue restarts

            if self._cancel.is_set():
                idx, inp = task[0], task[1]
                self.conversion_finished.emit(
                    idx, "cancelled",
                    f"'{os.path.basename(inp)}' 已跳过（取消中）。")
                self._q.task_done()
                continue

            self._run(*task)
            self._q.task_done()

        self._cancel.clear()   # reset after queue fully drained

    # ── output file cleanup ─────────────────────────────────────────
    @staticmethod
    def _cleanup_output(out: str, inp: str, log_cb) -> str:
        """
        Delete the output file if it looks broken, return a verdict:
          "ok"      – file looks complete (skip delete)
          "deleted" – file was deleted (too small / suspicious)
          "missing" – output file didn't exist at all
        """
        if not os.path.exists(out):
            return "missing"

        # M3U8 playlist 文件本身很小，跳过大小检查
        if out.endswith(".m3u8"):
            return "ok"

        out_sz = os.path.getsize(out)

        # Always delete zero-byte files
        if out_sz == 0:
            try:
                os.remove(out)
                log_cb(f"已删除空白输出文件: {os.path.basename(out)}")
            except OSError:
                pass
            return "deleted"

        # Compare to source size where available
        try:
            inp_sz = os.path.getsize(inp) if inp and os.path.exists(inp) else 0
        except OSError:
            inp_sz = 0

        # Heuristic: if source is known AND output is <1 % of source,
        # it's almost certainly a corrupt stub from an aborted encode.
        # (For format conversions output can legitimately be smaller,
        #  e.g. a large WAV → MP3, so we use a very conservative 1 %.)
        suspicious = (inp_sz > 0 and out_sz < inp_sz * 0.01
                      and out_sz < 512 * 1024)   # also cap at 512 KB

        if suspicious:
            try:
                os.remove(out)
                in_mb  = inp_sz  / 1024 / 1024
                out_kb = out_sz  / 1024
                log_cb(
                    f"已删除疑似损坏文件: {os.path.basename(out)} "
                    f"({out_kb:.0f} KB, 源文件 {in_mb:.1f} MB)")
            except OSError as e:
                log_cb(f"删除失败: {os.path.basename(out)} – {e}")
            return "deleted"

        return "ok"

    # ── ffmpeg ──────────────────────────────────────────────────────
    def _run(self, idx: int, inp: str, out: str, args: list):
        cmd = [self.ffmpeg_path, "-y", "-i", inp] + args + [out]

        # Emit the full command as first log line
        self.log_line.emit(idx, "cmd", "$ ffmpeg " + " ".join(
            f'"{a}"' if " " in a else a for a in cmd[1:]))

        self.conversion_started.emit(idx, inp)
        flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0

        # Compiled patterns for parsing FFmpeg stderr
        dur_re      = re.compile(r"Duration:\s*(\d{2}):(\d{2}):(\d{2})[\.,](\d+)")
        time_re     = re.compile(r"time=\s*(\d{2}):(\d{2}):(\d{2})[\.,]")
        stream_re   = re.compile(r"Stream #\d+:\d+.*")
        input_re    = re.compile(r"Input #\d+,\s*([\w,]+),\s*from")
        output_re   = re.compile(r"Output #\d+,\s*([\w,]+),\s*to")
        video_re    = re.compile(r"Stream.*Video:\s*(\S+).*?(\d+x\d+).*?(\d+(?:\.\d+)?\s*fps)")
        audio_re    = re.compile(r"Stream.*Audio:\s*(\S+).*?(\d+)\s*Hz.*?(\d+)\s*(?:kb/s|ch)")
        encoder_re  = re.compile(r"encoder\s*:\s*(.+)")
        speed_re    = re.compile(r"speed=\s*([\d\.]+x)")
        bitrate_re  = re.compile(r"bitrate=\s*([\d\.]+\s*\S+/s)")
        fps_re      = re.compile(r"\bfps=\s*([\d\.]+)")
        size_re     = re.compile(r"size=\s*([\d\.]+\w+)")
        warn_re     = re.compile(r"\b(warning|error|invalid|failed|cannot|unable|not found)\b",
                                 re.IGNORECASE)

        total_s     = 0
        last_lines  = []
        last_pct    = -1

        try:
            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                encoding="utf-8", errors="replace",
                creationflags=flags)
            with self._lock:
                self._proc = proc

            for raw in proc.stderr:
                line = raw.rstrip()
                last_lines.append(line)
                if len(last_lines) > 40:
                    last_lines.pop(0)

                if self._cancel.is_set():
                    proc.terminate(); proc.wait()
                    with self._lock:
                        self._proc = None
                    # Delete the partial output file
                    self._cleanup_output(out, inp,
                        lambda msg: self.log_line.emit(idx, "warn", msg))
                    self.conversion_finished.emit(
                        idx, "cancelled",
                        f"'{os.path.basename(inp)}' 已取消。")
                    return

                # ── Parse & emit structured log lines ──────────────
                stripped = line.strip()
                if not stripped:
                    continue

                # Duration / total length
                m = dur_re.search(line)
                if m and total_s == 0:
                    h, mn, s, cs = int(m.group(1)), int(m.group(2)), \
                                   int(m.group(3)), int(m.group(4))
                    total_s = h * 3600 + mn * 60 + s + cs / 100
                    self.log_line.emit(idx, "meta",
                        f"时长: {m.group(1)}:{m.group(2)}:{m.group(3)}")
                    continue

                # Input container format
                m = input_re.search(line)
                if m:
                    self.log_line.emit(idx, "meta",
                        f"输入格式: {m.group(1)}")
                    continue

                # Output container format
                m = output_re.search(line)
                if m:
                    self.log_line.emit(idx, "meta",
                        f"输出格式: {m.group(1)}")
                    continue

                # Video stream info
                m = video_re.search(line)
                if m:
                    self.log_line.emit(idx, "meta",
                        f"视频流: 编码={m.group(1)}  分辨率={m.group(2)}  帧率={m.group(3)}")
                    continue

                # Audio stream info
                m = audio_re.search(line)
                if m:
                    self.log_line.emit(idx, "meta",
                        f"音频流: 编码={m.group(1)}  采样率={m.group(2)}Hz  {m.group(3)}")
                    continue

                # Encoder tag in metadata
                m = encoder_re.search(line)
                if m:
                    self.log_line.emit(idx, "encoder",
                        f"编码器: {m.group(1).strip()}")
                    continue

                # Real-time progress line  (frame=… fps=… size=… time=… bitrate=… speed=…)
                if "frame=" in line and "time=" in line:
                    tm = time_re.search(line)
                    if tm and total_s > 0:
                        h2, mn2, s2 = int(tm.group(1)), int(tm.group(2)), int(tm.group(3))
                        cur = h2 * 3600 + mn2 * 60 + s2
                        pct = min(99, int(cur / total_s * 100))

                        # Build compact progress summary
                        parts = [f"{tm.group(1)}:{tm.group(2)}:{tm.group(3)}"]
                        sm = size_re.search(line)
                        if sm:  parts.append(f"大小={sm.group(1)}")
                        bm = bitrate_re.search(line)
                        if bm:  parts.append(f"码率={bm.group(1)}")
                        fm = fps_re.search(line)
                        if fm:  parts.append(f"fps={fm.group(1)}")
                        spm = speed_re.search(line)
                        if spm: parts.append(f"速度={spm.group(1)}")

                        self.log_line.emit(idx, "progress",
                            f"进度 {pct:3d}%  " + "  ".join(parts))
                        self.progress_update.emit(idx, "转换中…", pct)
                        last_pct = pct
                    continue

                # Warnings / errors from FFmpeg
                if warn_re.search(stripped):
                    # Skip noisy encoder-stats lines
                    if not any(k in stripped for k in
                               ("kb/s", "frame=", "fps=", "Stream mapping")):
                        self.log_line.emit(idx, "warn", stripped[:200])
                    continue

            proc.wait()
            with self._lock:
                self._proc = None

            if proc.returncode == 0:
                # Even on success, verify output is not suspiciously tiny
                verdict = self._cleanup_output(out, inp,
                    lambda msg: self.log_line.emit(idx, "warn", msg))
                if verdict == "deleted":
                    tail = "\n".join(
                        l for l in last_lines[-10:]
                        if l.strip() and not _is_stats_line(l))
                    self.conversion_finished.emit(
                        idx, "failure",
                        f"'{os.path.basename(inp)}' 转换结果异常，输出文件已删除。\n{tail}")
                else:
                    self.conversion_finished.emit(
                        idx, "success",
                        f"'{os.path.basename(inp)}'  →  '{os.path.basename(out)}' ✓")
            else:
                # Delete the broken partial output
                self._cleanup_output(out, inp,
                    lambda msg: self.log_line.emit(idx, "warn", msg))
                tail = "\n".join(
                    l for l in last_lines[-15:]
                    if l.strip() and not _is_stats_line(l))
                self.conversion_finished.emit(
                    idx, "failure",
                    f"'{os.path.basename(inp)}' 失败 (code {proc.returncode})\n{tail}")

        except FileNotFoundError:
            self._cleanup_output(out, inp, lambda msg: None)
            self.conversion_finished.emit(
                idx, "failure", f"找不到 FFmpeg：{self.ffmpeg_path}")
        except Exception as exc:
            self._cleanup_output(out, inp, lambda msg: None)
            self.conversion_finished.emit(
                idx, "failure", f"意外错误：{exc}")
        finally:
            with self._lock:
                self._proc = None

    # ── ffprobe ─────────────────────────────────────────────────────
    def _probe(self, path: str, cmd: list):
        info, err = {}, ""
        flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
        try:
            proc = subprocess.Popen(cmd,
                stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                encoding="utf-8", errors="replace", creationflags=flags)
            out, serr = proc.communicate(timeout=15)
            if proc.returncode == 0:
                info = json.loads(out)
            else:
                err = f"FFprobe 错误 {proc.returncode}: {serr.strip()}"
        except subprocess.TimeoutExpired:
            proc.kill(); proc.communicate()
            err = f"FFprobe 超时: {path}"
        except json.JSONDecodeError as e:
            err = f"FFprobe 输出解析失败: {e}"
        except Exception as e:
            err = f"FFprobe 意外错误: {e}"
        finally:
            self.file_info_ready.emit(path, info, err)