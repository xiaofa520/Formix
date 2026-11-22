"""Run against the staged interpreter and private engines before packaging."""
import os
import subprocess
import sys
import tempfile
from pathlib import Path

app=Path(sys.argv[1]).resolve()
profile = tempfile.TemporaryDirectory(prefix="formix-smoke-profile-")
for key in ("LOCALAPPDATA", "USERPROFILE", "HOME", "XDG_DATA_HOME"):
    os.environ[key] = profile.name
sys.path.insert(0,str(app))
from docx import Document
from formix.engines import plan
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QSettings
from formix.localization import LanguageManager
from formix.main import Window
from formix.runtime_paths import executable
from PIL import Image
import pyvips
import pdfplumber

os.environ["QT_QPA_PLATFORM"]="offscreen"
qt=QApplication([])
assert Path(executable("ffmpeg")).is_relative_to(app)
assert Path(executable("soffice")).is_relative_to(app)
with tempfile.TemporaryDirectory() as tmp:
    root=Path(tmp)
    class SmokeWindow(Window):
        @staticmethod
        def make_default_output_directory(): return root / "output"
    window=SmokeWindow(LanguageManager(QSettings(str(root / "settings.ini"), QSettings.Format.IniFormat)), startup_checks=False)
    window.close()
    word=Document()
    word.add_paragraph("Formix offline conversion")
    source=root/"source.docx"
    word.save(source)
    picture=root/"image.png"
    Image.new("RGB",(12,12)).save(picture)
    for page,src,fmt in (("文档转换",source,"pdf"),("PDF 转换",root/"source.pdf","txt"),("图片转换",picture,"jpg")):
        cmd,out=plan(page,src,fmt,None,root,root/"uninstalled-model")
        subprocess.run(cmd,check=True,timeout=180)
        assert out.stat().st_size
        if fmt=="txt":assert "Formix offline conversion" in out.read_text(encoding="utf8")

    import pymupdf
    ai = root / "vector.ai"
    with pymupdf.open() as document:
        page = document.new_page(width=80, height=80)
        page.draw_rect(pymupdf.Rect(10, 10, 60, 60), fill=(1, 0, 0))
        document.save(ai)
    cmd, out = plan("图片转换", ai, "svg", None, root, root / "uninstalled-model")
    subprocess.run(cmd, check=True, timeout=180)
    assert "<path" in out.read_text(encoding="utf-8")
print("Packaged GUI, Office/PDF, image and vector SVG smoke checks passed.")
