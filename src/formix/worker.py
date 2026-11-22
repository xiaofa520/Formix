"""Short-lived media workers. Heavy libraries never enter the GUI process."""
import csv
import os
import html
import json
import urllib.request
import math
import re
import platform
import shutil
import sys
import time
import zipfile
from pathlib import Path
if __package__:
    from .engines import MODEL_PROFILES, MODEL_REPOS, media_threads
    from .output_safety import csv_text, embed_html_assets
    from .recognition_layout import grounded, dots, docling_result, generation_status, table_only_page
    from .process_utils import run_pip, run_process, timeout_setting
else:
    from engines import MODEL_PROFILES, MODEL_REPOS, media_threads
    from output_safety import csv_text, embed_html_assets
    from recognition_layout import grounded, dots, docling_result, generation_status, table_only_page
    from process_utils import run_pip, run_process, timeout_setting

_language = None

def tr(key, **values):
    global _language
    if _language is None:
        if __package__:
            from .localization import LanguageManager
        else:
            from localization import LanguageManager
        _language = LanguageManager()
    return _language.t(key, **values)

def ncm_minimum_progress_seconds():
    """Choose a minimum visible NCM task duration by device tier."""
    try:
        import psutil
        physical_cores = psutil.cpu_count(logical=False) or psutil.cpu_count() or 2
        total_gib = psutil.virtual_memory().total / 1024**3
    except Exception:
        physical_cores, total_gib = 2, 4
    if physical_cores <= 2 or total_gib <= 4:
        return 180
    if physical_cores <= 4 or total_gib <= 8:
        return 120
    if physical_cores <= 8 or total_gib <= 16:
        return 60
    return 30

def configure_download_network():
    # urllib discovers environment proxies and Windows Internet Settings.
    proxies = urllib.request.getproxies()
    for scheme in ("http", "https"):
        proxy = proxies.get(scheme) or proxies.get("all")
        if proxy:
            if "://" not in proxy:
                proxy = "http://" + proxy
            os.environ.setdefault(scheme.upper() + "_PROXY", proxy)
    urllib.request.install_opener(
        urllib.request.build_opener(urllib.request.ProxyHandler(urllib.request.getproxies()))
    )


def manifest(key, revision="main"):
    configure_download_network()
    repo = MODEL_REPOS[key]
    url = f"https://huggingface.co/api/models/{repo}/revision/{revision}?blobs=true"
    with urllib.request.urlopen(url, timeout=30) as response:
        info = json.load(response)
    if key == "pp-ocrv5-mobile":
        sizes = {entry["rfilename"]: entry["size"] for entry in info["siblings"]}
        names = ("PP-OCRv5_mobile_det.onnx", "PP-OCRv5_mobile_rec.onnx", "PP-OCRv5_mobile_rec.dict.json")
        return info["sha"], {name: sizes[name] for name in names}
    files = {entry["rfilename"]: entry["size"] for entry in info["siblings"]
             if ("/" not in entry["rfilename"] or entry["rfilename"].endswith(".py"))
             and entry["rfilename"].endswith(
                 (".json", ".safetensors", ".txt", ".model", ".jinja", ".py"))}
    if not any(name.endswith(".safetensors") for name in files):
        raise ValueError("Missing model weights")
    return info["sha"], files


def runtime_dir(model_root):
    machine = platform.machine().lower()
    arch = "arm64" if machine in {"arm64", "aarch64"} else machine
    system = platform.system().lower()
    return model_root / f".vision-runtime-v3-{system}-{arch}-{sys.implementation.cache_tag}"


def intel_mac():
    return platform.system() == "Darwin" and platform.machine().lower() in {"x86_64", "amd64"}


def prepare_runtime(stage):
    probe = "import torch, torchvision, num2words, huggingface_hub, docling_core, einops; from transformers import AutoProcessor, AutoModelForImageTextToText, AutoModelForCausalLM"
    target = runtime_dir(stage.parent)
    local_probe = "import sys; sys.path.insert(0,sys.argv[1]); " + probe
    if target.is_dir():
        result = run_process([sys.executable, "-c", local_probe, str(target)],
                             capture_output=True, timeout=60)
        if result.returncode == 0:
            sys.path.insert(0, str(target))
            return
        print("Model runtime validation failed; repairing dependencies.",
              file=sys.stderr, flush=True)
        details = result.stderr or result.stdout
        if details:
            print(details.decode(errors="replace") if isinstance(details, bytes) else details,
                  file=sys.stderr, flush=True)
    elif run_process([sys.executable, "-c", probe],
                     capture_output=True, timeout=45).returncode == 0:
        return

    print("FORMIX_MODEL|preparing_runtime", file=sys.stderr, flush=True)
    # Keep the runtime at its final path. Windows may lock DLL-containing
    # directories after import validation, preventing a directory rename.
    target.mkdir(parents=True, exist_ok=True)
    print(f"pip → {target}", file=sys.stderr, flush=True)
    import importlib.util
    build_args = ['--no-build-isolation'] if importlib.util.find_spec('setuptools') else []
    accelerator_args = []
    if platform.system() == 'Windows':
        if __package__:
            from .hardware_info import cuda_driver_version
        else:
            from hardware_info import cuda_driver_version
        driver = cuda_driver_version()
        if driver and tuple(map(int, driver.split('.'))) >= (12, 6):
            accelerator_args = ['--extra-index-url', 'https://download.pytorch.org/whl/cu126',
                                'torch==2.6.0+cu126', 'torchvision==0.21.0+cu126']
    run_pip([sys.executable, "-u", "-X", "utf8", "-m", "pip", "install", "--disable-pip-version-check",
                 "--progress-bar", "raw", "--no-cache-dir", "--upgrade",
                 "--only-binary", "torch,torchvision,tokenizers,safetensors",
                 "--target", str(target),
                 *build_args, *accelerator_args,
                 "-r", str(Path(__file__).with_name(
                     "requirements-model-intel-mac.txt" if intel_mac() else "requirements-model.txt"))],
                check=True, timeout=timeout_setting('FORMIX_RUNTIME_TIMEOUT', 1800))
    result = run_process([sys.executable, "-c", local_probe, str(target)],
                         capture_output=True, timeout=60)
    if result.returncode != 0:
        details = result.stderr or result.stdout or b"Unknown import error"
        if isinstance(details, bytes):
            details = details.decode(errors="replace")
        raise RuntimeError("Model runtime validation failed: " + details)
    sys.path.insert(0, str(target))


