"""Editable Word layout using PDF geometry or model-provided regions."""
from io import BytesIO
import json
import re
from html.parser import HTMLParser

from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Pt


def element(tag, **attrs):
    node = OxmlElement('w:' + tag)
    for key, value in attrs.items():
        node.set(qn('w:' + key), str(value))
    return node


def position(paragraph, x, y, width):
    paragraph._p.get_or_add_pPr().append(element(
        'framePr', x=round(x*20), y=round(y*20), w=round(width*20),
        hAnchor='page', vAnchor='page', wrap='notBeside', hSpace=0, vSpace=0))
    fmt = paragraph.paragraph_format
    fmt.space_before = fmt.space_after = Pt(0)
    fmt.line_spacing = 1


def font_run(paragraph, text, name='SimSun', size=12, bold=False, color=None):
    run = paragraph.add_run(text)
    name = name.split('+')[-1]
    aliases = {'STFangsong': '华文仿宋', 'SimSun': '宋体', 'SimHei': '黑体'}
    run.font.name = aliases.get(name, name)
    run._element.get_or_add_rPr().rFonts.set(qn('w:eastAsia'), run.font.name)
    run.font.size = Pt(size)
    run.bold = bold or 'Bold' in name
    if isinstance(color, (tuple, list)) and len(color) == 3:
        from docx.shared import RGBColor
        run.font.color.rgb = RGBColor(*(max(0, min(255, round(c*255))) for c in color))
    return run


def annotate_pdf_emphasis(source, pages):
    """PDF faux bold is a stroked glyph, even when the font is named Regular."""
    import pymupdf
    with pymupdf.open(str(source)) as pdf:
        for index,page in enumerate(pages):
            strokes = [(glyph[0],glyph[2][0],(glyph[3][1]+glyph[3][3])/2)
                       for span in pdf[index].get_texttrace() if span['type'] == 1
                       for glyph in span['chars']]
            for char in page.chars:
                text = char.get('text','')
                if len(text) != 1:
                    continue
                center = (char['top']+char['bottom'])/2
                char['formix_bold'] = any(code == ord(text) and abs(x-char['x0']) < .8
                                         and abs(y-center) < 4 for code,x,y in strokes)


def fixed_pdf_spacing(paragraph):
    # Word/WPS otherwise insert extra spacing between Chinese and numbers,
    # which pushes dates onto an extra line even with the correct font size.
    props = paragraph._p.get_or_add_pPr()
    for tag in ('autoSpaceDE','autoSpaceDN','snapToGrid','widowControl'):
        props.append(element(tag,val=0))


def native_lines(container, chars, origin=(0, 0), absolute=True):
    """Keep original baselines, font runs and horizontal gaps."""
    groups = []
    for char in sorted(chars, key=lambda c: (round(c['top'], 1), c['x0'])):
        if not groups or abs(char['top']-groups[-1][0]['top']) > 2:
            groups.append([])
        groups[-1].append(char)
    if absolute:
        fragments = []
        for group in groups:
            fragment = []
            for char in sorted(group, key=lambda c:c['x0']):
                if char.get('text','').isspace():
                    if fragment:
                        fragments.append(fragment)
                        fragment = []
                    continue
                if fragment and char['x0']-fragment[-1]['x1'] > 2:
                    fragments.append(fragment)
                    fragment = []
                fragment.append(char)
            if fragment:
                fragments.append(fragment)
        groups = fragments
    # A first-line indent followed by flush-left lines is one paragraph,
    # not a sequence of paragraphs. Keep headings and numbered items separate.
    paragraphs = []
    for group in groups:
        group.sort(key=lambda c: c['x0'])
        join = False
        if not absolute and paragraphs:
            first, last = paragraphs[-1][0], paragraphs[-1][-1]
            size = max(c['size'] for c in first)
            text = ''.join(c.get('text', '') for c in group).lstrip()
            join = (first[0]['x0']-group[0]['x0'] >= size*.8
                    and abs(group[0]['x0']-origin[0]) < size*.6
                    and abs(max(c['size'] for c in group)-size) < .5
                    and size*.8 < group[0]['top']-last[0]['top'] < size*2.5
                    and not re.match(r'^(?:\d+[.、]|[（(]|[一二三四五六七八九十]+、)', text))
        if join:
            paragraphs[-1].append(group)
        else:
            paragraphs.append([group])
    previous = origin[1]
    for lines in paragraphs:
        group = lines[0]
        group.sort(key=lambda c: c['x0'])
        first = group[0]
        p = container.add_paragraph()
        fixed_pdf_spacing(p)
        size = max(c['size'] for c in group)
        if absolute:
            position(p, first['x0'], first['top']-size*.12,
                     max(c['x1'] for c in group)-first['x0']+8)
            p.paragraph_format.line_spacing = Pt(size)
        else:
            p.paragraph_format.space_before = Pt(max(0, first['top']-previous))
            p.paragraph_format.space_after = Pt(0)
            p.paragraph_format.line_spacing = Pt(size)
            p.paragraph_format.left_indent = Pt(max(0, first['x0']-origin[0]))
            if len(lines) > 1:
                indent = max(0, lines[1][0]['x0']-origin[0])
                p.paragraph_format.left_indent = Pt(indent)
                p.paragraph_format.first_line_indent = Pt(first['x0']-origin[0]-indent)
                leading = lines[1][0]['top']-first['top']
                p.paragraph_format.line_spacing = Pt(leading)
                p.paragraph_format.space_before = Pt(max(0, first['top']-previous-(leading-size)))
        # No hard break between wrapped lines: Word can reflow the date as a unit.
        group = [char for line in lines for char in line]
        last = first['x0']
        for char in group:
            gap = char['x0'] - last
            if gap > size*.6:
                # PDF often positions glyphs individually. Tabs can jump forward when
                # substituted font metrics differ, wrapping an otherwise fitting line.
                font_run(p, ' ' * max(1, round(gap/(size*.5))), first['fontname'], size)
            font_run(p, char.get('text', ''), char['fontname'], char['size'],
                     bold=char.get('formix_bold',False), color=char.get('non_stroking_color'))
            last = char['x1']
        previous = lines[-1][0]['top']+size


