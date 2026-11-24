#!/bin/bash
set -eu
version="$1"
mkdir -p dist
if [[ "$(uname)" == Darwin ]]; then
  arch="$(python3 -c 'import platform; print("arm64" if platform.machine() == "arm64" else "x64")')"
  app=build/root/Applications/Formix.app/Contents
  mkdir -p "$app/MacOS"
  mv build/macos-*-app "$app/Resources"
  cat > "$app/MacOS/Formix" <<'SCRIPT'
#!/bin/sh
root="$(dirname "$0")/../Resources"
exec "$root/python/bin/python3.11" -I "$root/main.py" "$@"
SCRIPT
  chmod +x "$app/MacOS/Formix"
  cat > "$app/Info.plist" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<plist version="1.0"><dict><key>CFBundleIdentifier</key><string>org.formix.desktop</string><key>CFBundleName</key><string>格式转换通</string><key>CFBundleDisplayName</key><string>格式转换通</string><key>CFBundlePackageType</key><string>APPL</string><key>CFBundleVersion</key><string>$version</string><key>CFBundleExecutable</key><string>Formix</string></dict></plist>
PLIST
  QT_QPA_PLATFORM=offscreen "$app/Resources/python/bin/python3.11" packaging/smoke.py "$app/Resources"
  pkgbuild --root build/root --identifier org.formix.desktop --version "$version" --install-location / "dist/formix-mac-${arch/x64/64}-v$version.pkg"
else
  app="build/linux-$(uname -m | sed 's/aarch64/arm64/;s/x86_64/x64/')-app"
  cat > "$app/Formix" <<'SCRIPT'
#!/bin/sh
root="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
export LD_LIBRARY_PATH="$root/python/lib:$root/python/lib/python3.11/site-packages/PySide6/Qt/lib:$root/vendor/office/usr/lib/libreoffice/program:$root/vendor/office/formix-libs${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
export SAL_USE_VCLPLUGIN=svp
exec "$root/python/bin/python3.11" -I "$root/main.py" "$@"
SCRIPT
  chmod +x "$app/Formix"
  python3 packaging/linux_packages.py "$app" "$version"
  tar -C build -czf "dist/formix-linux-$(uname -m | sed 's/aarch64/arm64/;s/x86_64/64/')-v$version.tar.gz" "$(basename "$app")"
fi
