"""Choose locally available interface fonts without loading extra fonts into Qt."""
import os
import sys
from pathlib import Path

from PySide6.QtGui import QFontDatabase, QRawFont


COMMON = {
    "win32": ("微软雅黑", "Microsoft YaHei UI", "宋体", "黑体", "楷体", "仿宋", "Microsoft JhengHei",
              "Segoe UI", "Arial", "Calibri", "Verdana", "Tahoma", "Georgia", "Times New Roman",
              "Consolas", "Yu Gothic UI", "Malgun Gothic"),
    "darwin": ("PingFang SC", "PingFang TC", "Songti SC", "Heiti SC", "Kaiti SC", "Hiragino Sans",
               "Apple SD Gothic Neo", "Helvetica Neue", "Arial", "Avenir", "Georgia", "Times New Roman",
               "Menlo", "Monaco"),
    "linux": ("Noto Sans CJK SC", "Noto Serif CJK SC", "Noto Sans CJK TC", "Noto Sans CJK JP",
              "Noto Sans CJK KR", "WenQuanYi Micro Hei", "Noto Sans", "Noto Serif", "DejaVu Sans",
              "DejaVu Serif", "DejaVu Sans Mono", "Liberation Sans", "Liberation Serif",
              "Liberation Mono", "Ubuntu", "Cantarell"),
}


def local_font_directories():
    home = Path.home()
    if sys.platform == "win32":
        return [Path(os.environ.get("LOCALAPPDATA", home / "AppData/Local")) / "Microsoft/Windows/Fonts"]
    if sys.platform == "darwin":
        return [home / "Library/Fonts", Path("/Library/Fonts")]
    return [Path(os.environ.get("XDG_DATA_HOME", home / ".local/share")) / "fonts",
            home / ".fonts", Path("/usr/local/share/fonts")]


def interface_families(settings):
    installed = {f for f in QFontDatabase.families()
                 if not f.startswith("@") and not QFontDatabase.isPrivateFamily(f)}
    baseline_key = "interface/knownFonts/" + sys.platform
    if not settings.contains(baseline_key):
        settings.setValue(baseline_key, sorted(installed))
    baseline = settings.value(baseline_key, type=list)
    common = [f for f in COMMON.get(sys.platform, ()) if f in installed]
    if sys.platform == "win32":
        for localized, english in (("微软雅黑", "Microsoft YaHei"), ("宋体", "SimSun"),
                                   ("黑体", "SimHei"), ("楷体", "KaiTi"), ("仿宋", "FangSong")):
            if localized not in installed and english in installed:
                common.append(english)
    extras = installed.difference(baseline)
    extras.add(settings.value("interface/fontFamily", "", type=str))
    if sys.platform == "win32":
        # Per-user font shortcuts can reference files outside the Fonts folder.
        import winreg
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                                r"Software\Microsoft\Windows NT\CurrentVersion\Fonts") as key:
                for index in range(winreg.QueryInfoKey(key)[1]):
                    name, _, _ = winreg.EnumValue(key, index)
                    extras.update(name.split(" (")[0].split(" & "))
        except OSError:
            pass
    for directory in local_font_directories():
        if directory.is_dir():
            for path in directory.rglob("*"):
                if path.suffix.lower() in {".ttf", ".ttc", ".otf", ".otc"} and path.is_file():
                    face = QRawFont(str(path), 13)
                    if face.isValid():
                        extras.add(face.familyName())
    return common + sorted((installed & extras).difference(common), key=str.casefold)
