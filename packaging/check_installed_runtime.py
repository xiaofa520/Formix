"""Exercise pip from the installed runtime without network or system changes."""
import argparse
import csv
import io
from pathlib import Path
import subprocess
import tempfile
import zipfile

def check(interpreter):
    interpreter = Path(interpreter).resolve()
    subprocess.run([str(interpreter), '-I', '-m', 'pip', '--version'], check=True, timeout=60)
    with tempfile.TemporaryDirectory(prefix='formix-pip-check-') as temp:
        folder = Path(temp)
        wheel = folder / 'formix_ci_dependency-1.0-py3-none-any.whl'
        metadata = 'formix_ci_dependency-1.0.dist-info/'
        files = {'formix_ci_dependency.py': 'VALUE = "installed successfully"\n',
                 metadata + 'METADATA': 'Metadata-Version: 2.1\nName: formix-ci-dependency\nVersion: 1.0\n',
                 metadata + 'WHEEL': 'Wheel-Version: 1.0\nGenerator: Formix CI\nRoot-Is-Purelib: true\nTag: py3-none-any\n'}
        record = io.StringIO()
        writer = csv.writer(record)
        for name in [*files, metadata + 'RECORD']:
            writer.writerow([name, '', ''])
        files[metadata + 'RECORD'] = record.getvalue()
        with zipfile.ZipFile(wheel, 'w') as archive:
            for name, value in files.items():
                archive.writestr(name, value)
        target = folder / 'installed dependency'
        subprocess.run([str(interpreter), '-I', '-u', '-X', 'utf8', '-m', 'pip', '--isolated',
                        'install', '--no-index', '--no-deps', '--no-cache-dir', '--progress-bar', 'raw',
                        '--target', str(target), str(wheel)], check=True, timeout=120)
        subprocess.run([str(interpreter), '-I', '-c',
                        'import sys; sys.path.insert(0,sys.argv[1]); import formix_ci_dependency; '
                        'assert formix_ci_dependency.VALUE == "installed successfully"', str(target)],
                       check=True, timeout=60)
    print('Installed pip and offline dependency install/import PASS', flush=True)

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('interpreter')
    check(parser.parse_args().interpreter)
