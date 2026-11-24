"""Network integration: actual source manifests, downloads and CPU OCR on each OS."""
import copy
import json
import re
import sys
import tempfile
import traceback
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from formix import worker, model_sources

EXPECTED = '格式转换通 图片文字识别测试\n毕业设计任务书 成果说明\n模型下载完成 1234567890\nFormix OCR Windows Linux'

def normalize(text):
    return re.sub(r'\s+', '', str(text))

def main():
    from PIL import Image
    import rapidocr, onnxruntime
    from formix.mobile_ocr import make_reader
    evidence = ROOT / 'build/model-source-test-logs'
    evidence.mkdir(parents=True, exist_ok=True)
    report = {'platform': sys.platform, 'sources': {}, 'ocr': {}, 'passed': False}
    try:
        worker.configure_download_network()
        mobile = None
        for key in model_sources.MODELSCOPE_REPOS:
            plans = model_sources.ranked_sources(key)
            assert {p['source'] for p in plans} == {'ModelScope', 'Hugging Face'}, key + ': source unavailable'
            assert plans[0]['latency'] <= plans[1]['latency']
            report['sources'][key] = [{'source': p['source'], 'latency': p['latency'],
                                      'files': len(p['files'])} for p in plans]
            if key == 'pp-ocrv5-mobile':
                mobile = plans
            else:
                by_source = {p['source']: p['files'] for p in plans}
                hf, ms = by_source['Hugging Face'], by_source['ModelScope']
                for name, entry in hf.items():
                    assert name in ms, (key, name, 'missing')
                    if name.endswith('.safetensors'):
                        assert entry['sha256'] and entry['sha256'] == ms[name]['sha256'], (key, name, 'weight mismatch')
                        assert entry['size'] == ms[name]['size'], (key, name, 'size mismatch')
        with tempfile.TemporaryDirectory(prefix='formix-model-ci-') as temp:
            dictionaries = []
            for index, plan in enumerate(mobile):
                target = Path(temp) / str(index) / 'pp-ocrv5-mobile'
                target.parent.mkdir()
                broken = copy.deepcopy(plan)
                first = next(iter(broken['files']))
                broken['files'][first]['url'] = 'https://formix-test.invalid/simulated-failure'
                original_open = worker.urllib.request.urlopen
                attempts = []
                def open_url(url, *args, **kwargs):
                    if url == 'https://formix-test.invalid/simulated-failure':
                        attempts.append(url)
                        raise OSError('Injected source outage')
                    return original_open(url, *args, **kwargs)
                # Dependencies are installed by the CI environment. Reuse them;
                # the real downloader, integrity checks and fallback remain active.
                with patch.object(worker, 'model_source_plans', return_value=[broken, plan]), \
                     patch.object(worker, 'prepare_private_model_runtime'), \
                     patch.object(worker.urllib.request, 'urlopen', side_effect=open_url):
                    worker.download(target, 'pp-ocrv5-mobile', 'auto')
                assert len(attempts) == 3 and (target / 'READY').is_file()
                dictionaries.append((target / 'characters.txt').read_text(encoding='utf-8').splitlines())
                with Image.open(ROOT / 'tests/fixtures/model-source-ocr.png') as image:
                    # Prove inference uses the downloaded local files with no network.
                    with patch.object(worker.urllib.request, 'urlopen', side_effect=AssertionError('Inference attempted network access')):
                        result = make_reader(target, 'document')(image)
                report['ocr'][plan['source']] = str(result)
                assert normalize(result) == normalize(EXPECTED), (plan['source'], str(result))
                print(plan['source'] + ': real download, outage fallback, checksum and offline OCR PASS', flush=True)
            assert dictionaries[0] == dictionaries[1] and len(dictionaries[0]) == 18383
        report['passed'] = True
    except Exception:
        report['error'] = traceback.format_exc()
        raise
    finally:
        (evidence / 'result.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')

if __name__ == '__main__':
    main()
