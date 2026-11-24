"""Linux-only CI integration: install real packages, update, and reopen the GUI."""
import argparse
import hashlib
import importlib.util
import os
from pathlib import Path
import shutil
import signal
import subprocess
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]


def run(*args, **kwargs):
    return subprocess.run([str(a) for a in args], check=True, **kwargs)


def digest(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def wait_window(process, env, output):
    deadline = time.monotonic() + 90
    while time.monotonic() < deadline:
        found = subprocess.run(['xdotool', 'search', '--onlyvisible', '--name', '^Formix$'],
                               env=env, capture_output=True, text=True)
        if found.returncode == 0 and found.stdout.strip():
            window = found.stdout.splitlines()[0]
            run('xdotool', 'getwindowgeometry', window, env=env, stdout=output)
            return
        if process.poll() is not None and process.returncode != 0:
            raise RuntimeError(f'GUI/updater exited: {process.returncode}')
        time.sleep(1)
    raise TimeoutError('Formix window did not become visible within 90 seconds')


def stop(process):
    try:
        os.killpg(process.pid, signal.SIGTERM)
    except ProcessLookupError:
        pass
    try:
        process.wait(timeout=15)
    except subprocess.TimeoutExpired:
        os.killpg(process.pid, signal.SIGKILL)
        process.wait()


def exercise(kind, launcher, installed_root, archive, env, evidence):
    profile = Path(env['HOME'])
    config = Path(env['XDG_CONFIG_HOME']) / 'Formix/Formix.conf'
    config.parent.mkdir(parents=True, exist_ok=True)
    config.write_text('[interface]\nlanguage=en\n[ci]\nkeep=preserved-setting\n', encoding='utf-8')
    model_roots = [Path(env['XDG_DATA_HOME']) / 'Formix/Formix/models/ci-preserve']
    if kind == 'deb':
        model_roots.append(installed_root / 'models/ci-preserve')
    for folder in model_roots:
        folder.mkdir(parents=True, exist_ok=True)
        (folder / 'weights.bin').write_bytes(os.urandom(8192))
        (folder / 'config.json').write_text('{"ci": true}')
    retained = {p: digest(p) for folder in model_roots for p in folder.iterdir()}
    spec = importlib.util.spec_from_file_location('formix_ci_updater', installed_root / 'formix/app_updater.py')
    updater = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(updater)
    log = (evidence / f'{kind}.log').open('w')
    old = subprocess.Popen([str(launcher)], env=env, stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
    process = None
    script = None
    try:
        wait_window(old, env, log)
        script = updater.prepare_linux_package_update(archive, installed_root, old.pid,
                                                      str(launcher) if kind == 'appimage' else None)
        process = subprocess.Popen(['/bin/sh', str(script)], env=env, stdout=log,
                                   stderr=subprocess.STDOUT, start_new_session=True)
        # The updater must wait while the original application is still running.
        time.sleep(2)
        assert process.poll() is None, 'Updater did not wait for the old application'
        stop(old)
        assert process.wait(timeout=1200) == 0, (script.parent / 'updater.log').read_text()
        wait_window(process, env, log)
        for path, expected in retained.items():
            assert path.is_file() and digest(path) == expected, f'Model changed: {path}'
        assert 'preserved-setting' in config.read_text(), 'Saved settings were lost'
        assert launcher.is_file(), 'Original installation path disappeared'
        shutil.copy2(script.parent / 'updater.log', evidence / f'{kind}-updater.log')
        print(f'{kind}: initial launch, actual upgrade, GUI restart, settings and models PASS', flush=True)
    finally:
        if script is not None and (script.parent / 'updater.log').is_file():
            shutil.copy2(script.parent / 'updater.log', evidence / f'{kind}-updater.log')
        stop(old)
        if process is not None:
            stop(process)
        log.close()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('version')
    args = parser.parse_args()
    assert os.geteuid() == 0, 'Run in the disposable CI runner with sudo'
    evidence = ROOT / 'build/linux-update-test-logs'
    evidence.mkdir(parents=True, exist_ok=True)
    dist = ROOT / 'dist'
    deb = next(dist.glob('*.deb'))
    appimage = next(dist.glob('*.AppImage'))
    work = ROOT / 'build/linux-packages'
    with tempfile.TemporaryDirectory(prefix='formix-ci-upgrade-') as temp:
        temp = Path(temp)
        env = os.environ.copy()
        env.update(HOME=str(temp / 'home'), XDG_CONFIG_HOME=str(temp / 'home/config'),
                   XDG_DATA_HOME=str(temp / 'home/data'), XDG_CACHE_HOME=str(temp / 'home/cache'),
                   XDG_STATE_HOME=str(temp / 'home/state'), XDG_RUNTIME_DIR=str(temp / 'runtime'),
                   QT_QPA_PLATFORM='xcb', QTWEBENGINE_DISABLE_SANDBOX='1', APPIMAGE_EXTRACT_AND_RUN='1')
        Path(env['HOME']).mkdir()
        Path(env['XDG_RUNTIME_DIR']).mkdir(mode=0o700)
        # Build an actual older package from the same payload, then upgrade its version.
        control = work / 'deb/DEBIAN/control'
        original = control.read_text()
        olddeb = temp / 'old.deb'
        try:
            control.write_text(original.replace(f'Version: {args.version}\n', 'Version: 0.0.0\n'))
            run('dpkg-deb', '--root-owner-group', '-Zgzip', '--build', work / 'deb', olddeb)
        finally:
            control.write_text(original)
        run('apt-get', '-y', '--no-remove', 'install', olddeb, env={**env, 'DEBIAN_FRONTEND': 'noninteractive'})
        assert subprocess.check_output(['dpkg-query', '-W', '-f=${Version}', 'formix'], text=True) == '0.0.0'
        exercise('deb', Path('/opt/formix/Formix'), Path('/opt/formix'), deb, env, evidence)
        assert subprocess.check_output(['dpkg-query', '-W', '-f=${Version}', 'formix'], text=True) == args.version
        # Build a real older AppImage; test replacement at a path containing spaces.
        appdir = work / 'Formix.AppDir'
        release = appdir / 'usr/lib/formix/release.txt'
        current = release.read_text()
        oldimage = temp / 'Formix original.AppImage'
        try:
            release.write_text('0.0.0')
            run(work / 'appimagetool.AppImage', appdir, oldimage,
                env={**env, 'ARCH': os.uname().machine, 'VERSION': '0.0.0'})
        finally:
            release.write_text(current)
        before = digest(oldimage)
        exercise('appimage', oldimage, appdir / 'usr/lib/formix', appimage, env, evidence)
        assert digest(oldimage) == digest(appimage) and digest(oldimage) != before
        print('Both package update integration tests passed', flush=True)


if __name__ == '__main__':
    main()