def native_table(document, table, page):
    # Snap PDF ruling coordinates; subpoint duplicates otherwise create phantom columns.
    def cluster(values):
        result = []
        for value in sorted(values):
            if not result or value-result[-1] > 2:
                result.append(value)
        return result
    xs = cluster([v for cell in table.cells for v in (cell[0], cell[2])])
    ys = cluster([v for cell in table.cells for v in (cell[1], cell[3])])
    grid = document.add_table(rows=len(ys)-1, cols=len(xs)-1)
    grid.style = 'Table Grid'
    grid.autofit = False
    props = grid._tbl.tblPr
    props.append(element('tblpPr', horzAnchor='page', vertAnchor='page',
                         tblpX=round(xs[0]*20), tblpY=round(ys[0]*20),
                         leftFromText=0, rightFromText=0, topFromText=0, bottomFromText=0))
    margins = element('tblCellMar')
    for edge in ('top', 'left', 'bottom', 'right'):
        margins.append(element(edge, w=0, type='dxa'))
    props.append(margins)
    for i, col in enumerate(grid.columns):
        col.width = Pt(xs[i+1]-xs[i])
        for cell in col.cells:
            cell.width = col.width
    from docx.enum.table import WD_ROW_HEIGHT_RULE
    for i, row in enumerate(grid.rows):
        row.height = Pt(ys[i+1]-ys[i])
        row.height_rule = WD_ROW_HEIGHT_RULE.AT_LEAST
        row._tr.get_or_add_trPr().append(element('cantSplit'))
    near = lambda values, value: min(range(len(values)), key=lambda i: abs(values[i]-value))
    for x0, y0, x1, y1 in table.cells:
        r, c = near(ys,y0), near(xs,x0)
        r1, c1 = near(ys,y1)-1, near(xs,x1)-1
        if r1 < r or c1 < c:
            continue
        cell = grid.cell(r,c)
        if r1 != r or c1 != c:
            cell = cell.merge(grid.cell(r1,c1))
        chars = [ch for ch in page.chars if x0 <= (ch['x0']+ch['x1'])/2 < x1
                 and y0 <= (ch['top']+ch['bottom'])/2 < y1]
        native_lines(cell, chars, (x0,y0), absolute=False)
        if len(cell.paragraphs) > 1:
            cell._tc.remove(cell.paragraphs[0]._p)
    return grid


