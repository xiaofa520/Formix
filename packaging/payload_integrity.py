"""Inventory the distributable tree and verify installed files and symlinks."""
import argparse
import hashlib
import json
import os
from pathlib import Path

MANIFEST = 'payload-manifest.json'
USER_DIRS = {'models', 'cache', 'logs', 'output'}

def digest(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()

def snapshot(root):
    root = Path(root)
    entries = {}
    for base, dirs, files in os.walk(root, followlinks=False):
        base = Path(base)
        dirs[:] = [n for n in dirs if n != '__pycache__' and not (base == root and n in USER_DIRS)]
        for name in [*dirs, *files]:
            path = base / name
            relative = path.relative_to(root).as_posix()
            if relative in {MANIFEST, 'release.txt'} or '__pycache__' in path.relative_to(root).parts:
                continue
            if path.is_symlink():
                entries[relative] = {'link': os.readlink(path)}
            elif path.is_file():
                entries[relative] = {'size': path.stat().st_size, 'sha256': digest(path)}
    return entries

def write(root):
    root = Path(root)
    entries = snapshot(root)
    (root / MANIFEST).write_text(json.dumps(entries, ensure_ascii=False, sort_keys=True), encoding='utf-8')
    print(f'Payload inventory: {len(entries)} files/links', flush=True)

def verify(root):
    root = Path(root)
    entries = json.loads((root / MANIFEST).read_text(encoding='utf-8'))
    if not entries:
        raise ValueError('Empty payload inventory')
    problems = []
    for relative, expected in entries.items():
        path = root / relative
        if Path(relative).is_absolute() or '..' in Path(relative).parts:
            raise ValueError('Unsafe inventory path')
        # The installer chooses the private executable's name by language.
        if relative == 'runtime/Formix.exe' and not path.exists():
            path = root / 'runtime/格式转换通.exe'
        if 'link' in expected:
            valid = path.is_symlink() and os.readlink(path) == expected['link']
        else:
            valid = (not path.is_symlink() and path.is_file() and
                     path.stat().st_size == expected['size'] and digest(path) == expected['sha256'])
        if not valid:
            problems.append(relative)
    if problems:
        raise RuntimeError('Payload missing or changed: ' + ', '.join(problems[:30]))
    print(f'Payload integrity PASS: {len(entries)} files/links', flush=True)

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('action', choices=['write', 'verify'])
    parser.add_argument('root', type=Path)
    args = parser.parse_args()
    (write if args.action == 'write' else verify)(args.root)