PRIVATE_MODEL_PACKAGES = {
    "pp-ocrv5-mobile": ["rapidocr>=3.4,<4", "onnxruntime>=1.20,<2"],
    "deepseek-ocr": ["--extra-index-url", "https://download.pytorch.org/whl/cu126",
                    "torch==2.6.0+cu126", "torchvision==0.21.0+cu126", "transformers==4.46.3",
                    "accelerate<2", "einops", "addict", "easydict", "matplotlib", "Pillow"],
}


def prepare_private_model_runtime(models, key):
    target = runtime_dir(models)
    imports = ('import rapidocr, onnxruntime' if key == 'pp-ocrv5-mobile' else
               'import torch, torchvision, transformers, accelerate, einops, addict, easydict')
    command = [sys.executable, '-I', '-c', 'import sys; sys.path.insert(0,sys.argv[1]); ' + imports, str(target)]
    if target.is_dir() and run_process(command, capture_output=True, timeout=60).returncode == 0:
        return target
    print("FORMIX_MODEL|preparing_runtime", file=sys.stderr, flush=True)
    target.mkdir(parents=True, exist_ok=True)
    print(f"pip → {target}", file=sys.stderr, flush=True)
    run_pip([sys.executable, "-I", "-u", "-X", "utf8", "-m", "pip", "--isolated", "install", "--no-cache-dir", "--progress-bar", "raw",
             "--upgrade", "--target", str(target), *PRIVATE_MODEL_PACKAGES[key]],
            check=True, timeout=timeout_setting("FORMIX_MODEL_INSTALL_TIMEOUT", 14400))
    result = run_process(command, capture_output=True, timeout=60)
    if result.returncode:
        raise RuntimeError(f'{key}: 模型运行环境校验失败：' + result.stderr.decode(errors='replace'))
    return target


def download(target, key, revision):
    if intel_mac() and key not in {"granite-docling-258m", "smoldocling", "smolvlm-500m", "pp-ocrv5-mobile"}:
        raise ValueError("Intel Mac: select Granite Docling for the compatible CPU runtime.")
    print(f"Hugging Face · {MODEL_REPOS[key]} @ {revision}", file=sys.stderr, flush=True)
    revision, files = manifest(key, revision)
    if shutil.disk_usage(target.parent).free < sum(files.values()) + 256 * 1024**2:
        raise ValueError(tr("model_disk_space"))
    target.mkdir()
    configure_download_network()
    if key in PRIVATE_MODEL_PACKAGES:
        prepare_private_model_runtime(target, key)
    else:
        prepare_runtime(target.parent)
    from urllib.parse import quote
    print("FORMIX_MODEL|downloading_model", file=sys.stderr, flush=True)
    total = sum(files.values())
    completed = 0
    for name, size in files.items():
        relative = Path(name)
        if relative.is_absolute() or ".." in relative.parts:
            raise ValueError("Unsafe model file path")
        destination = target / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        url = f"https://huggingface.co/{MODEL_REPOS[key]}/resolve/{revision}/{quote(name, safe='/')}"
        for attempt in range(3):
            print(f"↓ {name} ({size / 1024**2:.2f} MiB) → {destination.parent}",
                  file=sys.stderr, flush=True)
            received = 0
            last_report = 0
            try:
                with urllib.request.urlopen(url, timeout=60) as response, destination.open("wb") as stream:
                    while True:
                        block = response.read(256 * 1024)
                        if not block:
                            break
                        stream.write(block)
                        received += len(block)
                        now = time.monotonic()
                        if now - last_report >= .2:
                            print(f"FORMIX_PROGRESS|model|{completed + received}|{total}",
                                  file=sys.stderr, flush=True)
                            last_report = now
                if received != size:
                    raise OSError(f"Incomplete model file: {name} ({received}/{size})")
                break
            except (OSError, TimeoutError) as exc:
                if attempt == 2:
                    raise
                print(f"{name} · {exc} · {attempt + 2}/3", file=sys.stderr, flush=True)
                time.sleep(attempt + 1)
        completed += size
        print(f"FORMIX_PROGRESS|model|{completed}|{total}", file=sys.stderr, flush=True)
    if key == "pp-ocrv5-mobile":
        mobile_dictionary(target)
    (target/"READY").touch()


def mobile_dictionary(models):
    tokens = json.loads((models / "PP-OCRv5_mobile_rec.dict.json").read_text(encoding="utf-8"))
    (models / "characters.txt").write_text("\n".join(tokens) + "\n", encoding="utf-8")


def recognize(models, task="document"):
    try:
        reader = _recognize(models, task)
    except ImportError as exc:
        raise RuntimeError(f'{models.name}: 模型文件已下载，但当前 Python {sys.version_info.major}.{sys.version_info.minor} 的运行依赖不可用，请重新安装模型运行环境。{exc}') from exc
    def read(image):
        import threading
        stopped = threading.Event()
        started = time.monotonic()
        def heartbeat():
            while not stopped.wait(15):
                print(f'PDF · {models.name} 正在识别当前页，已用时 {int(time.monotonic()-started)} 秒',
                      file=sys.stderr, flush=True)
        thread = threading.Thread(target=heartbeat, daemon=True)
        thread.start()
        try:
            return reader(image)
        finally:
            stopped.set()
            thread.join(timeout=1)
    return read


def generation_guard(prompt_length):
    """Stop pathological repetition without forcing the model to invent alternatives."""
    from transformers import StoppingCriteria, StoppingCriteriaList
    class RepeatedOutput(StoppingCriteria):
        def __call__(self, input_ids, scores, **kwargs):
            count = input_ids.shape[-1] - prompt_length
            if count < 320 or count % 32:
                return False
            tokens = input_ids[0][prompt_length:].tolist()
            encoded = ' ' + ' '.join(map(str, tokens)) + ' '
            tail = ' ' + ' '.join(map(str, tokens[-64:])) + ' '
            return encoded.count(tail) >= 5
    return StoppingCriteriaList([RepeatedOutput()])


