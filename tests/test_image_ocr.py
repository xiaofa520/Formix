import sys,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from formix import engines,worker
from PIL import Image
class ImageOCRTests(unittest.TestCase):
 def test_plan_uses_lightweight_model_and_staging(self):
  cmd,out=engines.plan('图片提取文字',Path('a.png'),'txt','',Path('cache/job'),Path('models/deepseek-ocr'))
  self.assertEqual(out,Path('cache/job/result.txt'))
  self.assertEqual(Path(cmd[-2]),Path('models/pp-ocrv5-mobile'))
  self.assertIn('image-ocr',cmd)
 def test_multiframe_output_and_missing_model(self):
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp);model=root/'model';model.mkdir();out=root/'out.txt';source=root/'scan.tiff'
   with self.assertRaisesRegex(ValueError,'下载'):worker.image_ocr(source,out,model)
   (model/'READY').touch()
   Image.new('RGB',(20,20),'white').save(source,save_all=True,append_images=[Image.new('RGB',(20,20),'black')])
   with patch.object(worker,'recognize',return_value=lambda image:'白色' if image.getpixel((0,0))==(255,255,255) else '黑色'):
    worker.image_ocr(source,out,model)
   self.assertEqual(out.read_text('utf-8-sig'),'白色\n\n黑色')
 def test_copy_mode_never_writes_document(self):
  import io,contextlib,base64
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp);(root/'READY').touch();source=root/'image.png';out=root/'result.txt'
   Image.new('RGB',(20,20),'white').save(source)
   stream=io.StringIO()
   with patch.object(worker,'recognize',return_value=lambda image:'识别内容'),contextlib.redirect_stdout(stream):
    worker.image_ocr(source,out,root,mode='copy')
   self.assertFalse(out.exists())
   self.assertEqual(base64.b64decode(stream.getvalue().strip().split('|')[1]).decode(),'识别内容')
 def test_markdown_plan_keeps_extension(self):
  cmd,out=engines.plan('图片提取文字',Path('a.png'),'md','',Path('cache/job'),Path('models/deepseek-ocr'))
  self.assertEqual(out.suffix,'.md')
  self.assertEqual(cmd[-1],'md')
 def test_image_and_pdf_models_are_independent_snapshots(self):
  root=Path('models/deepseek-ocr');stage=Path('cache/job')
  image,_=engines.plan('图片提取文字',Path('a.png'),'txt','',stage,root,compression_params={'recognition_model':'paddleocr-vl-1.6'})
  pdf,_=engines.plan('PDF 转换',Path('a.pdf'),'docx','',stage,Path('models/pp-ocrv5-mobile'),compression_params={'recognition_model':'deepseek-ocr'})
  self.assertEqual(Path(image[-2]),Path('models/paddleocr-vl-1.6'))
  self.assertEqual(Path(pdf[-1]),Path('models/deepseek-ocr'))
  with self.assertRaises(ValueError):
   engines.plan('图片提取文字',Path('a.png'),'txt','',stage,root,compression_params={'recognition_model':'../outside'})
if __name__=='__main__':unittest.main()
