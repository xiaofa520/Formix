import sys,unittest,tempfile
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from formix import engines
class VideoFormatPolicyTests(unittest.TestCase):
 def test_format_only_copies_even_with_gpu_available(self):
  with tempfile.TemporaryDirectory() as folder:
   cmd,_=engines.plan('视频转换',Path('input.mp4'),'mkv',None,Path(folder),Path(folder),hardware_encoder='h264_nvenc',hardware_decode=True)
   self.assertIn('copy',cmd);self.assertNotIn('h264_nvenc',cmd);self.assertNotIn('-hwaccel',cmd)
 def test_transcoding_is_lossless_without_pixel_conversion(self):
  for gpu in [None,'h264_nvenc']:
   with tempfile.TemporaryDirectory() as folder:
    cmd,_=engines.plan('视频转换',Path('input.avi'),'mp4',None,Path(folder),Path(folder),hardware_encoder=gpu,compression_params={'video_transcode':True})
    self.assertEqual(cmd[cmd.index('-pix_fmt')+1],'+')
    self.assertIn('lossless' if gpu else '-crf',cmd)
    self.assertEqual(cmd[cmd.index('-c:a')+1],'copy')
 def test_unsupported_lossless_target_fails_explicitly(self):
  with self.assertRaises(ValueError):engines.lossless_video_args('wmv')
