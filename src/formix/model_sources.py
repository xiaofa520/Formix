"""Verified official model sources, ranked by manifest and file response latency."""
from concurrent.futures import ThreadPoolExecutor, as_completed
import json
from pathlib import Path, PurePosixPath
import sys
import time
import urllib.request
from urllib.parse import quote, urlencode

MODELSCOPE_REPOS = {
    'pp-ocrv5-mobile': 'RapidAI/RapidOCR',
    'deepseek-ocr': 'deepseek-ai/DeepSeek-OCR',
    'smoldocling': 'docling-project/SmolDocling-256M-preview',
    'smolvlm-500m': 'HuggingFaceTB/SmolVLM-500M-Instruct',
    'granite-docling-258m': 'ibm-granite/granite-docling-258M',
    'paddleocr-vl-1.6': 'PaddlePaddle/PaddleOCR-VL-1.6',
    'glm-ocr': 'ZhipuAI/GLM-OCR',
    'dots-ocr': 'dots-studio/dots.ocr',
}
PROFILES = json.loads((Path(__file__).with_name('assets') / 'model-profiles.json').read_text(encoding='utf-8'))

def probe(source, key="deepseek-ocr"):
    repo = MODELSCOPE_REPOS[key] if source == "ModelScope" else PROFILES[key]["repo"]
    start = time.monotonic()
    mobile = key == 'pp-ocrv5-mobile'
    if source == 'ModelScope':
        base = 'https://www.modelscope.cn/api/v1/models/' + repo
        with urllib.request.urlopen(base + '/repo/files?' + urlencode({'Revision': 'v3.4.0' if mobile else 'master', 'Recursive': 'true'}), timeout=8) as r:
            info = json.load(r)
        entries = info['Data']['Files']
        files = {e['Path']: dict(size=e['Size'], sha256=e.get('Sha256'),
                 url=base + '/repo?' + urlencode({'Revision': e['Revision'], 'FilePath': e['Path']}))
                 for e in entries if e['Type'] == 'blob'}
    else:
        with urllib.request.urlopen('https://huggingface.co/api/models/' + repo + '/revision/main?blobs=true', timeout=8) as r:
            info = json.load(r)
        files = {e['rfilename']: dict(size=e['size'], sha256=(e.get('lfs') or {}).get('sha256'),
                 url='https://huggingface.co/' + repo + '/resolve/' + info['sha'] + '/' + quote(e['rfilename'], safe='/'))
                 for e in info['siblings']}
    if mobile:
        if source == 'ModelScope':
            mapping = {
                'PP-OCRv5_mobile_det.onnx': 'onnx/PP-OCRv5/det/ch_PP-OCRv5_mobile_det.onnx',
                'PP-OCRv5_mobile_rec.onnx': 'onnx/PP-OCRv5/rec/ch_PP-OCRv5_rec_mobile_infer.onnx',
                'PP-OCRv5_mobile_rec.dict.txt': 'paddle/PP-OCRv5/rec/ch_PP-OCRv5_rec_mobile_infer/ppocrv5_dict.txt',
            }
            files = {local: files[remote] for local, remote in mapping.items()}
            probe_name = 'PP-OCRv5_mobile_rec.dict.txt'
        else:
            names = ('PP-OCRv5_mobile_det.onnx', 'PP-OCRv5_mobile_rec.onnx', 'PP-OCRv5_mobile_rec.dict.json')
            files = {name: files[name] for name in names}
            probe_name = names[-1]
    else:
        files = {n: e for n, e in files.items() if ('/' not in n or n.endswith('.py'))
                 and n.endswith(('.json', '.safetensors', '.txt', '.model', '.jinja', '.py'))}
        probe_name = 'config.json'
    for name in files:
        if PurePosixPath(name).is_absolute() or '..' in PurePosixPath(name).parts or '\\' in name or ':' in name:
            raise ValueError('Unsafe model file path')
    if not mobile and ('config.json' not in files or not any(n.endswith('.safetensors') for n in files)):
        raise ValueError('Incomplete model manifest')
    # Measure a real file endpoint, including redirects, rather than the homepage.
    with urllib.request.urlopen(files[probe_name]['url'], timeout=8) as r:
        body = r.read(1024 * 1024)
        if probe_name.endswith('.json'):
            json.loads(body)
        elif len(body.decode('utf-8').splitlines()) != 18383:
            raise ValueError('Unexpected PP-OCRv5 dictionary')
    return dict(source=source, repo=repo, files=files, latency=time.monotonic() - start)

def ranked_sources(key="deepseek-ocr"):
    plans = []
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = {pool.submit(probe, source, key): source for source in ('Hugging Face', 'ModelScope')}
        for future in as_completed(futures):
            try:
                plan = future.result()
                plans.append(plan)
                print(f"{plan['source']} · {plan['latency'] * 1000:.0f} ms", file=sys.stderr, flush=True)
            except Exception as error:
                print(f'{futures[future]} · unavailable: {error}', file=sys.stderr, flush=True)
    if not plans:
        raise OSError('Hugging Face and ModelScope are both unavailable')
    return sorted(plans, key=lambda p: p['latency'])