def _recognize(models, task="document"):
    import tempfile
    threads = min(4, media_threads())
    for name in ('OMP_NUM_THREADS', 'MKL_NUM_THREADS', 'OPENBLAS_NUM_THREADS'):
        os.environ.setdefault(name, str(threads))
    # Remote-code models still need a writable local module cache when offline.
    os.environ.setdefault('HF_MODULES_CACHE', str(Path(tempfile.gettempdir()) / 'formix-hf-modules'))
    os.environ.setdefault('HF_HOME', str(Path(tempfile.gettempdir()) / 'formix-hf'))
    if models.name == "deepseek-ocr":
        print("DeepSeek-OCR · 检查运行环境和可用显存", file=sys.stderr, flush=True)
        local_runtime = runtime_dir(models)
        if not local_runtime.is_dir():
            raise RuntimeError("DeepSeek-OCR 运行环境缺失，请在设置中重新安装模型。")
    elif models.name in PRIVATE_MODEL_PACKAGES:
        local_runtime = runtime_dir(models)
        if not local_runtime.is_dir():
            legacy = models / '.runtime'
            probe = run_process([sys.executable, '-I', '-c',
                                 'import sys; sys.path.insert(0,sys.argv[1]); import rapidocr,onnxruntime',
                                 str(legacy)], capture_output=True, timeout=30) if legacy.is_dir() else None
            if probe is None or probe.returncode:
                raise RuntimeError(f'{models.name}: 模型运行环境不兼容当前 Python，请重新安装模型运行环境。')
            local_runtime = legacy
    else:
        local_runtime = runtime_dir(models.parent)
    if local_runtime.is_dir():
        sys.path.insert(0, str(local_runtime))
    import psutil
    try:
        process = psutil.Process()
        process.nice(psutil.BELOW_NORMAL_PRIORITY_CLASS if os.name == 'nt' else 5)
    except (psutil.Error, AttributeError):
        pass
    profile = MODEL_PROFILES[models.name]
    min_ram = profile["min_available_ram_gib"]
    if psutil.virtual_memory().available < min_ram * 1024**3:
        raise ValueError(tr("pdf_memory_low", gb=min_ram))
    if models.name == "pp-ocrv5-mobile":
        if __package__:
            from .mobile_ocr import make_reader
        else:
            from mobile_ocr import make_reader
        return make_reader(models, task)
    import torch
    torch.set_num_threads(threads)
    min_vram = profile["min_cuda_vram_gib"]
    use_gpu = False
    if torch.cuda.is_available():
        try:
            use_gpu = torch.cuda.mem_get_info()[0] >= min_vram * 1024**3
        except (RuntimeError, AttributeError):
            use_gpu = False
    device = "cuda" if use_gpu else "cpu"
    print(f'{models.name} · {device.upper()} · CPU threads={threads}', file=sys.stderr, flush=True)
    use_bf16 = device == "cuda" and getattr(torch.cuda, "is_bf16_supported", lambda: False)()
    if models.name == "deepseek-ocr":
        if not use_gpu or not use_bf16:
            detail = tr("deepseek_gpu_required", gb=min_vram)
            if torch.cuda.is_available():
                detail += f" 当前可用 {torch.cuda.mem_get_info()[0] / 1024**3:.1f} GiB。"
            raise ValueError(detail)
        import tempfile
        from transformers import AutoModel, AutoTokenizer
        from transformers.utils import is_flash_attn_2_available
        attention = "flash_attention_2" if is_flash_attn_2_available() else "eager"
        print(f"DeepSeek-OCR · 正在加载模型到显卡（{attention}）", file=sys.stderr, flush=True)
        print('DeepSeek-OCR · base_size=1024 · image_size=640 · crop_mode=True · 保留 grounding 坐标',
              file=sys.stderr, flush=True)
        tokenizer = AutoTokenizer.from_pretrained(models, trust_remote_code=True, local_files_only=True)
        model = AutoModel.from_pretrained(models, trust_remote_code=True, local_files_only=True,
                                          torch_dtype=torch.bfloat16, attn_implementation=attention,
                                          device_map={"": "cuda:0"}).eval()

        def read(image):
            with tempfile.TemporaryDirectory() as folder:
                page = Path(folder) / "page.png"
                image.convert("RGB").save(page)
                prompt = "<image>\n<|grounding|>Convert the document to markdown."
                with torch.inference_mode():
                    result = model.infer(tokenizer, prompt=prompt, image_file=str(page),
                                         output_path=folder, base_size=1024, image_size=640,
                                         crop_mode=True, eval_mode=True, save_results=False)
                return grounded(result)
        return read
    from transformers import AutoProcessor, AutoModelForImageTextToText
    dtype = torch.bfloat16 if use_bf16 else torch.float32
    print(f'{models.name} · 生成缓存已启用 · 单页生成上限 {timeout_setting("FORMIX_OCR_PAGE_TIMEOUT", 180)} 秒',
          file=sys.stderr, flush=True)

    if models.name == "glm-ocr":
        from transformers import AutoProcessor, GlmOcrForConditionalGeneration
        processor = AutoProcessor.from_pretrained(str(models), local_files_only=True)
        model = GlmOcrForConditionalGeneration.from_pretrained(str(models), local_files_only=True, dtype=dtype).to(device).eval()

        def read(image):
            messages = [{"role": "user", "content": [
                {"type": "image", "image": image.convert("RGB")},
                {"type": "text", "text": "Table Recognition:" if task == "table" else "Text Recognition:"},
            ]}]
            inputs = processor.apply_chat_template(
                messages, tokenize=True, add_generation_prompt=True, return_dict=True,
                return_tensors="pt",
            ).to(device)
            with torch.inference_mode():
                ids = model.generate(**inputs, max_new_tokens=4096, do_sample=False, use_cache=True, max_time=timeout_setting("FORMIX_OCR_PAGE_TIMEOUT", 180))
            return generation_status(processor.decode(ids[0][inputs["input_ids"].shape[-1]:], skip_special_tokens=True).strip(), ids, model.generation_config)
        return read

    if models.name == "dots-ocr":
        from transformers import AutoProcessor, AutoModelForCausalLM
        processor = AutoProcessor.from_pretrained(str(models), local_files_only=True, trust_remote_code=True)
        model = AutoModelForCausalLM.from_pretrained(str(models), local_files_only=True, trust_remote_code=True, dtype=dtype).to(device).eval()

        def read(image):
            page_image = image.convert("RGB")
            prompt = ("Extract the page layout in reading order as a JSON array. Each element must contain "
                      "bbox [x1,y1,x2,y2], category and text. Use HTML for tables and LaTeX for formulas. "
                      "Keep the original language and all visible text. Omit text for Picture elements.")
            messages = [{"role": "user", "content": [
                {"type": "image", "image": page_image},
                {"type": "text", "text": prompt},
            ]}]
            text = processor.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
            inputs = processor(text=[text], images=[page_image], padding=True, return_tensors="pt").to(device)
            with torch.inference_mode():
                ids = model.generate(**inputs, max_new_tokens=8192, do_sample=False, use_cache=True, max_time=timeout_setting("FORMIX_OCR_PAGE_TIMEOUT", 180))
            generated = [out[len(source):] for source, out in zip(inputs.input_ids, ids)]
            return generation_status(dots(processor.batch_decode(generated, skip_special_tokens=True)[0].strip(), page_image.size), ids, model.generation_config)
        return read

    processor = AutoProcessor.from_pretrained(str(models), local_files_only=True, trust_remote_code=True)
    model_class = AutoModelForImageTextToText
    if models.name == "paddleocr-vl-1.6":
        from transformers import AutoModelForCausalLM
        model_class = AutoModelForCausalLM
    model = model_class.from_pretrained(str(models), local_files_only=True, trust_remote_code=True, dtype=dtype).to(device).eval()

    if models.name == "paddleocr-vl-1.6":
        def read(image):
            table_task = task == 'table' or table_only_page(image)
            print('PaddleOCR-VL · ' + ('Table Recognition' if table_task else 'OCR'),
                  file=sys.stderr, flush=True)
            messages = [{"role": "user", "content": [
                {"type": "image", "image": image.convert("RGB")},
                {"type": "text", "text": "Table Recognition:" if table_task else "OCR:"},
            ]}]
            inputs = processor.apply_chat_template(
                messages, add_generation_prompt=True, tokenize=True, return_dict=True,
                return_tensors="pt",
                images_kwargs={"size": {"shortest_edge": processor.image_processor.min_pixels,
                                         "longest_edge": 1280 * 28 * 28}},
            ).to(device)
            with torch.inference_mode():
                ids = model.generate(**inputs, max_new_tokens=4096, do_sample=False, use_cache=True, max_time=timeout_setting("FORMIX_OCR_PAGE_TIMEOUT", 180))
            value = processor.decode(ids[0][inputs["input_ids"].shape[-1]:], skip_special_tokens=True).strip()
            if '<fcel>' in value and '<nl>' in value:
                # PaddleOCR-VL emits OTSL, including merged-cell markers, not HTML.
                from docling_core.types.doc import DoclingDocument
                from docling_core.types.doc.utils import parse_otsl_table_content
                document = DoclingDocument(name='Table')
                table_source = value
                if not table_source.lstrip().startswith('<'):
                    # Full-page OCR can omit the opening marker of the first cell.
                    table_source = '<fcel>' + table_source
                document.add_table(data=parse_otsl_table_content(table_source))
                value = docling_result(document, value, image.size)
            return generation_status(value, ids, model.generation_config)
        return read

    docling = models.name in {"smoldocling", "granite-docling-258m"}
    prompt = ("Convert this page to docling." if docling else
              ("Extract tables as Markdown, preserving their rows and columns." if task == "table" else
               "Transcribe all visible text exactly in reading order. Preserve line breaks and tables."))

    def read(image):
        messages = [{"role": "user", "content": [
            {"type": "image", "image": image.convert("RGB")},
            {"type": "text", "text": prompt},
        ]}]
        inputs = processor.apply_chat_template(
            messages, add_generation_prompt=True, tokenize=True, return_dict=True,
            return_tensors="pt",
        ).to(device)
        with torch.inference_mode():
            ids = model.generate(**inputs, max_new_tokens=8192 if docling else 4096,
                                 do_sample=False, use_cache=True, max_time=timeout_setting("FORMIX_OCR_PAGE_TIMEOUT", 180),
                                 stopping_criteria=generation_guard(inputs["input_ids"].shape[-1]))
        value = processor.decode(ids[0][inputs["input_ids"].shape[-1]:], skip_special_tokens=not docling).strip()
        if docling:
            from docling_core.types.doc import DoclingDocument
            from docling_core.types.doc.document import DocTagsDocument
            document = DocTagsDocument.from_doctags_and_image_pairs([value], [image])
            value = docling_result(DoclingDocument.load_from_doctags(document, document_name="Page"), value, image.size)
        return generation_status(value, ids, model.generation_config)
    return read

