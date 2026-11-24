"""Build installable Linux packages from the staged portable application."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import urllib.request


def run(*args, **kwargs):
    subprocess.run([str(x) for x in args], check=True, **kwargs)


def write(path, content, executable=False):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding='utf-8')
    if executable:
        path.chmod(0o755)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('app', type=Path)
    parser.add_argument('version')
    args = parser.parse_args()
    app = args.app.resolve()
    arch = platform.machine()
    debarch, label = {'x86_64': ('amd64', '64'), 'aarch64': ('arm64', 'arm64')}[arch]
    root = Path(__file__).resolve().parents[1]
    work = root / 'build/linux-packages'
    work.mkdir(exist_ok=False)
    dist = root / 'dist'
    desktop = ('[Desktop Entry]\nType=Application\nName=Formix\nName[zh_CN]=格式转换通\n'
               'Comment=Video, audio, image and document converter\nExec=formix\n'
               'Icon=formix\nTerminal=false\nCategories=AudioVideo;Graphics;Office;\n')
    deb = work / 'deb'
    shutil.copytree(app, deb / 'opt/formix', symlinks=True)
    write(deb / 'opt/formix/package-format', 'deb\n')
    write(deb / 'usr/bin/formix', '#!/bin/sh\nexec /opt/formix/Formix "$@"\n', True)
    write(deb / 'usr/share/applications/formix.desktop', desktop)
    icon = deb / 'usr/share/icons/hicolor/256x256/apps/formix.png'
    icon.parent.mkdir(parents=True)
    run(app / 'python/bin/python3.11', '-I', '-c',
        'from PIL import Image; import sys; im=Image.open(sys.argv[1]); im.thumbnail((256,256)); im.save(sys.argv[2])',
        app / 'formix/assets/logo1.png', icon)
    dependencies = ('libc6 (>= 2.35), libstdc++6, libegl1, libgl1, libopengl0, libglib2.0-0, '
                    'libdbus-1-3, libfontconfig1, libfreetype6, libx11-6, libx11-xcb1, libxext6, '
                    'libxrender1, libxi6, libxkbcommon0, libxkbcommon-x11-0, libxcb1, libxcb-cursor0, '
                    'libxcb-icccm4, libxcb-image0, libxcb-keysyms1, libxcb-randr0, libxcb-render0, '
                    'libxcb-render-util0, libxcb-shape0, libxcb-shm0, libxcb-sync1, libxcb-xfixes0, '
                    'libxcb-xkb1, libsm6, libice6, libxinerama1, libcups2, libcairo2, libnss3, '
                    'libnspr4, libdbus-glib-1-2, libgomp1, libasound2 | libasound2t64')
    size = sum(p.stat().st_size for p in (deb / 'opt').rglob('*') if p.is_file()) // 1024
    write(deb / 'DEBIAN/control', f'Package: formix\nVersion: {args.version}\nArchitecture: {debarch}\n'
          f'Maintainer: xiaofa520 <xiaofa520@users.noreply.github.com>\nInstalled-Size: {size}\n'
          f'Section: utils\nPriority: optional\nDepends: {dependencies}\n'
          'Description: Formix desktop format converter\n Includes a private Python runtime and conversion engines.\n')
    output = dist / f'formix-linux-{label}-v{args.version}.deb'
    run('dpkg-deb', '--root-owner-group', '-Zxz', '--build', deb, output)
    run('dpkg-deb', '--info', output)
    appdir = work / 'Formix.AppDir'
    shutil.copytree(app, appdir / 'usr/lib/formix', symlinks=True)
    write(appdir / 'usr/lib/formix/package-format', 'appimage\n')
    write(appdir / 'formix.desktop', desktop)
    shutil.copy2(icon, appdir / 'formix.png')
    shutil.copy2(icon, appdir / '.DirIcon')
    write(appdir / 'AppRun', '#!/bin/sh\nroot="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"\n'
          'export LD_LIBRARY_PATH="$root/usr/lib/compat${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"\n'
          'exec "$root/usr/lib/formix/Formix" "$@"\n', True)
    # Include Qt/X11 dependencies, leaving glibc and graphics drivers to the host.
    import re
    compat = appdir / 'usr/lib/compat'
    compat.mkdir()
    skip = re.compile(r'^(ld-linux|lib(c|m|pthread|dl|rt|resolv|util|anl)\.so|lib(GL|EGL|drm|gbm))')
    qt = app / 'python/lib/python3.11/site-packages/PySide6/Qt'
    for folder in (qt / 'lib', qt / 'plugins'):
        for binary in folder.rglob('*.so*'):
            if not binary.is_file():
                continue
            result = subprocess.run(['ldd', str(binary)], capture_output=True, text=True)
            for name, path in re.findall(r'^\s*(\S+) => (/\S+)', result.stdout, re.M):
                source = Path(path)
                if not skip.match(name) and not source.resolve().is_relative_to(app) and not (compat / name).exists():
                    shutil.copy2(source, compat / name)
    request = urllib.request.Request('https://api.github.com/repos/AppImage/appimagetool/releases/latest',
                                     headers={'User-Agent': 'Formix-build'})
    with urllib.request.urlopen(request, timeout=60) as response:
        release = json.load(response)
    asset = next(a for a in release['assets'] if a['name'] == f'appimagetool-{arch}.AppImage')
    tool = work / 'appimagetool.AppImage'
    with urllib.request.urlopen(asset['browser_download_url'], timeout=120) as response, tool.open('wb') as stream:
        shutil.copyfileobj(response, stream)
    digest = asset.get('digest', '')
    if not digest.startswith('sha256:') or hashlib.sha256(tool.read_bytes()).hexdigest() != digest[7:]:
        raise RuntimeError('AppImage build tool checksum verification failed')
    tool.chmod(0o755)
    environment = os.environ.copy()
    environment.update(ARCH=arch, VERSION=args.version, APPIMAGE_EXTRACT_AND_RUN='1')
    output = dist / f'formix-linux-{label}-v{args.version}.AppImage'
    run(tool, appdir, output, env=environment)
    output.chmod(0o755)
    run(output, '--appimage-extract', cwd=work)
    extracted = work / 'squashfs-root/usr/lib/formix'
    from payload_integrity import verify
    verify(extracted)
    run(extracted / 'python/bin/python3.11', root / 'packaging/smoke.py', extracted,
        env={**environment, 'QT_QPA_PLATFORM': 'offscreen'})


if __name__ == '__main__':
    main()
