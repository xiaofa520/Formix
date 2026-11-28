"""Opt-in CI observation of a real packaged GUI and its update action."""
import hashlib
import json
import os
from pathlib import Path
from PySide6.QtCore import QTimer


def capture_settings(window, folder):
    from PySide6.QtCore import QPoint, Qt
    from PySide6.QtGui import QPainter
    from PySide6.QtTest import QTest

    scroll = window.settings_scroll
    bar = scroll.verticalScrollBar()
    bar.setValue(0)
    section = 1
    while bar.value() < bar.maximum():
        bar.setValue(min(bar.maximum(), bar.value() + max(1, scroll.viewport().height() - 60)))
        QTest.qWait(100)
        section += 1
        if not window.grab().save(str(folder / f'settings-scroll-{section:02}.png')):
            raise RuntimeError('Could not save settings screenshot')

    for name, combo in [('models', window.model_combo), ('language', window.language_combo),
                        ('acceleration', window.video_acceleration_combo)]:
        scroll.ensureWidgetVisible(combo)
        QTest.qWait(180)
        QTest.mouseClick(combo, Qt.MouseButton.LeftButton)
        QTest.qWait(200)
        view = combo.view()
        if not view.isVisible() or combo.count() == 0:
            raise RuntimeError(f'{name} dropdown did not open with choices')
        # Qt owns the popup as a separate window. Include it in the application image.
        popup = view.window()
        shot = window.grab()
        painter = QPainter(shot)
        painter.drawPixmap(window.mapFromGlobal(popup.mapToGlobal(QPoint())), popup.grab())
        painter.end()
        if not shot.save(str(folder / f'settings-dropdown-{name}.png')):
            raise RuntimeError(f'Could not save {name} dropdown')
        QTest.keyClick(view, Qt.Key.Key_Escape)
        QTest.qWait(100)
        if view.isVisible():
            raise RuntimeError(f'{name} dropdown did not close')
    bar.setValue(0)


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
            if command.get('verify_payload'):
                import subprocess, sys
                subprocess.run([sys.executable, '-I', command['verify_payload'], 'verify', str(root)], check=True, timeout=300)
                subprocess.run([sys.executable, '-I', command['verify_runtime'], sys.executable], check=True, timeout=240)
            settings = window.language.settings
            model = window.model_root / 'ci-retention-fixture' / 'weights.bin'
            if command['phase'] == 'seed':
                settings.setValue('ci/retention', 'keep-this-setting')
                settings.sync()
                model.parent.mkdir(parents=True, exist_ok=True)
                model.write_bytes(b'Formix CI model preservation fixture\n' * 1024)
            state = dict(pid=os.getpid(), root=str(root), version=version,
                         appimage=os.environ.get('APPIMAGE'),
                         setting=settings.value('ci/retention'), settings_file=settings.fileName(), model=str(model),
                         model_hash=hashlib.sha256(model.read_bytes()).hexdigest() if model.is_file() else None,
                         visible=window.isVisible(), exposed=window.windowHandle().isExposed())
            destination = Path(command['report'])
            if command['phase'] == 'verify' and command.get('screenshots'):
                from PySide6.QtTest import QTest
                from PySide6.QtWidgets import QMessageBox
                folder = Path(command['screenshots'])
                folder.mkdir(exist_ok=True)
                for index in range(window.stack.count()):
                    if index < len(window.pages):
                        page = window.pages[index]
                        name = page.name
                        window.category_buttons.button(window.page_categories[page]).click()
                    else:
                        name = '设置'
                    window.page_buttons.button(index).click()
                    QTest.qWait(350)
                    for dialog in window.findChildren(QMessageBox):
                        if dialog.isVisible():
                            dialog.reject()
                    app.processEvents()
                    path = folder / f'{index + 1:02d}-{name}.png'
                    if window.stack.currentIndex() != index or not window.grab().save(str(path), 'PNG'):
                        raise RuntimeError(f'Could not capture page: {path}')
                    if index == window.settings_index:
                        capture_settings(window, folder)
            temporary = destination.with_suffix('.tmp')
            temporary.write_text(json.dumps(state), encoding='utf-8')
            temporary.replace(destination)
            reported = True
        if command.get('download_asset'):
            from unittest.mock import patch
            from formix import engine_update
            asset = command.pop('download_asset')
            directory = engine_update.cache_folder('app', engine_update.SLUG, asset['version'])
            release = {'tag_name': 'v' + asset['version'], 'assets': [{
                'name': asset['name'], 'size': asset['size'], 'digest': asset['digest'],
                'browser_download_url': asset['url']}]}
            with patch.object(engine_update, 'latest_release', return_value=release):
                command['update'] = engine_update.fetch(asset['version'], directory)
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
            app.exit(1)
    timer.timeout.connect(guarded_poll)
    timer.start()