def raster(page):
    w,h = page.get_size()
    return page.render(scale=min(2,1800/max(w,h),math.sqrt(3_000_000/(w*h)))).to_pil().copy()

def report_pdf_progress(current,total):
    print(f"FORMIX_PROGRESS|pdf|{current}|{total}",file=sys.stderr,flush=True)


def markdown_table_rows(value):
    """Parse Markdown or DocTags HTML tables returned by OCR models."""
    rows = []
    for line in value.splitlines():
        stripped = line.strip()
        if stripped.startswith("|") and stripped.endswith("|"):
            cells = [cell.strip() for cell in stripped.strip("|").split("|")]
            if cells and all(not cell or set(cell) <= {"-", ":", " "} for cell in cells):
                continue
            rows.append(cells)
    if rows:
        return rows

    from html.parser import HTMLParser
    class TableParser(HTMLParser):
        def __init__(self):
            super().__init__()
            self.rows = []
            self.row = None
            self.cell = None
        def handle_starttag(self, tag, attrs):
            if tag.lower() == "tr":
                self.row = []
            elif tag.lower() in {"td", "th"} and self.row is not None:
                self.cell = []
                span = dict(attrs).get("colspan", "1") or "1"
                self.span = min(64, max(1, int(span))) if span.isascii() and span.isdigit() and len(span) < 4 else 1
        def handle_data(self, data):
            if self.cell is not None:
                self.cell.append(data)
        def handle_endtag(self, tag):
            tag = tag.lower()
            if tag in {"td", "th"} and self.cell is not None and self.row is not None:
                self.row.append("".join(self.cell).strip())
                self.row.extend([""] * (self.span - 1))
                self.cell = None
            elif tag == "tr" and self.row:
                self.rows.append(self.row)
                self.row = None
    parser = TableParser()
    parser.feed(value)
    return parser.rows


def pdf_to_excel(src, out, doc, models):
    import pdfplumber
    from openpyxl import Workbook

    workbook = Workbook()
    workbook.remove(workbook.active)
    table_count = 0
    reader = None
    model_ready = (models / "READY").is_file()
    missing_model_page = None
    with pdfplumber.open(src) as text_pdf:
        for page_index, page in enumerate(text_pdf.pages):
            page_tables = page.extract_tables() or []
            if not page_tables:
                page_text = (page.extract_text() or "").strip()
                if not page_text and not model_ready:
                    missing_model_page = page_index + 1
                    page.close()
                    report_pdf_progress(page_index + 1, len(text_pdf.pages))
                    continue
                if model_ready:
                    reader = reader or recognize(models, task="table")
                    if models.name == "deepseek-ocr":
                        print(f"DeepSeek-OCR · 正在识别第 {page_index + 1}/{len(text_pdf.pages)} 页", file=sys.stderr, flush=True)
                    rendered = doc[page_index]
                    try:
                        page_tables = [markdown_table_rows(reader(raster(rendered)))]
                    finally:
                        rendered.close()
                    page_tables = [rows for rows in page_tables if rows]
            for table_index, rows in enumerate(page_tables, 1):
                sheet = workbook.create_sheet(f"Page {page_index + 1} Table {table_index}"[:31])
                for row in rows:
                    sheet.append([csv_text(cell) for cell in row])
                    for cell in sheet[sheet.max_row]:
                        cell.data_type = "s"
                table_count += 1
            page.close()
            report_pdf_progress(page_index + 1, len(text_pdf.pages))
    if not table_count:
        workbook.close()
        if missing_model_page is not None:
            raise ValueError(tr("pdf_no_text", page=missing_model_page))
        raise ValueError(tr("pdf_no_tables"))
    workbook.save(out)
    workbook.close()


