import sys,tempfile,unittest,zipfile,xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from formix.runtime_paths import use_worker_modules
use_worker_modules('pdf')
from formix import worker
from formix.pdf_authorship import DC,CP,DCTERMS,XSI,source_author,finalize_authorship
import pymupdf

class AuthorshipTests(unittest.TestCase):
 def source(self,root,author):
  path=root/'source.pdf'
  doc=pymupdf.open();page=doc.new_page(width=400,height=400)
  page.insert_text((40,35),'Original author statement remains in the document.')
  for x in [40,180,320]:page.draw_line((x,60),(x,180))
  for y in [60,100,140,180]:page.draw_line((40,y),(320,y))
  for x,y,text in [(50,85,'Item'),(190,85,'Value'),(50,125,'Apple'),(190,125,'120'),(50,165,'Orange'),(190,165,'80')]:
   page.insert_text((x,y),text)
  doc.set_metadata({'author':author,'creator':'Source editing software','producer':'Source PDF software'})
  doc.save(path);doc.close()
  return path
 def test_actual_native_conversions_keep_only_source_author(self):
  for author in ('','Original Author'):
   with tempfile.TemporaryDirectory() as tmp:
    root=Path(tmp);source=self.source(root,author)
    for ext in ('docx','xlsx','pptx'):
     with self.subTest(author=author,format=ext):
      out=root/('result.'+ext);worker.pdf(source,out,root/'not-downloaded')
      with zipfile.ZipFile(out) as z:
       props=ET.fromstring(z.read('docProps/core.xml'))
       self.assertEqual(props.findtext('{'+DC+'}creator') or '',author)
       self.assertIsNone(props.find('{'+CP+'}lastModifiedBy'))
       self.assertIsNone(props.find('{'+DC+'}description'))
       for name in ('created','modified'):
        node=props.find('{'+DCTERMS+'}'+name)
        self.assertEqual(node.get('{'+XSI+'}type'),'dcterms:W3CDTF')
        stamp=datetime.fromisoformat(node.text.replace('Z','+00:00'))
        self.assertLess(abs((datetime.now(timezone.utc)-stamp).total_seconds()),30)
      if ext=='docx':
       from docx import Document
       self.assertIn('Originalauthorstatement',''.join(p.text for p in Document(out).paragraphs).replace(' ',''))
 def test_xmp_author_is_retained_when_info_author_is_missing(self):
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp);source=self.source(root,'')
   doc=pymupdf.open(source)
   doc.set_xml_metadata('<x:xmpmeta xmlns:x="adobe:ns:meta/"><rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#"><rdf:Description xmlns:dc="http://purl.org/dc/elements/1.1/"><dc:creator><rdf:Seq><rdf:li>Original XMP Author</rdf:li></rdf:Seq></dc:creator></rdf:Description></rdf:RDF></x:xmpmeta>')
   doc.saveIncr();doc.close()
   self.assertEqual(source_author(source),'Original XMP Author')
if __name__=='__main__':unittest.main()
