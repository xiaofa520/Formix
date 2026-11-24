"""Linux-only CI integration: install real packages, update, and reopen the GUI."""
import argparse
import hashlib
import functools
import http.server
import threading
import urllib.parse
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


def exercise(kind, launcher, installed_root, archive, env, evidence, version):
    from test_native_updates import wait_report, write_control
    control = evidence / f'{kind}-control.json'
    before_path, after_path = evidence / f'{kind}-before.json', evidence / f'{kind}-after.json'
    before_path.unlink(missing_ok=True)
    after_path.unlink(missing_ok=True)
    control.with_suffix('.error').unlink(missing_ok=True)
    environment = {**env, 'FORMIX_CI_CONTROL': str(control)}
    download = evidence.parent / f'{kind}-update-download'
    download.mkdir(exist_ok=True)
    package = download / archive.name
    shutil.copy2(archive, package)
    checks = {'verify_payload': str(ROOT / 'packaging/payload_integrity.py'),
              'verify_runtime': str(ROOT / 'packaging/check_installed_runtime.py')}
    write_control(control, {'phase': 'seed', 'report': str(before_path), **checks})
    log = (evidence / f'{kind}.log').open('w')
    old = subprocess.Popen([str(launcher)], env=environment, stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
    after = None
    server = http.server.ThreadingHTTPServer(('127.0.0.1', 0), functools.partial(
        http.server.SimpleHTTPRequestHandler, directory=str(download)))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        before = wait_report(before_path, 600, control, old)
        assert before['version'] == '0.0.0', before
        assert before['setting'] == 'keep-this-setting' and before['model_hash']
        write_control(control, {'phase': 'verify', 'report': str(after_path), **checks, 'download_asset': {
            'name': package.name, 'version': version, 'size': package.stat().st_size,
            'digest': 'sha256:' + digest(package),
            'url': f'http://127.0.0.1:{server.server_port}/' + urllib.parse.quote(package.name)}})
        after = wait_report(after_path, 1200, control, old)
        assert after['pid'] != before['pid']
        assert after['version'] == version, after
        for key in ('setting', 'settings_file', 'model', 'model_hash'):
            assert before[key] == after[key], f'{kind}: {key} changed'
        if kind == 'deb':
            assert Path(after['root']).resolve() == installed_root.resolve()
        else:
            assert not Path(before['model']).is_relative_to(Path(before['root']))
            assert not Path(before['settings_file']).is_relative_to(Path(before['root']))
            assert Path(before['appimage']).resolve() == launcher.resolve()
            assert Path(after['appimage']).resolve() == launcher.resolve()
            assert digest(launcher) == digest(archive)
        print(f'{kind}: installed GUI update, restart, original path, settings and models PASS', flush=True)
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
        write_control(control, {'phase': 'verify', 'report': str(after_path), 'close': True})
        time.sleep(3)
        stop(old)
        if after is not None:
            try:
                os.kill(after['pid'], signal.SIGTERM)
            except ProcessLookupError:
                pass
        log.close()
        print((evidence / f'{kind}.log').read_text(errors='replace')[-12000:], flush=True)
        app_logs = Path(env['XDG_DATA_HOME']) / 'Formix/logs'
        for path in app_logs.glob('*.log'):
            shutil.copy2(path, evidence / (kind + '-' + path.name))
            print(path.read_text(errors='replace')[-12000:], flush=True)
        for path in Path(env['XDG_CACHE_HOME']).rglob('updater.log'):
            shutil.copy2(path, evidence / (kind + '-' + path.parent.name + '-' + path.name))
        for path in download.rglob('*.log'):
            shutil.copy2(path, evidence / (kind + '-' + path.parent.name + '-' + path.name))
        package.unlink(missing_ok=True)


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
        payload_version = work / 'deb/opt/formix/release.txt'
        original_version = payload_version.read_text()
        olddeb = temp / 'old.deb'
        try:
            payload_version.write_text('0.0.0')
            control.write_text(original.replace(f'Version: {args.version}\n', 'Version: 0.0.0\n'))
            run('dpkg-deb', '--root-owner-group', '-Zgzip', '--build', work / 'deb', olddeb)
        finally:
            control.write_text(original)
            payload_version.write_text(original_version)
        run('apt-get', '-y', '--no-remove', 'install', olddeb, env={**env, 'DEBIAN_FRONTEND': 'noninteractive'})
        assert subprocess.check_output(['dpkg-query', '-W', '-f=${Version}', 'formix'], text=True) == '0.0.0'
        olddeb.unlink()
        exercise('deb', Path('/opt/formix/Formix'), Path('/opt/formix'), deb, env, evidence, args.version)
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
        exercise('appimage', oldimage, appdir / 'usr/lib/formix', appimage, env, evidence, args.version)
        assert digest(oldimage) == digest(appimage) and digest(oldimage) != before
        print('Both package update integration tests passed', flush=True)


if __name__ == '__main__':
    main()