def write_pdf_text_line(document, line, page_width, previous_bottom):
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    from docx.shared import Pt
    chars = line.get("chars", [])
    text = line.get("text", "").strip()
    if not text:
        return line.get("bottom", previous_bottom)
    paragraph = document.add_paragraph()
    left, right = line.get("x0", 36), line.get("x1", page_width - 36)
    center = (left + right) / 2
    if abs(center - page_width / 2) < page_width * .07:
        paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
    elif left > page_width * .58:
        paragraph.alignment = WD_ALIGN_PARAGRAPH.RIGHT
    paragraph.paragraph_format.left_indent = Pt(max(0, left - 36))
    paragraph.paragraph_format.space_before = Pt(max(0, line.get("top", 0) - previous_bottom))
    sizes = [char.get("size", 10) for char in chars]
    default_size = sum(sizes) / len(sizes) if sizes else 10
    paragraph.paragraph_format.space_after = Pt(0)
    paragraph.paragraph_format.line_spacing = max(1, min(2, (line.get("bottom", 0) - line.get("top", 0)) /
                                                            max(default_size, 1)))
    if not chars:
        paragraph.add_run(text)
        return line.get("bottom", previous_bottom)
    groups = []
    for char in chars:
        style = (char.get("fontname", ""), round(char.get("size", 10), 1),
                 repr(char.get("non_stroking_color")))
        if groups and groups[-1][0] == style:
            groups[-1][1].append(char)
        else:
            groups.append((style, [char]))
    for _, group in groups:
        run = paragraph.add_run("".join(char.get("text", "") for char in group))
        name = group[0].get("fontname", "").split("+")[-1].lower()
        run.font.size = Pt(max(5, min(48, sum(c.get("size", 10) for c in group) / len(group))))
        if "simsun" in name or "song" in name:
            run.font.name = "SimSun"
        elif "simhei" in name or "heiti" in name:
            run.font.name = "SimHei"
        elif "kai" in name:
            run.font.name = "KaiTi"
        elif "arial" in name:
            run.font.name = "Arial"
        run.bold = "bold" in name or "hei" in name or default_size >= 16
        run.italic = "italic" in name or "oblique" in name
    return line.get("bottom", previous_bottom)


def write_pdf_grid(document, table):
    from docx.shared import Pt
    from docx.enum.table import WD_TABLE_ALIGNMENT, WD_CELL_VERTICAL_ALIGNMENT
    xs = sorted({round(x, 1) for cell in table.cells for x in (cell[0], cell[2])})
    ys = sorted({round(y, 1) for cell in table.cells for y in (cell[1], cell[3])})
    if len(xs) < 2 or len(ys) < 2 or (len(xs)-1)*(len(ys)-1) > 10000:
        return False
    grid = document.add_table(rows=len(ys)-1, cols=len(xs)-1)
    grid.style = "Table Grid"
    grid.alignment = WD_TABLE_ALIGNMENT.CENTER
    grid.autofit = False
    for index, column in enumerate(grid.columns):
        column.width = Pt(xs[index+1] - xs[index])
        for cell in column.cells:
            cell.width = column.width
    from docx.enum.table import WD_ROW_HEIGHT_RULE
    for index, row in enumerate(grid.rows):
        row.height = Pt(ys[index+1] - ys[index])
        row.height_rule = WD_ROW_HEIGHT_RULE.AT_LEAST
    for row, texts in zip(table.rows, table.extract()):
        for bounds, value in zip(row.cells, texts):
            if bounds is None:
                continue
            left, top, right, bottom = (round(v, 1) for v in bounds)
            r, c = ys.index(top), xs.index(left)
            end_r, end_c = ys.index(bottom)-1, xs.index(right)-1
            if end_r < r or end_c < c:
                continue
            cell = grid.cell(r,c)
            if (r,c) != (end_r,end_c):
                cell = cell.merge(grid.cell(end_r,end_c))
            cell.vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.CENTER
            para = cell.paragraphs[0]
            para.paragraph_format.space_after = Pt(0)
            para.paragraph_format.line_spacing = 1
            para.add_run(value or "").font.size = Pt(10)
    return True


def write_recognized_word(document, value):
    # Translate model markup to editable Word blocks.
    value = re.sub(r"<loc_\d+>", "", value)
    value = re.sub(r"<section_header(?:_level_(\d+))?>(.*?)</section_header[^>]*>",
                   lambda m: "\n" + "#" * min(6,int(m[1] or 1)) + " " + m[2] + "\n",
                   value, flags=re.S)
    value = re.sub(r"</(?:text|title|list_item|paragraph)>", "\n", value)
    for block in re.split(r"(<table\b.*?</table>|<otsl>.*?</otsl>|(?:^\s*\|[^\n]+\|[ \t]*(?:\n|$))+)",
                          value, flags=re.S | re.M):
        if block.lstrip().startswith('<table'):
            if __package__:
                from .pdf_word_layout import html_table
            else:
                from pdf_word_layout import html_table
            if html_table(document, block) is not None:
                continue
        rows = markdown_table_rows(block) if block.lstrip().startswith(("<table", "|")) else []
        if block.startswith("<otsl>"):
            rows = [re.split(r"<(?:fcel|ecel|ched|rhed|srow|lcel|ucel|xcel)>", row)[1:]
                    for row in block[6:-7].split("<nl>")]
            rows = [row for row in rows if row]
        if rows:
            grid = document.add_table(rows=0, cols=max(map(len, rows)))
            grid.style = "Table Grid"
            for row in rows:
                for cell, text in zip(grid.add_row().cells, row):
                    cell.text = text.strip()
            continue
        for line in re.sub(r"</?[a-zA-Z][^>]*>", "", block).splitlines():
            line = line.strip()
            heading = re.match(r"^(#{1,6})\s+(.+)", line)
            if heading:
                document.add_heading(heading[2], level=len(heading[1]))
            elif line:
                document.add_paragraph(line)


