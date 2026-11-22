"""Replace damaged model folders without destroying a working installation."""
from pathlib import Path
import tempfile
from PySide6.QtCore import QLockFile


def publish_model(staged, target):
    staged, target = Path(staged), Path(target)
    if not (staged / 'READY').is_file():
        raise ValueError('Model download is not ready')
    lock = QLockFile(str(target.parent / ('.' + target.name + '.lock')))
    lock.setStaleLockTime(0)
    if not lock.tryLock(0):
        raise RuntimeError('Another model operation is in progress')
    backup = None
    try:
        if (target / 'READY').is_file():
            return None
        if target.exists() or target.is_symlink():
            backup = Path(tempfile.mkdtemp(dir=target.parent, prefix='.retired-'))
            target.rename(backup / 'model')
        try:
            staged.rename(target)
        except OSError:
            if backup:
                (backup / 'model').rename(target)
                backup.rmdir()
            raise
        return backup
    finally:
        lock.unlock()