def native_page(document, page, image):
    tables = page.find_tables()
    inside = lambda c, box: box[0] <= (c['x0']+c['x1'])/2 <= box[2] and box[1] <= (c['top']+c['bottom'])/2 <= box[3]
    native_lines(document, [c for c in page.chars if not any(inside(c,t.bbox) for t in tables)])
    for table in tables:
        native_table(document, table, page)
    for picture in page.images:
        x0,y0,x1,y1 = picture['x0'],picture['top'],picture['x1'],picture['bottom']
        if x1-x0 < 2 or y1-y0 < 2:
            continue
        crop = image.crop((x0/page.width*image.width,y0/page.height*image.height,
                           x1/page.width*image.width,y1/page.height*image.height))
        stream = BytesIO()
        crop.save(stream,'PNG');stream.seek(0)
        p = document.add_paragraph()
        position(p,x0,y0,x1-x0+20)
        p.add_run().add_picture(stream,width=Pt(x1-x0),height=Pt(y1-y0))
    # Form underlines are PDF vector strokes, not text characters.
    for line in page.lines:
        if abs(line['top']-line['bottom']) > .5 or line['x1']-line['x0'] < 3:
            continue
        if any(t.bbox[0]-.5 <= line['x0'] <= t.bbox[2]+.5 and
               t.bbox[1]-.5 <= line['top'] <= t.bbox[3]+.5 for t in tables):
            continue
        p = document.add_paragraph()
        position(p,line['x0'],line['top']-1,line['x1']-line['x0'])
        p.paragraph_format.line_spacing = Pt(1)
        p.add_run(' ').font.size = Pt(1)
        borders = element('pBdr')
        borders.append(element('bottom',val='single',sz=max(2,round(line.get('linewidth',.5)*8)),space=0,color='000000'))
        p._p.get_or_add_pPr().append(borders)


class HTMLTable(HTMLParser):
    def __init__(self):
        super().__init__()
        self.rows = []
        self.cell = None
    def handle_starttag(self,tag,attrs):
        attrs = dict(attrs)
        if tag == 'tr':
            self.rows.append([])
        if tag in ('td','th'):
            if not self.rows:
                self.rows.append([])
            def span(key):
                try:
                    return max(1, min(200, int(attrs.get(key, 1))))
                except (ValueError, TypeError):
                    return 1
            self.cell = dict(text='',rowspan=span('rowspan'),colspan=span('colspan'))
            self.rows[-1].append(self.cell)
        if tag == 'br' and self.cell is not None:
            self.cell['text'] += '\n'
    def handle_data(self,value):
        if self.cell is not None:
            self.cell['text'] += value
    def handle_endtag(self,tag):
        if tag in ('td','th'):
            self.cell = None


def table_layout(value):
    parser = HTMLTable()
    parser.feed(value)
    occupied = set()
    cells = []
    for r,row in enumerate(parser.rows):
        c = 0
        for cell in row:
            while (r,c) in occupied:
                c += 1
            rs,cs = cell['rowspan'],cell['colspan']
            if (r+rs)*(c+cs) > 10000:
                raise ValueError('模型表格尺寸异常')
            cells.append((r,c,rs,cs,cell['text']))
            occupied.update((rr,cc) for rr in range(r,r+rs) for cc in range(c,c+cs))
            c += cs
    return cells


def html_table(document, value):
    cells = table_layout(value)
    if not cells:
        return None
    grid = document.add_table(rows=max(r+rs for r,c,rs,cs,t in cells),
                              cols=max(c+cs for r,c,rs,cs,t in cells))
    grid.style = 'Table Grid'
    for r,c,rs,cs,text in cells:
        cell = grid.cell(r,c)
        if rs > 1 or cs > 1:
            cell = cell.merge(grid.cell(r+rs-1,c+cs-1))
        cell.text = text.strip()
    return grid


def place_table(grid, box, page_size):
    import math
    from docx.enum.table import WD_ROW_HEIGHT_RULE
    x0,y0,x1,y1 = box
    width,height = page_size
    grid.autofit = False
    grid._tbl.tblPr.append(element('tblpPr', horzAnchor='page', vertAnchor='page',
                                  tblpX=round(x0*width*20), tblpY=round(y0*height*20),
                                  leftFromText=0, rightFromText=0, topFromText=0, bottomFromText=0))
    for column in grid.columns:
        column.width = Pt((x1-x0)*width/len(grid.columns))
    weights = []
    for row in grid.rows:
        row_weight = 1
        seen = set()
        for cell in row.cells:
            if cell._tc in seen:
                continue
            seen.add(cell._tc)
            cell_width = (x1-x0)*width/len(grid.columns)*cell._tc.grid_span
            cell.width = Pt(cell_width)
            row_weight = max(row_weight, sum(max(1,math.ceil(len(line)*7/max(10,cell_width-8)))
                                             for line in cell.text.splitlines()))
            for paragraph in cell.paragraphs:
                paragraph.paragraph_format.space_after = Pt(0)
                for run in paragraph.runs:
                    run.font.size = Pt(10)
        weights.append(row_weight)
    for row, weight in zip(grid.rows, weights):
        row.height = Pt((y1-y0)*height*weight/max(1,sum(weights)))
        row.height_rule = WD_ROW_HEIGHT_RULE.AT_LEAST


