import os,sys,subprocess,unittest,tempfile
from pathlib import Path
from xml.etree import ElementTree as ET
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'))
from formix.runtime_paths import use_worker_modules
use_worker_modules('pdf')
import pymupdf
from formix import engines,worker
class SvgConversionTests(unittest.TestCase):
 def test_ai_worker_preserves_vector_paths_and_visuals(self):
  with tempfile.TemporaryDirectory() as folder:
   root=Path(folder);src=root/'vector.ai'
   with pymupdf.open() as doc:
    page=doc.new_page(width=320,height=180)
    page.draw_rect(pymupdf.Rect(20,20,120,120),color=(.1,.2,.8),fill=(.1,.2,.8))
    page.draw_circle(pymupdf.Point(180,70),40,color=(1,.2,.1),fill=(1,.2,.1),fill_opacity=.65)
    page.insert_text((20,155),'Formix SVG',fontsize=20)
    doc.save(src)
   cmd,out=engines.plan('图片转换',src,'svg',None,root,root)
   run=subprocess.run(cmd,capture_output=True)
   self.assertEqual(run.returncode,0,run.stderr.decode(errors='replace'))
   tree=ET.parse(out);ns={'s':'http://www.w3.org/2000/svg'}
   self.assertGreater(len(tree.findall('.//s:path',ns)),2)
   self.assertEqual(tree.findall('.//s:image',ns),[])
   with pymupdf.open(str(src),filetype='pdf') as source,pymupdf.open(str(out)) as result:
    a=source[0].get_pixmap(matrix=pymupdf.Matrix(2,2));b=result[0].get_pixmap(matrix=pymupdf.Matrix(2,2))
    self.assertEqual((a.width,a.height),(b.width,b.height))
    import numpy as np
    error=np.abs(np.frombuffer(a.samples,dtype=np.uint8).astype(float)-np.frombuffer(b.samples,dtype=np.uint8))
    self.assertLess(error.mean(),2.0)
 def test_multi_artboard_is_not_silently_truncated(self):
  with tempfile.TemporaryDirectory() as folder:
   src=Path(folder)/'multi.ai';out=src.with_suffix('.svg')
   with pymupdf.open() as doc:
    doc.new_page();doc.new_page();doc.save(src)
   with self.assertRaisesRegex(ValueError,'单画板'):worker.ai_svg(src,out)
   self.assertFalse(out.exists())
 def test_old_ai_has_actionable_error(self):
  with tempfile.TemporaryDirectory() as folder:
   src=Path(folder)/'legacy.ai';src.write_text('%!PS-Adobe-3.0\n%%Creator: Adobe Illustrator\n')
   with self.assertRaisesRegex(ValueError,'PDF 兼容'):worker.ai_svg(src,src.with_suffix('.svg'))
 def test_svg_passthrough_and_no_fake_raster_vectorization(self):
  with tempfile.TemporaryDirectory() as folder:
   src=Path(folder)/'in.svg';out=Path(folder)/'out.svg'
   src.write_text('<svg xmlns="http://www.w3.org/2000/svg" width="8" height="8"><path d="M0 0L8 8"/></svg>')
   worker.convert_image(src,out);self.assertEqual(src.read_bytes(),out.read_bytes())
   with self.assertRaises(ValueError):worker.convert_image(src.with_suffix('.png'),out)