def pdf(src,out,models,image_format="PNG"):
    result = _pdf(src,out,models,image_format)
    if __package__:
        from .pdf_authorship import finalize_authorship
    else:
        from pdf_authorship import finalize_authorship
    finalize_authorship(src,out)
    return result


def _pdf(src,out,models,image_format="PNG"):
    if __package__:
        from .runtime_paths import use_worker_modules
    else:
        from runtime_paths import use_worker_modules
    use_worker_modules("pdf")
    import pypdfium2 as pdfium
    model_ready = (models / "READY").is_file()
    with pdfium.PdfDocument(str(src)) as doc:
        if model_ready and out.suffix.lower() in {'.docx', '.xlsx', '.csv', '.txt', '.md', '.html', '.pptx'}:
            if __package__:
                from .pdf_model import convert
            else:
                from pdf_model import convert
            return convert(doc, out, models, recognize, raster, report_pdf_progress, source=src)
        print('PDF · 原生提取 / 页面渲染（未调用模型）', file=sys.stderr, flush=True)
        if out.suffix.lower() == ".xlsx":
            pdf_to_excel(src, out, doc, models)
            return
        if out.suffix == ".pptx":
            from io import BytesIO
            from pptx import Presentation
            from pptx.util import Inches
            slides = Presentation()
            page = doc[0]
            width, height = page.get_size()
            page.close()
            slides.slide_width = Inches(10 * min(1, width / height))
            slides.slide_height = Inches(10 * min(1, height / width))
            for i, page in enumerate(doc):
                try:
                    image = raster(page)
                    scale = min(slides.slide_width / image.width, slides.slide_height / image.height)
                    w, h = round(image.width * scale), round(image.height * scale)
                    stream = BytesIO()
                    image.save(stream, "PNG")
                    slide = slides.slides.add_slide(slides.slide_layouts[6])
                    slide.shapes.add_picture(stream, (slides.slide_width-w)//2, (slides.slide_height-h)//2, w, h)
                finally:
                    page.close()
                report_pdf_progress(i+1, len(doc))
            slides.save(out)
            return
        if out.suffix == ".zip":
            with zipfile.ZipFile(out,"w") as archive:
                for i in range(len(doc)):
                    page = doc[i]
                    suffix = "jpg" if image_format == "JPEG" else "png"
                    with archive.open(f"page-{i+1:04}.{suffix}","w") as dest:
                        image = raster(page)
                        if image_format == "JPEG":
                            image.convert("RGB").save(dest, "JPEG", quality=92)
                        else:
                            image.save(dest, "PNG")
                    page.close()
                    report_pdf_progress(i+1,len(doc))
            return
        if out.suffix == ".csv":
            import pdfplumber
            count = 0
            with pdfplumber.open(src) as source, out.open("w",encoding="utf-8-sig",newline="") as stream:
                writer = csv.writer(stream)
                total=len(source.pages)
                for i,page in enumerate(source.pages,1):
                    for table in page.extract_tables():
                        writer.writerows([[csv_text(cell) for cell in row] for row in table])
                        count += 1
                    page.close()
                    report_pdf_progress(i,total)
            if not count:
                raise ValueError(tr("pdf_no_tables"))
            return
        from docx import Document
        word = Document() if out.suffix == ".docx" else None
        pdf_text = None
        if word is not None:
            import pdfplumber
            from docx.shared import Inches
            pdf_text = pdfplumber.open(src)
            section = word.sections[0]
            section.page_width = Inches(pdf_text.pages[0].width / 72)
            section.page_height = Inches(pdf_text.pages[0].height / 72)
            section.top_margin = Inches(.35)
            section.bottom_margin = Inches(.35)
            section.left_margin = Inches(.5)
            section.right_margin = Inches(.5)
        is_html = out.suffix == ".html"
        is_markdown = out.suffix == ".md"
        reader = None
        with out.with_suffix(".textpart").open("w",encoding="utf-8") as stream:
            if is_html:
                stream.write("<!doctype html>\n<html><head><meta charset=\"utf-8\">"
                             "<meta name=\"viewport\" content=\"width=device-width,initial-scale=1\">"
                             f"<title>{html.escape(tr('pdf_export_title'))}</title></head><body>\n")
            total=len(doc)
            for i in range(total):
                page = doc[i]
                textpage = page.get_textpage()
                value = textpage.get_text_bounded().strip()
                textpage.close()
                if not value:
                    if not (models/"READY").exists():
                        raise ValueError(tr("pdf_no_text",page=i+1))
                    reader = reader or recognize(models, task="word" if word is not None else "document")
                    if models.name == "deepseek-ocr":
                        print(f"DeepSeek-OCR · 正在识别第 {i + 1}/{total} 页", file=sys.stderr, flush=True)
                    value = reader(raster(page))
                if word is not None:
                    if i:
                        word.add_page_break()
                    source_page = pdf_text.pages[i]
                    lines = source_page.extract_text_lines(return_chars=True)
                    previous_bottom = 25
                    if lines:
                        tables = source_page.find_tables()
                        outside = source_page.filter(lambda obj: not any(
                            t.bbox[0] <= (obj["x0"]+obj["x1"])/2 < t.bbox[2] and
                            t.bbox[1] <= (obj["top"]+obj["bottom"])/2 < t.bbox[3]
                            for t in tables))
                        lines = outside.extract_text_lines(return_chars=True) if tables else lines
                        blocks = [(line["top"], False, line) for line in lines]
                        blocks.extend((t.bbox[1], True, t) for t in tables)
                        for _, is_table, block in sorted(blocks, key=lambda entry: entry[0]):
                            if is_table:
                                if not write_pdf_grid(word, block):
                                    for row in block.extract():
                                        word.add_paragraph("  ".join(cell or "" for cell in row))
                                previous_bottom = block.bbox[3]
                            else:
                                previous_bottom = write_pdf_text_line(
                                    word, block, source_page.width, previous_bottom)
                    else:
                        write_recognized_word(word, value)
                    source_page.close()
                elif is_html:
                    escaped = html.escape(value).replace("\n", "<br>\n")
                    stream.write(f"<section><p>{escaped}</p></section>\n")
                elif is_markdown:
                    if i:
                        stream.write("\n\n---\n\n")
                    stream.write(value + "\n")
                else:
                    stream.write(value+"\n")
                page.close()
                report_pdf_progress(i+1,total)
        if pdf_text is not None:
            pdf_text.close()
        if word is not None: word.save(out)
        else: out.with_suffix(".textpart").replace(out)

def image_output_formats():
    """Probe optional encoders in a worker, never in the GUI process."""
    if __package__:
        from .runtime_paths import load_vips
        from .engines import PAGES
    else:
        from runtime_paths import load_vips
        from engines import PAGES
    vips = load_vips()
    sample = vips.Image.black(2, 2, bands=3).copy(interpretation="srgb")
    sample.write_to_buffer('.png')
    formats = list(PAGES['图片转换'])
    for extension in ('heic', 'avif'):
        try:
            sample.write_to_buffer('.' + extension)
        except vips.Error:
            formats.remove(extension)
    return formats


def convert_image(src, out, mode=None, detail="original", preserve_metadata=True):
    if out.suffix.lower() == ".svg":
        if src.suffix.lower() != ".svg":
            raise ValueError("SVG 矢量输出目前支持 AI 和 SVG 文件；不将普通照片伪装成矢量图。")
        shutil.copyfile(src, out)
        return
    if __package__:
        from .runtime_paths import load_vips
    else:
        from runtime_paths import load_vips
    os.environ.setdefault("VIPS_CONCURRENCY", str(media_threads()))
    vips = load_vips()
    vips.cache_set_max_mem(32 * 1024 ** 2)
    keep = vips.enums.ForeignKeep
    options = {}
    if mode:
        if out.suffix == ".png":
            options["compression"] = {"quality": 3, "balanced": 6, "small": 9}[mode]
        elif out.suffix in {".jpg", ".jpeg"}:
            options.update(Q={"quality": 90, "balanced": 75, "small": 55}[mode], optimize_coding=True)
        else:
            options.update(Q={"quality": 90, "balanced": 75, "small": 55}[mode], effort=5, smart_subsample=True)

    if out.suffix.lower() == ".ico":
        from PIL import Image, ImageOps
        sizes = [int(size) for size in json.loads(sys.argv[5])] if len(sys.argv) > 5 else [32, 64, 128]
        allowed = {32, 64, 128}
        sizes = sorted(set(sizes) & allowed) or [32, 64, 128]
        image = vips.Image.new_from_file(str(src), access="sequential").autorot()
        if image.get_typeof("n-pages") and image.get("n-pages") > 1:
            image = vips.Image.new_from_file(str(src), access="sequential")
        image = image.colourspace("srgb")
        canvas_size = max(sizes)
        scale = min(1.0, canvas_size / max(image.width, image.height))
        if scale < 1:
            image = image.resize(scale, kernel="lanczos3")
        if image.hasalpha():
            image = image.cast("uchar")
        else:
            image = image.bandjoin(255).cast("uchar")
        pil = Image.frombytes("RGBA", (image.width, image.height), image.write_to_memory())
        # Pillow embeds a requested ICO size only when the source canvas is large enough.
        canvas = Image.new("RGBA", (canvas_size, canvas_size), (0, 0, 0, 0))
        canvas.alpha_composite(pil, ((canvas_size-pil.width)//2, (canvas_size-pil.height)//2))
        canvas.save(out, format="ICO", sizes=[(size, size) for size in sizes])
        return

    def save(flags):
        image = vips.Image.new_from_file(str(src), access="sequential")
        pages = image.get('n-pages') if image.get_typeof('n-pages') else 1
        if pages > 1:
            if mode or out.suffix.lower() not in {'.gif', '.webp', '.tif', '.tiff'}:
                raise ValueError(tr("static_images_only"))
            image = vips.Image.new_from_file(str(src), access="sequential", n=-1)
        image = image.autorot()
        scale = {"75": 0.75, "50": 0.5}.get(detail, 1.0)
        if scale < 1:
            image = image.resize(scale, kernel="lanczos3")
        if out.suffix.lower() in {".bmp", ".pdf"}:
            from PIL import Image
            image = image.colourspace("srgb")
            if image.hasalpha():
                image = image.flatten(background=[255, 255, 255])
            image = image.cast("uchar")
            pil = Image.frombytes("RGB", (image.width, image.height), image.write_to_memory())
            dpi = tuple(value * 25.4 for value in (image.xres, image.yres))
            dpi = dpi if all(math.isfinite(value) and value > 0 for value in dpi) else (72, 72)
            pil.save(out, format="BMP" if out.suffix.lower() == ".bmp" else "PDF", dpi=dpi)
            return
        if out.suffix in {".jpg", ".jpeg"} and image.hasalpha():
            image = image.flatten(background=[255])
        image.write_to_file(str(out), keep=flags if preserve_metadata else keep.NONE, **options)

    try:
        save(keep.ALL)
    except vips.Error as exc:
        reason = str(exc).lower()
        rejected = 0
        for field in ("exif", "xmp", "iptc", "icc", "gainmap"):
            if field in reason:
                rejected |= getattr(keep, field.upper(), 0)
        if not rejected and "metadata" not in reason:
            raise
        print(tr("metadata_retry"), file=sys.stderr, flush=True)
        out.unlink(missing_ok=True)
        vips.cache_set_max(0)
        save(keep.ALL & ~rejected if rejected else keep.NONE)


def ai_pdf(src, out):
    """Validate PDF-compatible Illustrator artwork and preserve its vector PDF data."""
    import pypdfium2 as pdfium
    try:
        with pdfium.PdfDocument(str(src)) as document:
            if len(document) < 1:
                raise ValueError("AI 文件中没有可读取的页面")
    except Exception as exc:
        raise ValueError("无法读取此 AI 文件。请在 Illustrator 保存时启用“创建 PDF 兼容文件”。") from exc
    shutil.copyfile(src, out)


def ai_svg(src, out):
    """Export PDF-compatible Illustrator vectors without rasterizing the artwork."""
    if __package__:
        from .runtime_paths import use_worker_modules
    else:
        from runtime_paths import use_worker_modules
    use_worker_modules("pdf")
    import pymupdf
    try:
        document = pymupdf.open(str(src), filetype="pdf")
    except Exception as exc:
        raise ValueError("无法读取此 AI 文件。请在 Illustrator 保存时启用“创建 PDF 兼容文件”。") from exc
    with document:
        if document.needs_pass:
            raise ValueError("AI 文件受密码保护，请先解除密码保护。")
        if document.page_count != 1:
            raise ValueError("AI 转 SVG 当前支持单画板文件，请将所需画板另存为单画板 AI 后转换。")
        # Outline glyphs to preserve the appearance even without the original fonts.
        svg = document[0].get_svg_image(text_as_path=True)
    out.write_text(svg, encoding="utf-8")


def ai_image(src, out, icon_sizes=None):
    """Rasterize PDF-compatible AI artboard 1 within a bounded memory budget."""
    import pypdfium2 as pdfium
    from PIL import Image, ImageOps
    try:
        with pdfium.PdfDocument(str(src)) as document:
            if len(document) < 1:
                raise ValueError("AI 文件中没有可读取的画板")
            page = document[0]
            width, height = page.get_size()
            scale = min(4.0, 4096/max(width, height), math.sqrt(12_000_000/(width*height)))
            image = page.render(scale=scale).to_pil().copy()
            page.close()
    except Exception as exc:
        raise ValueError("无法读取此 AI 文件。请在 Illustrator 保存时启用“创建 PDF 兼容文件”。") from exc
    if out.suffix.lower() == ".ico":
        sizes = [int(size) for size in (icon_sizes or [32, 64, 128])]
        canvas_size = max(sizes)
        contained = ImageOps.contain(image.convert("RGBA"), (canvas_size, canvas_size), Image.Resampling.LANCZOS)
        canvas = Image.new("RGBA", (canvas_size, canvas_size), (0, 0, 0, 0))
        canvas.alpha_composite(contained, ((canvas_size-contained.width)//2, (canvas_size-contained.height)//2))
        canvas.save(out, format="ICO", sizes=[(size, size) for size in sizes])
    elif out.suffix.lower() in {".jpg", ".jpeg"}:
        image.convert("RGB").save(out, format="JPEG", quality=95)
    elif out.suffix.lower() in {".avif", ".heic", ".heif"}:
        if __package__:
            from .runtime_paths import load_vips
        else:
            from runtime_paths import load_vips
        vips = load_vips()
        image.save(out.with_suffix(".png"), format="PNG")
        temp_png = out.with_suffix(".png")
        try:
            vips.Image.new_from_file(str(temp_png), access="sequential").write_to_file(str(out), Q=90)
        finally:
            temp_png.unlink(missing_ok=True)
    else:
        formats = {".png": "PNG", ".webp": "WEBP", ".bmp": "BMP", ".gif": "GIF", ".tif": "TIFF", ".tiff": "TIFF"}
        image.save(out, format=formats[out.suffix.lower()])


def image_ocr(source, output, models, mode="txt"):
    from PIL import Image, ImageOps, ImageSequence
    if not (models / 'READY').is_file():
        raise ValueError(f'请先在设置中下载 {models.name} 模型，再进行图片文字识别。')
    print(f'图片提取文字 · 模型：{models.name}', file=sys.stderr, flush=True)
    reader = recognize(models, task='document')
    texts = []
    with Image.open(source) as image:
        for frame in ImageSequence.Iterator(image):
            rgb = ImageOps.exif_transpose(frame).convert('RGB')
            text = str(reader(rgb)).strip()
            texts.append(text)
    result = '\n\n'.join(texts).strip()
    if not result:
        raise ValueError('未识别到文字，请使用清晰、方向正确的图片。')
    if mode == 'copy':
        import base64
        print('FORMIX_OCR_TEXT|' + base64.b64encode(result.encode('utf-8')).decode('ascii'), flush=True)
    else:
        output.write_text(result, encoding='utf-8-sig' if mode == 'txt' else 'utf-8')


if __name__ == "__main__":
    os.environ["HF_HUB_DISABLE_PROGRESS_BARS"] = "1"
    os.environ["TQDM_DISABLE"] = "1"
    try:
        action = sys.argv[1]
        if action == "office":
            if __package__:
                from .office_msi import prepare_local_office
            else:
                from office_msi import prepare_local_office
            print(tr("office_preparing"), flush=True)
            run_process([prepare_local_office(), *sys.argv[2:]], check=True,
                        timeout=timeout_setting('FORMIX_DOCUMENT_TIMEOUT', 3600))
        elif action == 'office-convert':
            out = Path(sys.argv[2])
            run_process(sys.argv[3:], check=True, timeout=timeout_setting('FORMIX_DOCUMENT_TIMEOUT', 3600))
            if out.suffix.lower() == '.html' and out.is_file():
                embed_html_assets(out)
        elif action == "ncm":
            if __package__:
                from .ncm import decrypt_to_cache
                from .runtime_paths import ncm_cache_dir
            else:
                from ncm import decrypt_to_cache
                from runtime_paths import ncm_cache_dir
            source = Path(sys.argv[2])
            cache = Path(sys.argv[3]) if len(sys.argv) > 3 else ncm_cache_dir()
            command = sys.argv[4:]
            progress_started = time.monotonic()
            progress_duration = ncm_minimum_progress_seconds()
            source_path = decrypt_to_cache(source, cache)
            print("FORMIX_NCM_READY", file=sys.stderr, flush=True)
            output = Path(command[-1])
            if source_path.suffix.lower() == output.suffix.lower():
                output.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(source_path), str(output))
            else:
                input_index = command.index("-i") + 1
                command[input_index] = str(source_path)
                run_process(command, check=True, timeout=timeout_setting('FORMIX_MEDIA_TIMEOUT', 24 * 3600))
            remaining = progress_started + progress_duration - time.monotonic()
            if remaining > 0:
                time.sleep(remaining)
        elif action == 'hls':
            if __package__:
                from .hls_input import materialize
            else:
                from hls_input import materialize
            command = sys.argv[3:]
            source_index = command.index('-i') + 1
            command[source_index] = str(materialize(command[source_index], Path(sys.argv[2])))
            run_process(command, check=True, timeout=timeout_setting('FORMIX_MEDIA_TIMEOUT', 24*3600))
        elif action == "size":
            revision, files = manifest(sys.argv[2])
            print(json.dumps([revision, sum(files.values())]))
        elif action == "download":
            download(Path(sys.argv[2]), sys.argv[3], sys.argv[4])
        elif action in ("image", "compress-image"):
            src, out = map(Path, sys.argv[2:4])
            convert_image(src, out, sys.argv[4] if action == "compress-image" else None,
                          sys.argv[5] if action == "compress-image" and len(sys.argv) > 5 else "original",
                          len(sys.argv) <= 6 or sys.argv[6] != "0")
        elif action == "ai-pdf":
            ai_pdf(Path(sys.argv[2]), Path(sys.argv[3]))
        elif action == "ai-svg":
            ai_svg(Path(sys.argv[2]), Path(sys.argv[3]))
        elif action == "ai-image":
            sizes = json.loads(sys.argv[4]) if len(sys.argv) > 4 else [32, 64, 128]
            ai_image(Path(sys.argv[2]), Path(sys.argv[3]), sizes)
        elif action == "image-ocr":
            image_ocr(*map(Path, sys.argv[2:5]), mode=sys.argv[5] if len(sys.argv)>5 else "txt")
        elif action == "pdf":
            src,out,models = map(Path,sys.argv[2:5])
            pdf(src,out,models,*sys.argv[5:])
    except Exception as exc:
        print(str(exc),file=sys.stderr)
        sys.exit(1)

