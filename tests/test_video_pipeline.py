import sys,unittest,tempfile
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from formix.engines import plan,hardware_codec_for
class HardwarePipelineTests(unittest.TestCase):
 def command(self,encoder=None,decode=False):
  return plan('视频压缩',Path('source.mp4'),'balanced','',Path('cache/job'),Path('models'),hardware_encoder=encoder,hardware_decode=decode,compression_params={'width':1920,'height':1080})[0]
 def test_cuda_decode_and_scale_stay_on_gpu(self):
  cmd=self.command('h264_nvenc',True)
  self.assertLess(cmd.index('-hwaccel'),cmd.index('-i'))
  self.assertEqual(cmd[cmd.index('-hwaccel_output_format')+1],'cuda')
  self.assertTrue(cmd[cmd.index('-vf')+1].startswith('scale_cuda='))
 def test_hybrid_and_cpu_have_no_cuda_filters(self):
  for encoder in ('h264_nvenc',None,'h264_amf'):
   cmd=self.command(encoder)
   self.assertNotIn('-hwaccel',cmd)
   self.assertTrue(cmd[cmd.index('-vf')+1].startswith('scale='))
   self.assertEqual(cmd[cmd.index('-c:v')+1],encoder or 'libx264')
 def test_unsupported_target_has_no_hardware_route(self):
  for target in ('wmv','mpeg','vob','ogv'):
   self.assertIsNone(hardware_codec_for('视频转换',Path('input.mp4'),target))
if __name__=='__main__':unittest.main()