def add_provenance(document, records):
    """Embed raw OCR/geometry in the DOCX package, without adding visible pages."""
    from docx.opc.part import Part
    from docx.opc.packuri import PackURI
    from docx.opc.constants import RELATIONSHIP_TYPE as RT
    from xml.etree.ElementTree import Element, tostring
    root = Element('formix-recognition', {'version':'1'})
    root.text = json.dumps(records, ensure_ascii=False)
    part = Part(PackURI('/customXml/formix-recognition.xml'), 'application/xml',
                tostring(root, encoding='utf-8', xml_declaration=True), document.part.package)
    document.part.relate_to(part, RT.CUSTOM_XML)


def repair_table_grids(document):
    """pdf2docx sets cell widths but leaves equal grid columns; Writer uses the grid."""
    import numpy as np
    for table in document.tables:
        count = len(table.columns)
        equations, widths = [], []
        for row in table._tbl.tr_lst:
            col = 0
            for cell in row.tc_lst:
                span = cell.grid_span
                if cell.width is not None and col+span <= count:
                    equations.append([1 if col <= i < col+span else 0 for i in range(count)])
                    widths.append(cell.width.pt)
                col += span
        if not equations:
            continue
        result, _, rank, _ = np.linalg.lstsq(equations, widths, rcond=None)
        if rank != count or min(result) <= 0 or max(abs(np.array(equations) @ result-widths)) > 1:
            continue
        for column, width in zip(table.columns, result):
            column.width = Pt(float(width))
        table.autofit = False
        total = table._tbl.tblPr.find(qn('w:tblW'))
        total.set(qn('w:type'), 'dxa')
        total.set(qn('w:w'), str(round(sum(result)*20)))


def restore_native_cells(document, pages, layout):
    """Use parsed cell geometry, avoiding ambiguous repeated text matching."""
    from docx.enum.table import WD_CELL_VERTICAL_ALIGNMENT
    from docx.enum.table import WD_ROW_HEIGHT_RULE
    tables = []
    for item in layout['pages']:
        for section in item['sections']:
            for column in section['columns']:
                for block in column['blocks']:
                    if 'rows' in block:
                        tables.append((pages[item['id']],block))
    if len(tables) != len(document.tables):
        return
    for table,(page,source) in zip(document.tables,tables):
        for row in table.rows:
            # Never hide the last numbered item if a reader substitutes a font.
            row.height_rule = WD_ROW_HEIGHT_RULE.AT_LEAST
        seen = set()
        for r,row in enumerate(source['rows']):
            for c,original in enumerate(row['cells']):
                if not original or not original.get('bbox'):
                    continue
                x0,y0,x1,y1 = original['bbox']
                if x1 <= x0 or y1 <= y0:
                    continue
                cell = table.cell(r,c)
                if cell._tc in seen:
                    continue
                seen.add(cell._tc)
                chars = [ch for ch in page.chars if x0-.5 <= (ch['x0']+ch['x1'])/2 < x1+.5
                         and y0-.5 <= (ch['top']+ch['bottom'])/2 < y1+.5]
                if not chars:
                    continue
                cell.vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.TOP
                props = cell._tc.get_or_add_tcPr()
                for old in list(props.findall(qn('w:tcMar'))):
                    props.remove(old)
                margins = element('tcMar')
                for edge in ('top','left','bottom','right'):
                    margins.append(element(edge,w=0,type='dxa'))
                props.append(margins)
                props.append(element('noWrap'))
                for p in list(cell.paragraphs):
                    cell._tc.remove(p._p)
                native_lines(cell, chars, (x0,y0), absolute=False)


def restore_native_text_pages(document, pages, images):
    """Replace free text flow with editable positioned paragraphs on non-table pages."""
    from PIL import Image
    body = document._element.body
    groups, current = [], []
    for child in list(body):
        if child.tag == qn('w:sectPr'):
            if current:
                groups.append(current)
            break
        current.append(child)
        if child.find('./'+qn('w:pPr')+'/'+qn('w:sectPr')) is not None:
            groups.append(current)
            current = []
    if len(groups) != len(pages):
        return
    for index,(page,group) in enumerate(zip(pages,groups)):
        if page.find_tables():
            continue
        existing = set(body)
        anchor = document.add_paragraph()
        anchor.paragraph_format.line_spacing = Pt(1)
        anchor.paragraph_format.space_after = Pt(0)
        with Image.open(BytesIO(images[index])) as image:
            native_page(document,page,image)
        added = [child for child in body if child not in existing]
        for child in added:
            group[0].addprevious(child)
        for child in group:
            if child.find('./'+qn('w:pPr')+'/'+qn('w:sectPr')) is None:
                body.remove(child)
