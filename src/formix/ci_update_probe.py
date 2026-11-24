"""Opt-in CI observation of a real packaged GUI and its update action."""
import hashlib
import json
import os
from pathlib import Path
from PySide6.QtCore import QTimer


def attach(app, window, root, version):
    if os.environ.get('GITHUB_ACTIONS') != 'true' or not os.environ.get('FORMIX_CI_CONTROL'):
        return
    control = Path(os.environ['FORMIX_CI_CONTROL'])
    timer = QTimer(window)
    timer.setInterval(500)
    reported = False

    def poll():
        nonlocal reported
        if not window.isVisible() or window.windowHandle() is None or not window.windowHandle().isExposed():
            return
        command = json.loads(control.read_text(encoding='utf-8'))
        if not reported:
            settings = window.language.settings
            model = window.model_root / 'ci-retention-fixture' / 'weights.bin'
            if command['phase'] == 'seed':
                settings.setValue('ci/retention', 'keep-this-setting')
                settings.sync()
                model.parent.mkdir(parents=True, exist_ok=True)
                model.write_bytes(b'Formix CI model preservation fixture\n' * 1024)
            state = dict(pid=os.getpid(), root=str(root), version=version,
                         appimage=os.environ.get('APPIMAGE'),
                         setting=settings.value('ci/retention'), model=str(model),
                         model_hash=hashlib.sha256(model.read_bytes()).hexdigest() if model.is_file() else None,
                         visible=window.isVisible(), exposed=window.windowHandle().isExposed())
            destination = Path(command['report'])
            temporary = destination.with_suffix('.tmp')
            temporary.write_text(json.dumps(state), encoding='utf-8')
            temporary.replace(destination)
            reported = True
        if command.get('update'):
            timer.stop()
            archive = command.pop('update')
            temporary = control.with_suffix('.probe.tmp')
            temporary.write_text(json.dumps(command), encoding='utf-8')
            temporary.replace(control)
            if not window.app_update_row.launch_app_update(Path(archive)):
                raise RuntimeError('Update launch failed: ' + window.app_update_row.note.text() + ' ' + window.app_update_row.note.toolTip())
        elif command.get('close'):
            timer.stop()
            window.close()
    def guarded_poll():
        try:
            poll()
        except Exception:
            import traceback
            timer.stop()
            failure = control.with_suffix('.error')
            failure.write_text(traceback.format_exc(), encoding='utf-8')
    timer.timeout.connect(guarded_poll)
    timer.start()
