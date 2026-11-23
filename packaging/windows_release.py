"""Build the directory-mode Windows release using the preserved installer template."""
import argparse
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys


def run(*args, **kwargs):
    subprocess.run([str(arg) for arg in args], check=True, **kwargs)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('version')
    args = parser.parse_args()
    if not re.fullmatch(r'\d+\.\d+\.\d+', args.version):
        parser.error('Expected MAJOR.MINOR.PATCH')
    root = Path(__file__).resolve().parents[1]
    template = root / 'packaging/windows-release'
    work = root / 'build/windows-release-ci'
    if work.exists():
        raise SystemExit(f'Build directory already exists: {work}')
    shutil.copytree(template, work)
    version_file = work / 'version.txt'
    version_file.write_text(version_file.read_text(encoding='utf-8')
                            .replace('(1,2,9,0)', '(' + args.version.replace('.', ',') + ',0)')
                            .replace('1.2.9', args.version), encoding='utf-8')
    run(sys.executable, '-m', 'PyInstaller', '--noconfirm', '--distpath', work,
        '--workpath', work / 'pyinstaller-work', work / 'Formix.spec', cwd=work)
    app = work / 'Formix'
    staged = root / 'build/windows-x64-app'
    shutil.copytree(staged, app, dirs_exist_ok=True)
    runtime = app / 'runtime'
    (app / 'python').rename(runtime)
    shutil.copy2(work / 'launcher-stage.py', app / 'formix/launcher.py')
    run(work / 'native/build_host.cmd', runtime, 'x64', args.version,
        runtime / 'Formix.exe', cwd=work)
    # Compile with the shipped interpreter; retain dependency sources, but not application sources.
    interpreter = runtime / 'python.exe'
    run(interpreter, '-m', 'compileall', '-q', '-b', '-f', app / 'formix', app / 'main.py')
    for source in [app / 'main.py', *(app / 'formix').rglob('*.py')]:
        if not source.with_suffix('.pyc').is_file():
            raise RuntimeError(f'Missing compiled application module: {source}')
        source.unlink()
    for name in ('python.exe', 'pythonw.exe'):
        (runtime / name).unlink(missing_ok=True)
    environment = os.environ.copy()
    environment['QT_QPA_PLATFORM'] = 'offscreen'
    run(runtime / 'Formix.exe', '-I', root / 'packaging/smoke.py', app, env=environment)
    shutil.copy2(root / 'build/vc_redist.x64.exe', work / 'vc_redist.x64.exe')
    compiler = shutil.which('ISCC') or str(Path(os.environ['ProgramFiles(x86)']) / 'Inno Setup 6/ISCC.exe')
    run(compiler, f'/DVersion={args.version}', '/DBuildArch=x64', f'/O{root / "dist"}', work / 'install.iss')
    output = root / f'dist/formix-win-64-v{args.version}.exe'
    if not output.is_file():
        raise RuntimeError(f'Missing installer: {output}')
    print(f'Windows installer ready: {output}', flush=True)


if __name__ == '__main__':
    main()
