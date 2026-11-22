import os
import sys
import uuid
import time
import re
import errno
import shutil
from urllib.parse import unquote, urlsplit
from collections import Counter, deque
from pathlib import Path

from PySide6.QtCore import QObject, Signal, QProcess, QTimer
if __package__:
    from .diagnostics import event, logger, setup
    from .runtime_paths import missing_runtime, ROOT
    from .engines import hardware_codec_for, plan, WORKER
    from .background_work import cleanup_path, run_background
    from .model_store import publish_model
    from .process_utils import timeout_setting
else:
    from diagnostics import event, logger, setup
    from runtime_paths import missing_runtime, ROOT
    from engines import hardware_codec_for, plan, WORKER
    from background_work import cleanup_path, run_background
    from model_store import publish_model
    from process_utils import timeout_setting


def source_details(source):
    if isinstance(source, Path):
        return source.name, source.stem, source.suffix.lower() == ".m3u8"
    parsed = urlsplit(source)
    filename = Path(unquote(parsed.path)).name or parsed.hostname or "M3U8"
    stem = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", Path(filename).stem).strip(" .") or "M3U8"
    return filename, stem, parsed.scheme.lower() in {"http", "https"}


def format_bytes(size, decimal=False):
    value = float(max(0, size))
    divisor = 1000 if decimal else 1024
    units = ("B", "KB", "MB", "GB", "TB") if decimal else ("B", "KiB", "MiB", "GiB", "TiB")
    for unit in units:
        if value < divisor or unit == units[-1]:
            return f"{int(value)} {unit}" if unit == "B" else f"{value:.1f} {unit}"
        value /= divisor


def create_stage(folder, prefix):
    """Fail immediately on ACL errors; tempfile's Windows retry loop can block Qt."""
    for _ in range(8):
        candidate = Path(folder) / (prefix + uuid.uuid4().hex)
        try:
            candidate.mkdir(mode=0o700)
            return candidate
        except FileExistsError:
            continue
    raise FileExistsError(f'Could not allocate a unique temporary directory in {folder}')


def prepare_conversion_output(requested):
    cache = ROOT/'cache'
    cache.mkdir(parents=True, exist_ok=True)
    stage = create_stage(cache, '.formix-')
    event('conversion_cache_created', stage=stage, destination=requested)
    return Path(requested), stage


def move_completed_file(source, destination):
    """Publish across filesystems without losing the cached result on failure."""
    try:
        os.replace(source, destination)
        return
    except OSError as exc:
        if exc.errno != errno.EXDEV and getattr(exc, 'winerror', None) != 17:
            raise
    temporary = destination.with_name('.formix-copy-' + uuid.uuid4().hex)
    try:
        with source.open('rb') as reader, temporary.open('xb') as writer:
            shutil.copyfileobj(reader, writer, 1024*1024)
            writer.flush()
            os.fsync(writer.fileno())
        os.replace(temporary, destination)
    finally:
        temporary.unlink(missing_ok=True)
    # Source is removed with its job cache after publication succeeds.


def publish_file(source, base):
    if not source.is_file() or not source.stat().st_size:
        raise ValueError('引擎未生成输出文件')
    base.parent.mkdir(parents=True, exist_ok=True)
    index = 0
    while True:
        destination = base if index == 0 else base.with_stem(f'{base.stem} ({index})')
        try:
            with destination.open('xb'):
                pass
            break
        except FileExistsError:
            index += 1
    try:
        move_completed_file(source, destination)
    except OSError:
        destination.unlink(missing_ok=True)
        raise
    return destination


def ncm_minimum_progress_seconds():
    try:
        import psutil
        physical_cores = psutil.cpu_count(logical=False) or psutil.cpu_count() or 2
        total_gib = psutil.virtual_memory().total / 1024**3
    except Exception:
        physical_cores, total_gib = 2, 4
    if physical_cores <= 2 or total_gib <= 4:
        return 180
    if physical_cores <= 4 or total_gib <= 8:
        return 120
    if physical_cores <= 8 or total_gib <= 16:
        return 60
    return 30


def kill_process_tree(process):
    """Stop only this owned QProcess and its descendants."""
    import psutil
    pid = process.processId()
    children = []
    if pid:
        try:
            children = psutil.Process(pid).children(recursive=True)
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass
    process.kill()
    for child in reversed(children):
        try:
            child.kill()
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass


