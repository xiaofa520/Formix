"""CPU-only page OCR with optional reconstruction of visible ruled tables."""
from bisect import bisect_left
from html import escape
if __package__:
    from .recognition_layout import Recognition, region
else:
    from recognition_layout import Recognition, region


def clustered(values, tolerance=5):
    groups = []
    for value in sorted(values):
        if not groups or value - groups[-1][0] > tolerance:
            groups.append([])
        groups[-1].append(value)
    return [round(sum(group) / len(group)) for group in groups]


def ruled_tables(rgb, lines):
    import cv2
    import numpy as np

    gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
    ink = cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_MEAN_C,
                                cv2.THRESH_BINARY_INV, 21, 12)
    height, width = gray.shape
    horizontal = cv2.morphologyEx(ink, cv2.MORPH_OPEN, np.ones((1, max(24, width // 30)), np.uint8))
    vertical = cv2.morphologyEx(ink, cv2.MORPH_OPEN, np.ones((max(20, height // 70), 1), np.uint8))
    contours, hierarchy = cv2.findContours(horizontal | vertical, cv2.RETR_CCOMP,
                                            cv2.CHAIN_APPROX_SIMPLE)
    cells_by_outline = {}
    if hierarchy is not None:
        for contour, node in zip(contours, hierarchy[0]):
            x, y, w, h = cv2.boundingRect(contour)
            if node[3] >= 0 and w >= 14 and h >= 12:
                cells_by_outline.setdefault(int(node[3]), []).append((x, y, w, h))

    used = set()
    blocks = []
    for cells in cells_by_outline.values():
        if len(cells) < 3:
            continue
        xs = clustered([x for x, _, _, _ in cells])
        ys = clustered([y for _, y, _, _ in cells])
        if min(len(xs), len(ys)) < 2:
            continue
        rows = [{} for _ in ys]
        matched = set()
        for x, y, w, h in cells:
            row = bisect_left(ys, y - 5)
            col = bisect_left(xs, x - 5)
            span = max(1, bisect_left(xs, x + w - 5) - col)
            rowspan = max(1, bisect_left(ys, y + h - 5) - row)
            content = []
            rows[row][col] = (span, rowspan, content)
            for i, (cx, cy, text) in enumerate(lines):
                if x <= cx < x + w and y <= cy < y + h:
                    content.append(escape(text))
                    matched.add(i)
        if matched:
            used.update(matched)
            html = []
            covered = set()
            for row_index, row in enumerate(rows):
                col = 0
                html.append("<tr>")
                while col < len(xs):
                    if (row_index,col) in covered:
                        col += 1
                        continue
                    span, rowspan, content = row.get(col, (1, 1, []))
                    html.append(f'<td colspan="{span}" rowspan="{rowspan}">' + " ".join(content) + "</td>")
                    covered.update((r,c) for r in range(row_index+1,row_index+rowspan)
                                   for c in range(col,col+span))
                    col += span
                html.append("</tr>")
            blocks.append((ys[0], '<table data-formix-grid="1">' + "".join(html) + "</table>"))
    return blocks, used


def make_reader(models, task):
    import numpy as np
    from rapidocr import RapidOCR

    engine = RapidOCR(params={
        "Global.use_cls": False,
        "Det.model_path": str(models / "PP-OCRv5_mobile_det.onnx"),
        "Rec.model_path": str(models / "PP-OCRv5_mobile_rec.onnx"),
        "Rec.rec_keys_path": str(models / "characters.txt"),
        "EngineConfig.onnxruntime.intra_op_num_threads": 2,
        "EngineConfig.onnxruntime.inter_op_num_threads": 1,
    })

    def read(image):
        rgb = np.asarray(image.convert("RGB"))
        result = engine(image.convert("RGB"), use_cls=False)
        if not result.txts:
            return ""
        lines = [(float(box[:, 0].mean()), float(box[:, 1].mean()), text)
                 for box, text in zip(result.boxes, result.txts)]
        regions = [region('text', [float(box[:,0].min()),float(box[:,1].min()),
                                  float(box[:,0].max()),float(box[:,1].max())], text, *image.size)
                   for box,text in zip(result.boxes,result.txts)]
        def result_text(text, use_regions=True):
            return Recognition(text, regions=[r for r in regions if r] if use_regions else [],
                               structured={'ocr_regions':[r for r in regions if r]})
        if task not in {"word", "table"}:
            return result_text("\n".join(text for _, _, text in lines))
        tables, used = ruled_tables(rgb, lines)
        if task == "table":
            return result_text("\n".join(value for _, value in sorted(tables)), False)
        if not tables:
            return result_text("\n".join(text for _, _, text in lines))
        blocks = tables + [(y, text) for i, (_, y, text) in enumerate(lines) if i not in used]
        return result_text("\n".join(value for _, value in sorted(blocks, key=lambda item: item[0])), False)

    return read
