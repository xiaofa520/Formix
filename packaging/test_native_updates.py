"""Install native artifacts and exercise the installed GUI's update action in CI."""
import argparse
import json
import os
from pathlib import Path
import platform
import subprocess
import time

ROOT = Path(__file__).resolve().parents[1]


def run(*args, **kwargs):
    return subprocess.run([str(x) for x in args], check=True, **kwargs)


def wait_report(path, timeout=900):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if path.is_file():
            state = json.loads(path.read_text(encoding='utf-8'))
            assert state['visible'] and state['exposed'], state
            return state
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
    assert launcher.is_file() and (installed / 'release.txt').is_file()
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
            before = wait_report(before_path, 180)
            assert before['version'] == '0.0.0'
            assert before['setting'] == 'keep-this-setting' and before['model_hash']
            write_control(control, {'phase': 'verify', 'report': str(after_path), 'update': str(package)})
            after = wait_report(after_path)
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


if __name__ == '__main__':
    main()