class TaskService(QObject):
    runtime_missing = Signal(str)
    busy = Signal(bool)
    message = Signal(str)
    log = Signal(str, str)
    live_log = Signal(str, str)
    progress = Signal(int)
    file_status = Signal(str, str, str)
    progress_time = Signal(str)
    paused_changed = Signal(bool)
    model_stage_changed = Signal(str)
    ocr_text_ready = Signal(str)
    output_ready = Signal(str, str)
    stopped = Signal()
    def __init__(self, models, parent):
        super().__init__(parent)
        setup()
        self.task_id = None
        self.finalizing = False
        self._publication_complete = False
        self._publication_error = None
        self.error = b''
        self.cancelled = False
        self.models = models
        self.checking_engines = set()
        self.queue = deque()
        self.proc = None
        self.closing = False
        self.label = ""
        self.job_name = ""
        self.label_key = None
        self.paused = False
        self.active_job = None
        self.results = Counter()
        self.reported_missing = set()
        self.new_batch = True
        self.ncm_job = False
        self.ncm_progress_percent = 0
        self.pause_requested = False
        self.elapsed_timer = QTimer(self)
        self.elapsed_timer.setInterval(1000)
        self.elapsed_timer.timeout.connect(self.show_elapsed)
        self._stderr_buffer = ""
        self._stdout_buffer = ""
        self._progress_values = {}
        self.directory_output = False
        self.segment_dir = None
        self.hardware_encoder = None
        self.hardware_decode = False
        self.hardware_device = None
        self.hardware_fallback = False
        self.log_page = None
        self.suspended_processes = []
        self.watchdog_generation = 0
        self.watchdog_pending = False
        self.timed_out = False
        self.watchdog = QTimer(self)
        self.watchdog.setInterval(5000)
        self.watchdog.timeout.connect(self.check_activity)
        self.pending_engine_logs = deque(maxlen=400)
        self.engine_log_timer = QTimer(self)
        self.engine_log_timer.setInterval(100)
        self.engine_log_timer.timeout.connect(self.flush_engine_logs)

    def current_message(self):
        display_label=self.parent().t(self.label_key) if self.label_key else self.label
        return self.parent().t("task_processing",file=display_label,count=len(self.queue))

    def log_conversion(self, message):
        event('task_message', task=self.task_id, page=self.log_page, message=message)
        if self.log_page is not None:
            self.log.emit(self.log_page, message)

    def notify_task(self, message):
        self.log_conversion(message)
        self.message.emit(message)

    def next_job(self):
        if self.proc or self.finalizing or self.paused or not self.queue or self.closing:return
        name, source = self.queue[0][:2]
        if source is not None:
            component = {"文档转换": "libreoffice", "图片转换": "libvips", "图片压缩": "libvips", "PDF 转换": "pdf"}.get(name, "ffmpeg")
            if component in self.checking_engines:
                return
        if self.new_batch:
            self.results.clear()
            self.reported_missing.clear()
            self.new_batch = False
        self.active_job = self.queue.popleft()
        self.task_id = uuid.uuid4().hex[:12]
        self._publication_complete = False
        self._publication_error = None
        event('task_start', task=self.task_id, job=self.active_job, model=self.models)
        if len(self.active_job) == 6:
            self.active_job = (*self.active_job, {})
        name,src,option,audio,folder,hardware_mode,compression_params=self.active_job
        self.log_page = name if src is not None else "__model_download__"
        self.stage=self.out=None
        self.error=b""
        self.cancelled=False
        self.timed_out=False
        self.paused=False
        self._stderr_buffer=""
        self._stdout_buffer=""
        self._ocr_text = None
        self._progress_values={}
        self.ncm_job = src is not None and Path(src).suffix.lower() == ".ncm"
        self.ncm_progress_percent = 0
        self.ncm_minimum_seconds = ncm_minimum_progress_seconds() if self.ncm_job else 0
        self.ncm_source_ready = False
        self.directory_output=False
        self.segment_dir=None
        self.hardware_fallback=False
        self.hardware_encoder = None
        self.hardware_decode = False
        self.pause_requested = False
        self.hardware_mode=hardware_mode
        self.compression_params = dict(compression_params)
        self.stream_copy_attempt = name == "视频转换"
        self.reduced_metadata = False
        self.metadata_error = False
        self.label_key="task_model_download" if src is None else None
        source_name,source_stem,remote_playlist=source_details(src) if src is not None else (name,"",False)
        self.label=name if src is None else source_name
        try:
            if src is None:
                self.hardware_encoder=None
                self.hardware_device=None
                self.install_target = self.models.parent / option
                self.models.parent.mkdir(parents=True,exist_ok=True)
                self.stage=create_stage(self.models.parent, ".download-")
                cmd=[sys.executable,"-X","utf8",WORKER,"download",str(self.stage/"model"),option,audio]
            else:
                self.job_name,self.job_source,self.job_option,self.job_audio=name,src,option,audio
                if name == "视频转换" and not Path(src).is_file():
                    raise FileNotFoundError(f"输入视频不存在或无法访问：{src}")
                folder, self.stage = prepare_conversion_output(ROOT / "cache" if name == "图片提取文字" and option == "copy" else folder)
                self.output_folder=folder
                video_pages={"视频转换","视频压缩","M3U8 合成","音视频合并"}
                codecs=getattr(self.parent(),"hardware_video_encoders",{})
                codec=hardware_codec_for(name,src,option) if name in video_pages else None
                encoder_info=codecs.get(codec) if hardware_mode in {"auto","gpu","hybrid"} and codec else None
                self.hardware_encoder=encoder_info[0] if encoder_info else None
                self.hardware_device=encoder_info[1] if encoder_info else None
                self.hardware_decode = self.hardware_encoder == "h264_nvenc" and hardware_mode in {"auto", "gpu"}
                cmd,self.out=plan(name,src,option,audio,self.stage,self.models,
                                  hardware_encoder=self.hardware_encoder,hardware_device=self.hardware_device,
                                  hardware_decode=self.hardware_decode, compression_params=compression_params)
                if self.stream_copy_attempt:
                    self.log_conversion("优先直接复制音视频流，不重新编码、不降低画质。")
                elif self.hardware_encoder:
                    self.log_conversion(self.parent().t("video_gpu_pipeline" if self.hardware_decode else "video_hybrid_pipeline", encoder=self.hardware_encoder))
                self.directory_output=name=="视频转换" and option=="m3u8"
                self.base=folder/source_stem if self.directory_output else folder/(source_stem+self.out.suffix)
                if self.directory_output:
                    self.segment_dir=self.out.parent/source_stem
                if not self.stream_copy_attempt and hardware_mode in {"auto", "gpu", "hybrid"} and name in video_pages and self.hardware_encoder is None:
                    self.log_conversion(self.parent().t("video_gpu_unavailable"))
            self.notify_task(self.current_message())
            self.busy.emit(True)
            self.progress.emit(-1)
            display_label=self.parent().t(self.label_key) if self.label_key else self.label
            self.log_conversion(self.parent().t("log_started",file=display_label))
            if remote_playlist or name=="M3U8 合成":
                self.log_conversion(self.parent().t("log_m3u8_merge"))
            self.start_process(cmd)
        except Exception as exc:
            logger.exception('task_prepare_failed task=%s', self.task_id)
            self.error=str(exc).encode()
            self.done(1)

    def start_process(self,cmd):
        event('engine_start', task=self.task_id, command=cmd, stage=self.stage)
        self.durations = []
        self.has_progress = self.ncm_job
        self.ncm_progress_percent = 0
        self.ffmpeg_progress = "-progress" in cmd
        self.recent_lines = {}
        self.progress_detail = ""
        self.started_at = time.monotonic()
        self.last_activity = self.started_at
        self.activity_signature = None
        self.disk_signature = None
        self.watchdog_generation += 1
        self.idle_timeout = timeout_setting('FORMIX_TASK_IDLE_TIMEOUT', 1800 if self.active_job[0] == 'PDF 转换' or self.active_job[1] is None else 900)
        if self.label_key == "task_model_download":
            self.idle_timeout = timeout_setting("FORMIX_MODEL_INSTALL_TIMEOUT", 14400)
        self.watchdog.start()
        self.report_file("queue_processing")
        self.elapsed_timer.start()
        self.proc=QProcess(self)
        self.proc.started.connect(self.on_process_started)
        self.proc.readyReadStandardError.connect(self.read_error)
        self.proc.readyReadStandardOutput.connect(self.read_output)
        self.proc.finished.connect(self.done)
        self.proc.errorOccurred.connect(self.process_error)
        self.proc.start(cmd[0],cmd[1:])

    def on_process_started(self):
        event('engine_started', task=self.task_id, child_pid=self.proc.processId())
        if self.cancelled:
            kill_process_tree(self.proc)
        elif self.pause_requested:
            self.pause_requested = False
            self.toggle_pause()

    def check_activity(self):
        if not self.proc or self.paused or self.watchdog_pending:
            return
        generation, stage = self.watchdog_generation, self.stage
        self.watchdog_pending = True

        def snapshot():
            total = count = 0
            if stage:
                for directory, _, names in os.walk(stage):
                    for name in names:
                        try:
                            total += (Path(directory) / name).stat().st_size
                            count += 1
                        except OSError:
                            continue
            return count, total

        def checked(signature, error):
            self.watchdog_pending = False
            if generation != self.watchdog_generation or not self.proc or self.paused:
                return
            now = time.monotonic()
            if not error and signature != self.disk_signature:
                self.disk_signature = signature
                self.last_activity = now
            if now - self.last_activity > self.idle_timeout:
                self.timed_out = True
                self.error = self.parent().t('task_stalled').encode('utf-8')
                kill_process_tree(self.proc)
        run_background(snapshot, checked)

    def report_file(self, key):
        if self.active_job and self.active_job[1] is not None:
            self.file_status.emit(self.active_job[0], str(self.active_job[1]), key)

    def show_elapsed(self):
        seconds = int(time.monotonic() - self.started_at)
        elapsed = f"{seconds // 60:02}:{seconds % 60:02}"
        if self.ncm_job and self.active_job and not self.paused and self.ncm_minimum_seconds:
            estimate = min(99, int((time.monotonic() - self.started_at) * 100 / self.ncm_minimum_seconds))
            self.emit_progress(max(self.ncm_progress_percent, estimate))
            self.progress_detail = self.parent().t("log_worker_progress",
                stage=self.parent().t("queue_processing"), current=self.ncm_progress_percent,
                total=100, percent=self.ncm_progress_percent)
        if not self.has_progress:
            self.progress_time.emit(elapsed)
        if self.label_key == "task_model_download" and not self.progress_detail:
            return
        if self.log_page is not None and not self.paused and not self.cancelled:
            detail = self.progress_detail or self.parent().t("queue_processing")
            self.live_log.emit(self.log_page, self.parent().t("log_live_elapsed", detail=detail, elapsed=elapsed))

    def emit_progress(self, percent):
        if self.ncm_job and percent >= 0:
            self.ncm_progress_percent = max(self.ncm_progress_percent, percent)
            percent = self.ncm_progress_percent
        self.progress.emit(percent)

    def retry_media_job(self, *, reduced_metadata=False, transcode=False):
        try:
            if self.proc:
                self.proc.deleteLater()
                self.proc=None
            self.discard_stage()
            _, self.stage=prepare_conversion_output(self.output_folder)
            if transcode:
                self.stream_copy_attempt = False
                self.compression_params["video_transcode"] = True
                # Avoid implicit pixel-format conversion on the lossless path.
                self.hardware_decode = False
            elif reduced_metadata:
                self.reduced_metadata = True
            else:
                self.hardware_decode = False
                self.hardware_encoder = self.hardware_device = None
                self.hardware_fallback = True
            cmd,self.out=plan(self.job_name,self.job_source,self.job_option,self.job_audio,
                              self.stage,self.models,hardware_encoder=self.hardware_encoder,
                              hardware_device=self.hardware_device,reduced_metadata=self.reduced_metadata,
                              hardware_decode=self.hardware_decode,
                              compression_params=self.compression_params)
            self.directory_output=self.job_name=="视频转换" and self.job_option=="m3u8"
            self.segment_dir=self.out.parent/Path(str(self.job_source)).stem if self.directory_output else None
            self.metadata_error = False
            self.error=b""
            self._stderr_buffer=""
            self._stdout_buffer=""
            self._progress_values={}
            self.log_conversion("直接封装失败，尝试无损转码（文件可能增大）；音频保持原编码。" if transcode else self.parent().t("metadata_retry" if reduced_metadata else "video_gpu_fallback"))
            self.progress.emit(-1)
            self.start_process(cmd)
            return True
        except Exception as exc:
            self.error=str(exc).encode()
            return False
    def process_error(self,error):
        if error==QProcess.ProcessError.FailedToStart:
            self.error=self.proc.errorString().encode()
            self.done(1)
    def read_error(self):
        if not self.proc:
            return
        chunk=bytes(self.proc.readAllStandardError())
        if not chunk:
            return
        text=self._stderr_buffer+chunk.decode("utf-8","replace")
        lines=text.splitlines()
        if text and not text.endswith(("\n","\r")):
            self._stderr_buffer=lines.pop() if lines else text
        else:
            self._stderr_buffer=""
        for line in lines:
            self._consume_stderr_line(line)
    def read_output(self):
        if not self.proc:
            return
        chunk=bytes(self.proc.readAllStandardOutput())
        if not chunk:
            return
        text=self._stdout_buffer+chunk.decode("utf-8","replace")
        lines=text.splitlines()
        if text and not text.endswith(("\n","\r")):
            self._stdout_buffer=lines.pop() if lines else text
        else:
            self._stdout_buffer=""
        for line in lines:
            line = line.strip()
            if self.label_key == "task_model_download":
                progress = re.fullmatch(r"Progress (\d+) of (\d+)", line)
                if progress:
                    current, total = map(int, progress.groups())
                    self.progress_detail = "pip ↓ " + format_bytes(current, decimal=True)
                    if total:
                        self.progress_detail += " / " + format_bytes(total, decimal=True)
                    self.last_activity = time.monotonic()
                    continue
                self.progress_detail = ""
            self.log_engine_line(line)

    def log_engine_line(self, line):
        if line.startswith("FORMIX_OCR_TEXT|"):
            import base64
            self._ocr_text = base64.b64decode(line.split("|",1)[1]).decode("utf-8")
            return
        event('engine_output', task=self.task_id, line=line[:16384])
        line = line[:4096]
        if not line or line in self.recent_lines:
            return
        if re.search(r"\b\d{1,3}%\s*\|.*\|", line):
            return
        self.recent_lines[line] = None
        if len(self.recent_lines) > 128:
            del self.recent_lines[next(iter(self.recent_lines))]
        self.pending_engine_logs.append(line)
        if not self.engine_log_timer.isActive():
            self.engine_log_timer.start()

    def flush_engine_logs(self):
        self.engine_log_timer.stop()
        if self.pending_engine_logs:
            message = '\n'.join(self.pending_engine_logs)
            self.pending_engine_logs.clear()
            self.log_conversion(message)

    def _consume_stderr_line(self,line):
        if line.startswith('FORMIX_'):
            event('engine_progress', task=self.task_id, message=line)
        line=line.strip()
        if not line:
            return
        if self.ffmpeg_progress and "[info]" in line:
            match = re.search(r"\[info\]\s*Duration: (\d+):(\d+):([\d.]+)", line)
            if match:
                hours, minutes, seconds = match.groups()
                self.durations.append(int(hours)*3600 + int(minutes)*60 + float(seconds))
            return
        if re.search(r"(?i)(?:error|failed|failure|invalid|malformed|unable|could not).*?(?:metadata|exif|id3|timecode|chapter)|(?:metadata|exif|id3|timecode|chapter).*?(?:error|failed|failure|invalid|malformed|unable|could not)", line):
            self.metadata_error = True
        if self.label_key == "task_model_download" and line.startswith("FORMIX_MODEL|"):
            stage = line.partition("|")[2]
            if stage in ("preparing_runtime", "downloading_model"):
                self.model_stage_changed.emit(stage)
                self.log_engine_line(self.parent().t(stage))
                return
        if line.startswith("FORMIX_PROGRESS|"):
            parts=line.split("|",3)
            if len(parts)==4:
                try:
                    current,total=int(parts[2]),int(parts[3])
                    signature = (parts[1], current, total)
                    if self.activity_signature != signature:
                        self.activity_signature = signature
                        self.last_activity = time.monotonic()
                    if parts[1] == "ncm":
                        percent=max(0,min(25,current)) if total else -1
                        stage=self.parent().t("queue_processing")
                    elif parts[1] == "ncm_direct":
                        percent=max(0,min(100,round(current*100/total))) if total else -1
                        stage=self.parent().t("queue_processing")
                    else:
                        percent=max(0,min(100,round(current*100/total))) if total else -1
                        stage = self.parent().t("downloading_model" if parts[1] == "model" else "log_pdf_pages") if parts[1] in {"model", "pdf"} else parts[1]
                    self.emit_progress(percent)
                    if percent >= 0:
                        self.has_progress = True
                    display_current = format_bytes(current, decimal=True) if parts[1] == "model" else current
                    display_total = format_bytes(total, decimal=True) if parts[1] == "model" else total
                    self.progress_detail = self.parent().t(
                        "log_worker_progress", stage=stage, current=display_current,
                        total=display_total, percent=percent)
                except ValueError:
                    self.log_conversion(line)
            return
        if line == "FORMIX_NCM_READY":
            self.ncm_source_ready = True
            return
        if self.ffmpeg_progress and "=" in line:
            key,value=line.split("=",1)
            if key in {"frame","out_time","out_time_us","out_time_ms","speed","progress"}:
                self._progress_values[key]=value
                if key=="progress" and value in {"continue","end"}:
                    self._emit_ffmpeg_progress(value=="end")
                return
            if re.fullmatch(r"[A-Za-z0-9_]+", key):
                return
        self.error=(self.error+(line+"\n").encode("utf-8","replace"))[-3000:]
        self.log_engine_line(line)
    def _emit_ffmpeg_progress(self,final=False):
        percent = -1
        microseconds = self._progress_values.get("out_time_us", "")
        signature = (microseconds, self._progress_values.get('frame'))
        if signature != self.activity_signature:
            self.activity_signature = signature
            self.last_activity = time.monotonic()
        if microseconds.lstrip("-").isdigit():
            seconds = max(0, int(microseconds)) / 1_000_000
            self.has_progress = True
            if self.durations and min(self.durations) > 0:
                if self.ncm_job:
                    percent = min(99, int((time.monotonic() - self.started_at) * 100 /
                                          max(1, self.ncm_minimum_seconds)))
                    self.emit_progress(percent)
                else:
                    percent = min(99, int(seconds * 100 / min(self.durations)))
                    self.emit_progress(percent)
            else:
                self.progress_time.emit(self._progress_values.get("out_time", "").split(".")[0])
        if self.ncm_job:
            percent = min(99, int((time.monotonic() - self.started_at) * 100 /
                                  max(1, self.ncm_minimum_seconds)))
            self.progress_detail = self.parent().t("log_worker_progress",
                stage=self.parent().t("queue_processing"), current=max(self.ncm_progress_percent, percent),
                total=100, percent=max(self.ncm_progress_percent, percent))
        else:
            processed=self._progress_values.get("out_time","00:00:00.000000")
            speed=self._progress_values.get("speed","—")
            self.progress_detail = self.parent().t("log_ffmpeg_progress",time=processed,speed=speed)
            if percent >= 0 and not final:
                self.progress_detail += f" · {percent}%"
    def toggle_pause(self):
        event('pause_toggle', task=self.task_id, was_paused=self.paused)
        if self.pause_requested or self.active_job is None or self.active_job[1] is None:
            return
        if self.paused:
            for process in reversed(self.suspended_processes):
                try:
                    process.resume()
                except Exception as exc:
                    self.log_conversion(str(exc))
            self.suspended_processes = []
            elapsed = time.monotonic() - self.paused_at
            self.started_at += elapsed
            self.last_activity += elapsed
            self.paused = False
            self.elapsed_timer.start()
            self.report_file('queue_processing')
            self.paused_changed.emit(False)
            self.log_conversion(self.parent().t("log_resumed"))
        elif self.proc and not self.cancelled:
            if not self.proc.processId():
                self.pause_requested = True
                return
            import psutil
            suspended = []
            try:
                root = psutil.Process(self.proc.processId())
                root.suspend()
                suspended.append(root)
                for process in root.children(recursive=True):
                    try:
                        process.suspend()
                        suspended.append(process)
                    except psutil.NoSuchProcess:
                        continue
            except (psutil.NoSuchProcess, psutil.AccessDenied) as exc:
                for process in reversed(suspended):
                    try:
                        process.resume()
                    except (psutil.NoSuchProcess, psutil.AccessDenied):
                        pass
                self.log_conversion(str(exc))
                return
            self.suspended_processes = suspended
            self.paused_at = time.monotonic()
            self.paused = True
            self.elapsed_timer.stop()
            self.report_file('file_paused')
            self.paused_changed.emit(True)
            self.notify_task(self.parent().t('log_paused'))

    def discard_stage(self):
        if self.stage is not None:
            path = self.stage
            page = self.log_page
            self.stage = None
            cleanup_path(path, lambda _, error: self.log.emit(page, str(error)) if error and page and not self.closing else None)
    def done(self,code,*_):
        event('engine_exit', task=self.task_id, code=code, cancelled=self.cancelled,
              timed_out=self.timed_out, error=self.error.decode(errors='replace'))
        self.watchdog.stop()
        self.watchdog_generation += 1
        self.suspended_processes = []
        self.elapsed_timer.stop()
        if self.proc:
            self.read_error()
            self.read_output()
        if self._stderr_buffer.strip():
            self._consume_stderr_line(self._stderr_buffer)
            self._stderr_buffer=""
        if self._stdout_buffer.strip():
            self.log_engine_line(self._stdout_buffer.strip())
            self._stdout_buffer=""
        self.flush_engine_logs()
        if self.proc and self.progress_detail:
            self.show_elapsed()
        gpu_output_missing = False
        if not code and self.hardware_encoder and self.out and not self._publication_complete:
            try:
                gpu_output_missing = not self.out.is_file() or self.out.stat().st_size == 0
            except OSError:
                gpu_output_missing = True
        media_pages = {"音频转换", "音频压缩", "视频转换", "视频压缩", "M3U8 合成", "音视频合并", "音视频分离"}
        if (code and self.proc and not self.cancelled and not self.timed_out and not self.label_key and self.job_name in media_pages
                and self.metadata_error and not self.reduced_metadata):
            if self.retry_media_job(reduced_metadata=True):
                return
        if code and getattr(self, "stream_copy_attempt", False) and not self.cancelled and not self.timed_out:
            if self.retry_media_job(transcode=True):
                return
        if (code or gpu_output_missing) and self.hardware_encoder and not self.hardware_fallback and not self.cancelled and not self.timed_out:
            if self.retry_media_job():
                return
        copy_only = self.job_name == "图片提取文字" and self.job_option == "copy" if not self.label_key else False
        if not code and not self.cancelled and self.out and not copy_only and not self._publication_complete:
            if self.finalizing:
                return
            self.finalizing = True
            self.log_conversion('转换完成，正在将缓存结果保存到输出目录…')
            event('publication_start', task=self.task_id, cache=self.stage, destination=self.base)
            def publish():
                if self.job_name == "音视频分离" and self.job_option == "both":
                    video = next(self.out.parent.glob("video.*"), None)
                    if video is None or not video.stat().st_size or not self.out.is_file() or not self.out.stat().st_size:
                        raise ValueError("引擎未生成输出文件")
                    audio_dest = publish_file(self.out, self.base.with_stem(self.base.stem + "_audio"))
                    try:
                        video_dest = publish_file(video, self.base.with_name(self.base.stem + "_video" + video.suffix))
                    except Exception:
                        shutil.copy2(audio_dest, self.out)
                        audio_dest.unlink()
                        raise
                    return [audio_dest, video_dest]
                return self.commit_hls_output() if self.directory_output else publish_file(self.out, self.base)
            def published(destination, error):
                self.finalizing = False
                self._publication_complete = True
                self._publication_error = error
                self._published_destination = destination
                self.done(0)
            run_background(publish, published)
            return
        success=False
        preserve_stage=False
        compression_report = None
        try:
            if self.cancelled: result=self.parent().t("task_cancelled")
            elif code:
                result=self.error.decode(errors="replace").strip()[-800:] or self.parent().t("conversion_failed")
                if not self.label_key and self.job_name == "视频转换" and self.job_option == "webm" and "Only VP8 or VP9 or AV1" in self.error.decode(errors="replace"):
                    result = "WebM 不支持当前音视频编码组合。为避免有损转换或丢失音轨，已停止输出；请改用 MKV。"
            elif copy_only:
                if not self._ocr_text:
                    raise ValueError("未收到识别结果")
                self.ocr_text_ready.emit(self._ocr_text)
                result = self.parent().t("image_ocr_copy_done")
            elif self.out:
                if self._publication_error:
                    raise self._publication_error
                dest = self._published_destination
                destinations = dest if isinstance(dest, list) else [dest]
                dest = destinations[0]
                if self.job_name in {"音频压缩", "视频压缩", "图片压缩"}:
                    try:
                        compression_report = (Path(self.job_source).stat().st_size, dest.stat().st_size)
                    except OSError:
                        compression_report = None
                result=self.parent().t("saved_to",path="\n".join(str(path) for path in destinations))
                for path in destinations:
                    event('file_written', task=self.task_id, path=path, bytes=path.stat().st_size)
                    self.output_ready.emit(self.job_name, str(path))
            else:
                retired = publish_model(self.stage/"model", self.install_target)
                if retired:
                    cleanup_path(retired)
                result=f"{self.parent().t('model_downloaded')} · {self.install_target}"
            success=not self.cancelled and not code
        except Exception as exc:
            logger.exception('task_finalize_failed task=%s', self.task_id)
            result=str(exc)
            if self.out and self.out.is_file():
                preserve_stage=True
                result += f'\n转换结果已保留，请从此处取回文件：{self.out}'
                event('conversion_output_preserved', task=self.task_id, path=self.out)
        known_errors={
            "请安装 FFmpeg 并将其加入 PATH":"ffmpeg_missing",
            "请安装 LibreOffice，或将 soffice 加入 PATH":"office_missing",
            "引擎未生成输出文件":"engine_no_output",
        }
        if code and not self.cancelled and not self.closing:
            dependency = missing_runtime(self.error.decode(errors="replace"), code)
            if dependency and dependency not in self.reported_missing:
                self.reported_missing.add(dependency)
                self.runtime_missing.emit(dependency)
        if result in known_errors:
            result=self.parent().t(known_errors[result])
        if not preserve_stage:
            self.discard_stage()
        outcome = "file_done" if success else ("task_cancelled" if self.cancelled else "conversion_failed")
        self.results[outcome] += 1
        event('task_finish', task=self.task_id, outcome=outcome, result=result)
        self.new_batch = not self.queue
        self.report_file(outcome)
        self.active_job = None
        if self.proc:self.proc.deleteLater()
        self.proc=None
        self.paused=False
        self.paused_changed.emit(False)
        self.emit_progress(100 if success else 0)
        self.busy.emit(False)
        display_label=self.parent().t(self.label_key) if self.label_key else self.label
        if compression_report and success:
            original_size, compressed_size = compression_report
            difference = abs(original_size - compressed_size)
            percent = round(difference * 100 / original_size, 1) if original_size else 0
            key = "compression_result_saved" if compressed_size <= original_size else "compression_result_larger"
            self.log_conversion(self.parent().t(
                key, original=format_bytes(original_size), compressed=format_bytes(compressed_size),
                amount=format_bytes(difference), percent=percent,
            ))
        self.notify_task(self.parent().t("task_result",file=display_label,result=result))
        if self.closing:self.stopped.emit()
        else:QTimer.singleShot(0,self.next_job)

    def commit_hls_output(self):
        """Publish a self-contained HLS folder; expose the playlist last."""
        playlist = self.out
        if not playlist.is_file() or not self.segment_dir.is_dir():
            raise ValueError("引擎未生成输出文件")
        original = playlist.read_text(encoding="utf-8-sig").splitlines()
        if not original or original[0] != "#EXTM3U" or "#EXT-X-ENDLIST" not in original:
            raise ValueError("HLS 播放清单不完整")
        segments = {}
        lines = []
        for line in original:
            if line and not line.startswith("#"):
                filename = line.replace("\\", "/").rsplit("/", 1)[-1]
                source = self.segment_dir / filename
                if not source.is_file() or source.is_symlink() or not source.stat().st_size:
                    raise ValueError(f"HLS 分片缺失或为空：{filename}")
                if filename not in segments:
                    segments[filename] = (source, f"segment_{len(segments):05d}.ts")
                line = segments[filename][1]
            lines.append(line)
        if not segments:
            raise ValueError("HLS 播放清单没有分片")
        self.base.parent.mkdir(parents=True, exist_ok=True)
        index = 0
        while True:
            stem = self.base.name if index == 0 else f"{self.base.name} ({index})"
            directory = self.base.with_name(stem)
            try:
                directory.mkdir()
                break
            except FileExistsError:
                index += 1
        try:
            for source, name in segments.values():
                shutil.copy2(source, directory / name)
            target = directory / "index.m3u8"
            temporary = directory / ".index.part"
            temporary.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
            os.replace(temporary, target)
            return target
        except BaseException:
            cleanup_path(directory)
            raise

    def stop(self):
        event('task_stop_requested', task=self.task_id)
        if self.finalizing:
            self.log_conversion("正在保存转换结果，请稍候…")
            return
        if self.paused and not self.proc:
            self.paused = False
            self.cancelled = True
            self.done(1)
            return
        if self.proc:
            self.cancelled=True
            kill_process_tree(self.proc)
