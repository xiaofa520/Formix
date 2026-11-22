import json,sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from formix.runtime_paths import use_worker_modules
use_worker_modules('pdf')
from formix.recognition_layout import grounded,dots,region,generation_status,Recognition,table_only_page
from formix.pdf_word_layout import html_table,add_provenance,repair_table_grids
from docx import Document
class LayoutTests(unittest.TestCase):
 def test_deepseek_keeps_raw_and_normalizes_999_coordinates(self):
  raw='<|ref|>table<|/ref|><|det|>[[0, 0, 999, 999]]<|/det|>\n<table><tr><td>A</td></tr></table>'
  value=grounded(raw)
  self.assertEqual(value.raw,raw)
  self.assertEqual(value.regions[0]['bbox'],[0,0,1,1])
  self.assertIn('<table>',value)
 def test_invalid_coordinates_are_not_used(self):
  self.assertIsNone(region('text',[-1,0,1,1],'a'))
  self.assertFalse(grounded('<|ref|>text<|/ref|><|det|>not python<|/det|>a').regions)
 def test_dots_pixel_geometry(self):
  value=dots(json.dumps([{'bbox':[20,40,100,160],'category':'Text','text':'hello'}]),(200,200))
  self.assertEqual(value.regions[0]['bbox'],[.1,.2,.5,.8])
 def test_table_row_and_column_merges(self):
  doc=Document()
  grid=html_table(doc,'<table><tr><td rowspan="2">A</td><td colspan="2">B</td></tr><tr><td>C<br/>D</td><td>E</td></tr></table>')
  self.assertEqual(len(grid.rows),2)
  self.assertEqual(len(grid.columns),3)
  self.assertEqual(grid.cell(0,0)._tc,grid.cell(1,0)._tc)
  self.assertEqual(grid.cell(0,1)._tc,grid.cell(0,2)._tc)
  self.assertEqual(grid.cell(1,1).text,'C\nD')
 def test_model_provenance_is_embedded_not_visible(self):
  from io import BytesIO
  import zipfile
  doc=Document();add_provenance(doc,[{'raw':'<x>中文','regions':[]}])
  stream=BytesIO();doc.save(stream)
  with zipfile.ZipFile(stream) as z:
   self.assertIn('中文',z.read('customXml/formix-recognition.xml').decode())
  self.assertFalse(doc.paragraphs)
 def test_truncated_generation_has_explicit_warning(self):
  from types import SimpleNamespace
  self.assertTrue(generation_status('partial',[[3,4]],SimpleNamespace(eos_token_id=2)).warnings)
  self.assertFalse(generation_status('complete',[[3,2]],SimpleNamespace(eos_token_id=2)).warnings)
 def test_table_prompt_does_not_discard_outside_text_or_mistake_a_border(self):
  from PIL import Image,ImageDraw
  image=Image.new('RGB',(800,1100),'white');draw=ImageDraw.Draw(image)
  draw.rectangle((50,100,750,1050),outline='black',width=3)
  self.assertFalse(table_only_page(image))
  draw.line((50,550,750,550),fill='black',width=3)
  self.assertTrue(table_only_page(image))
  draw.rectangle((100,30,300,50),fill='black')
  self.assertFalse(table_only_page(image))
 def test_unequal_table_widths_are_preserved_for_writer(self):
  from docx.shared import Pt
  doc=Document();table=doc.add_table(rows=2,cols=2)
  for row in table.rows:
   row.cells[0].width=Pt(70);row.cells[1].width=Pt(200)
  repair_table_grids(doc)
  self.assertAlmostEqual(table.columns[0].width.pt,70,places=1)
  self.assertAlmostEqual(table.columns[1].width.pt,200,places=1)
 def test_partial_scan_output_is_not_reported_as_success(self):
  import tempfile
  import pypdfium2
  from test_pdf_models import text_pdf
  from formix import worker,pdf_model
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp);source=root/'scan.pdf';text_pdf(source)
   with pypdfium2.PdfDocument(source) as pdf:
    with self.assertRaisesRegex(ValueError,'生成上限'):
     pdf_model.convert(pdf,root/'out.docx',root/'smolvlm-500m',
       lambda *a,**kw:lambda im:Recognition('partial',warnings=['达到生成上限']),
       worker.raster,lambda *a:None)
   self.assertFalse((root/'out.docx').exists())
if __name__=='__main__':unittest.main()
