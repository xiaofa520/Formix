import hashlib
import io
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from formix import model_sources, worker

class ModelSourceTests(unittest.TestCase):
    def test_ranks_by_latency_and_ignores_unavailable_source(self):
        def probe(source, key):
            return dict(source=source, latency=2 if source == 'Hugging Face' else 1)
        with patch.object(model_sources, 'probe', side_effect=probe):
            self.assertEqual(model_sources.ranked_sources()[0]['source'], 'ModelScope')
        with patch.object(model_sources, 'probe', side_effect=[OSError('offline'), dict(source='other', latency=1)]):
            self.assertEqual(len(model_sources.ranked_sources()), 1)

    def test_corrupt_first_source_falls_back_without_mixing_files(self):
        first = dict(source='first', files={'extra.json': dict(size=1, url='extra', sha256=None),
            'config.json': dict(size=3, url='broken', sha256=hashlib.sha256(b'yes').hexdigest())})
        second = dict(source='second', files={'config.json':dict(size=3,url='good',sha256=hashlib.sha256(b'yes').hexdigest())})
        def open_url(url, **kwargs):
            return io.BytesIO(b'x' if url == 'extra' else b'bad' if url == 'broken' else b'yes')
        with tempfile.TemporaryDirectory() as t, patch.object(worker, 'model_source_plans', return_value=[first,second]), \
             patch.object(worker, 'intel_mac', return_value=False), patch.object(worker, 'prepare_private_model_runtime'), \
             patch.object(worker, 'configure_download_network'), patch.object(worker.time, 'sleep'), \
             patch.object(worker.urllib.request, 'urlopen', side_effect=open_url):
            target=Path(t)/'model'
            worker.download(target,'deepseek-ocr','auto')
            self.assertTrue((target/'READY').exists())
            self.assertEqual((target/'config.json').read_bytes(),b'yes')
            self.assertFalse((target/'extra.json').exists())

    def test_mobile_dictionary_and_fallback_use_one_complete_set(self):
        import json
        tokens = ['字'] * 18383
        dictionary = json.dumps(tokens).encode()
        good = {'PP-OCRv5_mobile_det.onnx': b'det', 'PP-OCRv5_mobile_rec.onnx': b'rec',
                'PP-OCRv5_mobile_rec.dict.json': dictionary}
        first = dict(source='ModelScope', files={'PP-OCRv5_mobile_rec.dict.txt':
            dict(size=7, url='broken', sha256=None)})
        second = dict(source='Hugging Face', files={name: dict(size=len(data), url=name,
            sha256=hashlib.sha256(data).hexdigest()) for name, data in good.items()})
        def response(url, **kwargs):
            return io.BytesIO(b'partial'[:2] if url == 'broken' else good[url])
        with tempfile.TemporaryDirectory() as t, patch.object(worker, 'model_source_plans', return_value=[first,second]), \
             patch.object(worker, 'intel_mac', return_value=False), patch.object(worker, 'prepare_private_model_runtime'), \
             patch.object(worker, 'configure_download_network'), patch.object(worker.time, 'sleep'), \
             patch.object(worker.urllib.request, 'urlopen', side_effect=response):
            target = Path(t) / 'model'
            worker.download(target, 'pp-ocrv5-mobile', 'auto')
            self.assertTrue((target / 'READY').exists())
            self.assertFalse((target / 'PP-OCRv5_mobile_rec.dict.txt').exists())
            self.assertEqual((target / 'characters.txt').read_text(encoding='utf-8').splitlines(), tokens)
            for name, data in good.items():
                self.assertEqual((target / name).read_bytes(), data)

    def test_mobile_rejects_incomplete_dictionary(self):
        with tempfile.TemporaryDirectory() as t:
            folder = Path(t)
            (folder / 'PP-OCRv5_mobile_rec.dict.txt').write_text('bad', encoding='utf-8')
            with self.assertRaises(ValueError):
                worker.mobile_dictionary(folder)
            self.assertFalse((folder / 'characters.txt').exists())
