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
  python3 packaging/payload_integrity.py write "$app/Resources"
  pkgbuild --root build/root --component-plist packaging/macos-components.plist --identifier org.formix.desktop --version "$version" --install-location / "dist/formix-mac-${arch/x64/64}-v$version.pkg"
else
  app="build/linux-$(uname -m | sed 's/aarch64/arm64/;s/x86_64/x64/')-app"
  cat > "$app/Formix" <<'SCRIPT'
#!/bin/sh
set -eu
case "$0" in */*) directory=${0%/*} ;; *) directory=. ;; esac
root=$(CDPATH= cd -- "$directory" && pwd -P)
if [ ! -t 2 ] && [ -z "${FORMIX_CI_CONTROL:-}" ]; then
  logs="${XDG_STATE_HOME:-$HOME/.local/state}/Formix/logs"
  if mkdir -p -- "$logs" && ( : >> "$logs/launcher.log" ); then
    if [ -w "$logs" ] && [ -r "$logs/launcher.log" ] && [ "$(wc -c < "$logs/launcher.log")" -gt 5242880 ]; then
      mv -f -- "$logs/launcher.log" "$logs/launcher.previous.log" || echo "Formix: could not rotate launcher.log" >&2
    fi
    exec 2>>"$logs/launcher.log"
    printf '\nFormix startup: %s\n' "$root" >&2
  fi
fi
if [ -d "$root/qt-xcb-libs" ]; then
  export LD_LIBRARY_PATH="$root/qt-xcb-libs${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
fi
exec "$root/python/bin/python3" -I -X faulthandler "$root/main.py" "$@"
SCRIPT
  chmod +x "$app/Formix"
  python3 packaging/payload_integrity.py write "$app"
  python3 packaging/linux_packages.py "$app" "$version"
fi
