"""Filter and stat imports off-thread, delivering bounded incremental batches."""
import os
from pathlib import Path
import stat
import threading
from PySide6.QtCore import QObject, QRunnable, QLocale, Signal


class ScanSignals(QObject):
    batch = Signal(object, list)
    finished = Signal(object, int, str)


class FileScanTask(QRunnable):
    def __init__(self, paths, extensions):
        super().__init__()
        self.paths, self.extensions = paths, extensions
        self.signals = ScanSignals()
        self.cancelled = threading.Event()
        self.slots = threading.Semaphore(4)
        self.added_count = 0
        self.setAutoDelete(False)

    def run(self):
        batch, seen, errors = [], set(), []
        skipped = 0

        def send():
            while not self.cancelled.is_set():
                if self.slots.acquire(timeout=.1):
                    self.signals.batch.emit(self, batch.copy())
                    batch.clear()
                    return True
            return False

        def candidates():
            for raw in self.paths:
                if self.cancelled.is_set():
                    return
                path = Path(raw)
                if path.is_dir():
                    for directory, _, names in os.walk(path):
                        if self.cancelled.is_set():
                            return
                        for name in names:
                            yield Path(directory) / name
                else:
                    yield path

        try:
            locale = QLocale()
            for path in candidates():
                if self.cancelled.is_set():
                    break
                if path.suffix.lower() not in self.extensions:
                    skipped += 1
                    continue
                try:
                    path = path.resolve()
                    info = path.stat()
                    value = str(path)
                    if not stat.S_ISREG(info.st_mode) or value in seen:
                        continue
                    seen.add(value)
                    batch.append((value, path.name, locale.formattedDataSize(info.st_size, 1)))
                except OSError as exc:
                    if len(errors) < 20:
                        errors.append(str(exc))
                if len(batch) >= 128 and not send():
                    break
            if batch and not self.cancelled.is_set():
                send()
        except Exception as exc:
            errors.append(str(exc))
        finally:
            self.signals.finished.emit(self, skipped, '\n'.join(errors))
