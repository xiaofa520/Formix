"""Install native artifacts and exercise the installed GUI's update action in CI."""
import argparse
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import time

ROOT = Path(__file__).resolve().parents[1]


def run(*args, **kwargs):
    return subprocess.run([str(x) for x in args], check=True, **kwargs)


def wait_report(path, timeout=900, control=None, process=None):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        # Reap the old launcher after it exits; kill -0 otherwise sees a zombie
        # and the detached Unix updater waits forever for it.
        exit_code = process.poll() if process is not None else None
        if control is not None and control.with_suffix('.error').is_file():
            raise RuntimeError(control.with_suffix('.error').read_text(encoding='utf-8'))
        if path.is_file():
            state = json.loads(path.read_text(encoding='utf-8'))
            assert state['visible'] and state['exposed'], state
            return state
        if exit_code not in (None, 0):
            raise RuntimeError(f'Application exited before reporting its window: {process.returncode}')
        time.sleep(1)
    raise TimeoutError(f'Installed application did not report a visible, responsive window: {path}')


def write_control(path, command):
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(command), encoding='utf-8')
    temporary.replace(path)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('version')
    args = parser.parse_args()
    assert os.environ.get('GITHUB_ACTIONS') == 'true', 'Only run on disposable GitHub runners'
    system = platform.system()
    evidence = ROOT / 'build/native-update-test-logs'
    evidence.mkdir(parents=True, exist_ok=True)
    control = evidence / 'control.json'
    before_path, after_path = evidence / 'before.json', evidence / 'after.json'
    for path in (before_path, after_path, control.with_suffix('.error')):
        path.unlink(missing_ok=True)
    environment = os.environ.copy()
    environment['FORMIX_CI_CONTROL'] = str(control)
    if system == 'Windows':
        package = next((ROOT / 'dist').glob('*.exe'))
        installed = Path(os.environ['RUNNER_TEMP']) / 'Formix custom installation'
        run(package, '/VERYSILENT', '/SUPPRESSMSGBOXES', '/NORESTART', '/SP-', '/LANG=en',
            '/DIR=' + str(installed), '/LOG=' + str(evidence / 'initial-install.log'))
        launcher = installed / 'Formix.exe'
    elif system == 'Darwin':
        package = next((ROOT / 'dist').glob('*.pkg'))
        with (evidence / 'initial-install.log').open('w') as output:
            run('sudo', '-n', '/usr/sbin/installer', '-pkg', package, '-target', '/', stdout=output, stderr=subprocess.STDOUT)
        installed = Path('/Applications/Formix.app/Contents/Resources')
        launcher = Path('/Applications/Formix.app/Contents/MacOS/Formix')
    else:
        raise RuntimeError('Use test_linux_updates.py on Linux')
    download = ROOT / 'build/native-update-download'
    download.mkdir(exist_ok=True)
    shutil.copy2(package, download / package.name)
    package = download / package.name
    missing = [str(p) for p in (launcher, installed / 'release.txt') if not p.is_file()]
    if missing:
        if system == 'Darwin':
            with (evidence / 'install-path-diagnostics.log').open('w') as output:
                for command in (['pkgutil', '--pkg-info', 'org.formix.desktop'],
                                ['pkgutil', '--files', 'org.formix.desktop'],
                                ['find', '/Applications', str(ROOT / 'build'), '-name', 'Formix.app', '-print']):
                    subprocess.run(command, stdout=output, stderr=subprocess.STDOUT, check=False)
            print((evidence / 'initial-install.log').read_text(), flush=True)
        raise RuntimeError('Installer returned success but required files are missing: ' + ', '.join(missing))
    # Construct an older on-disk state using this release's real installer.
    # This tests installation/replacement, not compatibility with historical releases.
    if system == 'Darwin':
        run('sudo', '-n', 'tee', installed / 'release.txt', input=b'0.0.0', stdout=subprocess.DEVNULL)
    else:
        (installed / 'release.txt').write_text('0.0.0')
    write_control(control, {'phase': 'seed', 'report': str(before_path)})
    with (evidence / 'application.log').open('w') as output:
        process = subprocess.Popen([str(launcher)], env=environment, stdout=output, stderr=subprocess.STDOUT)
        try:
            before = wait_report(before_path, 180, control, process)
            assert before['version'] == '0.0.0'
            assert before['setting'] == 'keep-this-setting' and before['model_hash']
            write_control(control, {'phase': 'verify', 'report': str(after_path), 'update': str(package)})
            after = wait_report(after_path, control=control, process=process)
            assert after['pid'] != before['pid'], 'Old application was not replaced and restarted'
            assert after['version'] == args.version, after
            for key in ('root', 'setting', 'model', 'model_hash'):
                assert before[key] == after[key], f'{key} was not preserved: {before} -> {after}'
            assert Path(after['root']).resolve() == installed.resolve(), 'Installation location changed'
            print(f'{system}: real installation, GUI update, restart, original path, settings and model retention PASS', flush=True)
        finally:
            write_control(control, {'phase': 'verify', 'report': str(after_path), 'close': True})
            # Graceful exit lets settings flush and the single-instance lock release.
            try:
                process.wait(timeout=30)
            except subprocess.TimeoutExpired:
                process.terminate()
            time.sleep(3)
            for path in download.rglob('*.log'):
                shutil.copy2(path, evidence / (path.parent.name + '-' + path.name))
            if system == 'Darwin':
                updater_log = Path.home() / 'Library/Logs/Formix/logs/updater.log'
                if updater_log.is_file():
                    shutil.copy2(updater_log, evidence / 'updater.log')
            output.flush()
            print((evidence / 'application.log').read_text(errors='replace')[-12000:], flush=True)
            package.unlink(missing_ok=True)


if __name__ == '__main__':
    main()
