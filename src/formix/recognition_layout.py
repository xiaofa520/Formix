"""Model output with provenance; coordinates are normalized to a top-left page."""
import ast
import json
import re
from collections import Counter


def quality_warnings(text):
    # Repeated long prose is usually a degenerate generation, not an empty form cell.
    chunks = re.split(r'<[^>]+>|\n', text)
    counts = Counter(re.sub(r'\s+', '', item) for item in chunks)
    repeated = any((len(item) >= 20 and n >= 5) or (len(item) >= 8 and n >= 8)
                   for item,n in counts.items())
    return ['模型出现多次重复内容，请核对识别结果'] if repeated else []


class Recognition(str):
    def __new__(cls, text, *, regions=None, raw=None, structured=None, warnings=None):
        value = super().__new__(cls, text)
        value.regions = regions or []
        value.raw = text if raw is None else raw
        value.structured = structured
        value.warnings = warnings or []
        return value


def generation_status(value, ids, tokenizer):
    result = value if isinstance(value, Recognition) else Recognition(value)
    eos = tokenizer.eos_token_id
    eos = eos if isinstance(eos, (list,tuple)) else [eos]
    if int(ids[0][-1]) not in eos:
        result.warnings.append('模型达到生成时间、长度或重复上限，识别结果可能不完整')
    return result


def table_only_page(image):
    """Use the table prompt only for a ruled table with no meaningful outside text."""
    try:
        import cv2
        import numpy as np
    except ImportError:
        return False
    gray = cv2.cvtColor(np.asarray(image.convert('RGB')), cv2.COLOR_RGB2GRAY)
    ink = cv2.threshold(gray, 180, 255, cv2.THRESH_BINARY_INV)[1]
    height,width = gray.shape
    horizontal = cv2.morphologyEx(ink, cv2.MORPH_OPEN,
                                np.ones((1,max(30,width//25)),np.uint8))
    vertical = cv2.morphologyEx(ink, cv2.MORPH_OPEN,
                              np.ones((max(30,height//35),1),np.uint8))
    if not vertical.any() or not horizontal.any():
        return False
    contours,_ = cv2.findContours(horizontal | vertical,cv2.RETR_EXTERNAL,cv2.CHAIN_APPROX_SIMPLE)
    for contour in contours:
        x,y,w,h = cv2.boundingRect(contour)
        if w*h < width*height*.4:
            continue
        row_hits = np.count_nonzero(horizontal[y:y+h,x:x+w],axis=1) > w*.25
        runs = np.count_nonzero(np.diff(np.r_[False,row_hits,False].astype(int)) == 1)
        if runs < 3:
            continue
        outside = ink.copy()
        outside[max(0,y-8):min(height,y+h+8),max(0,x-8):min(width,x+w+8)] = 0
        if np.count_nonzero(outside) < width*height*.0005:
            return True
    return False


def region(label, box, text, width=1, height=1):
    if not isinstance(box, (list, tuple)) or len(box) != 4:
        return None
    try:
        x0, y0, x1, y1 = [float(v) / (width if i % 2 == 0 else height)
                          for i, v in enumerate(box)]
        if not (0 <= x0 < x1 <= 1.01 and 0 <= y0 < y1 <= 1.01):
            return None
        return dict(label=str(label), bbox=[x0, y0, min(1, x1), min(1, y1)], text=str(text))
    except (ValueError, TypeError, ZeroDivisionError):
        return None


def grounded(value):
    pattern = r'<\|ref\|>(.*?)<\|/ref\|>\s*<\|det\|>(.*?)<\|/det\|>'
    matches = list(re.finditer(pattern, value, re.S))
    regions = []
    for index, match in enumerate(matches):
        text = value[match.end():matches[index+1].start() if index+1 < len(matches) else len(value)].strip()
        try:
            boxes = ast.literal_eval(match[2])
            if boxes and isinstance(boxes[0], (int, float)):
                boxes = [boxes]
            for box in boxes:
                item = region(match[1], box, text, 999, 999)
                if item:
                    regions.append(item)
        except (ValueError, SyntaxError, TypeError):
            continue
    return Recognition(re.sub(pattern, '', value, flags=re.S).strip(), regions=regions, raw=value)


def dots(value, size):
    source = value.strip()
    if source.startswith(chr(96)*3):
        source = source.split('\n', 1)[-1].rsplit(chr(96)*3, 1)[0]
    items = json.loads(source)
    if isinstance(items, dict):
        items = items.get('layout', items.get('blocks', items.get('elements', [items])))
    regions = [region(b.get('category', 'text'), b.get('bbox'), b.get('text', ''), *size)
               for b in items if isinstance(b, dict)]
    return Recognition('\n\n'.join(str(b.get('text', '')) for b in items if isinstance(b, dict)),
                       regions=[r for r in regions if r], raw=value, structured=items)


def docling_result(document, raw, size):
    regions = []
    content = []
    for item, _ in document.iterate_items():
        label = str(item.label.value)
        text = item.export_to_html(doc=document) if label == 'table' else getattr(item, 'text', '')
        if text:
            content.append(text)
        for prov in item.prov:
            box = prov.bbox.to_top_left_origin(page_height=size[1])
            entry = region(label, [box.l, box.t, box.r, box.b], text, *size)
            if entry:
                regions.append(entry)
    return Recognition('\n\n'.join(content), regions=regions, raw=raw,
                       structured=document.export_to_dict())
