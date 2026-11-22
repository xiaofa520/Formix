import sys,unittest,tempfile
from pathlib import Path
sys.path.insert(0,str(Path('src').resolve()))
from formix.runtime_paths import use_worker_modules
use_worker_modules('pdf')
from formix.pdf_word_layout import native_lines,annotate_pdf_emphasis
from docx import Document
from docx.oxml.ns import qn
import pymupdf,pdfplumber
class Regression(unittest.TestCase):
 def test_indented_continuations_and_new_item(self):
  chars=[]
  for y,x,text in [(10,24,'1.hello'),(32,0,'world'),(54,24,'2.next')]:
   for i,c in enumerate(text):chars.append(dict(text=c,x0=x+i*6,x1=x+i*6+6,top=y,bottom=y+12,size=12,fontname='SimSun'))
  d=Document();native_lines(d,chars,absolute=False)
  self.assertEqual([p.text for p in d.paragraphs],['1.helloworld','2.next'])
  self.assertEqual(d.paragraphs[0].paragraph_format.first_line_indent.pt,24)
  self.assertEqual(d.paragraphs[0].paragraph_format.line_spacing.pt,22)
  self.assertEqual(d.paragraphs[0]._p.pPr.find(qn('w:autoSpaceDN')).get(qn('w:val')),'0')
 def test_faux_bold_is_detected_without_bold_font_name(self):
  with tempfile.TemporaryDirectory() as tmp:
   path=Path(tmp)/'test.pdf';d=pymupdf.open();p=d.new_page()
   p.insert_text((30,40),'Bold',render_mode=2);p.insert_text((30,70),'Plain');d.save(path);d.close()
   with pdfplumber.open(path) as d:
    annotate_pdf_emphasis(path,d.pages)
    chars=d.pages[0].chars
    self.assertTrue(all(c['formix_bold'] for c in chars[:4]))
    self.assertFalse(any(c['formix_bold'] for c in chars[4:]))
if __name__=='__main__':unittest.main()
