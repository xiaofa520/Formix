"""Normalize OCR output before serializing editable PDF document exports."""
import csv
import html
import json
import re
import sys
from io import BytesIO
from html.parser import HTMLParser


class Text(HTMLParser):
    def __init__(self):
        super().__init__()
        self.parts = []

    def handle_data(self, value):
        self.parts.append(value)

    def handle_endtag(self, tag):
        if tag in {'p', 'div', 'tr', 'table'}:
            self.parts.append('\n')


def plain(value):
    parser = Text()
    parser.feed(value)
    return ''.join(parser.parts).strip()


def normalize(value, key):
    if not isinstance(value, str):
        raise ValueError(f'{key}: 模型未返回文字结果')
    value = re.sub(r'^\s*```(?:json|markdown|html)?\s*\n|\n```\s*$', '', value.strip())
    if key == 'dots-ocr' and value.lstrip().startswith(('[', '{')):
        blocks = json.loads(value)
        if isinstance(blocks, dict):
            blocks = blocks.get('layout', blocks.get('blocks', blocks.get('elements', [blocks])))
        value = '\n\n'.join(str(block.get('text', '')) for block in blocks if isinstance(block, dict))
    value = re.sub(r'<\|ref\|>.*?<\|/ref\|>\s*<\|det\|>.*?<\|/det\|>', '', value, flags=re.S)
    value = re.sub(r'<\|(?:endoftext|eos|im_end)\|>', '', value)
    if not value.strip():
        raise ValueError(f'{key}: 模型返回空内容，未生成成功文件')
    return value.strip()


def blocks(value, table_parser):
    """Keep separate tables separate, instead of joining every row on a page."""
    pattern = r'(<table\b.*?</table>|(?:^\s*\|[^\n]+\|[ \t]*(?:\n|$))+)'
    for part in re.split(pattern, value, flags=re.S | re.M):
        if not part.strip():
            continue
        rows = table_parser(part) if part.lstrip().startswith(('<table', '|')) else []
        yield ('table', rows) if rows else ('text', plain(part))


def convert(doc, out, models, recognize, raster, progress, source=None):
    result = _convert(doc,out,models,recognize,raster,progress,source)
    if __package__:
        from .pdf_authorship import finalize_authorship
    else:
        from pdf_authorship import finalize_authorship
    finalize_authorship(source,out,author=None if source else doc.get_metadata_value('Author').strip())
    return result


def _convert(doc, out, models, recognize, raster, progress, source=None):
    if __package__:
        from .worker import markdown_table_rows, write_recognized_word
        from .output_safety import csv_text
        from .recognition_layout import quality_warnings
    else:
        from worker import markdown_table_rows, write_recognized_word
        from output_safety import csv_text
        from recognition_layout import quality_warnings
    extension = out.suffix.lower()
    print(f'PDF · 模型识别：{models.name} → {extension}', file=sys.stderr, flush=True)
    task = 'table' if extension in {'.xlsx', '.csv'} else 'word'
    reader = recognize(models, task=task)
    pages = []
    layouts, images, sizes = [], [], []
    for index in range(len(doc)):
        page = doc[index]
        try:
            print(f'PDF · {models.name} · 第 {index+1}/{len(doc)} 页', file=sys.stderr, flush=True)
            image = raster(page)
            result = reader(image)
            native_fallback = []
            value = None
            if extension == '.docx' and source and isinstance(result,str) and not result.strip():
                text_page = page.get_textpage()
                try:
                    text = text_page.get_text_bounded().strip()
                finally:
                    text_page.close()
                if len(text) >= 50:
                    value = text
                    native_fallback.append('模型未返回完整结构，本页 Word 使用原 PDF 文字层')
            if value is None:
                value = normalize(result, models.name)
            layouts.append(dict(model=models.name, raw=getattr(result, 'raw', str(result)),
                                regions=getattr(result, 'regions', []),
                                structured=getattr(result, 'structured', None),
                                warnings=getattr(result, 'warnings', []) + native_fallback +
                                quality_warnings(getattr(result, 'raw', str(result)))))
            for warning in layouts[-1]['warnings']:
                print(f'PDF · 第 {index+1} 页 · {warning}', file=sys.stderr, flush=True)
            if extension == '.docx':
                buffer = BytesIO()
                image.save(buffer, 'PNG')
                images.append(buffer.getvalue())
            else:
                images.append(None)
            sizes.append(page.get_size())
            pages.append((value, list(blocks(value, markdown_table_rows))))
        finally:
            page.close()
        progress(index+1, len(doc))
    if extension != '.docx' and any(any('上限' in warning for warning in item['warnings']) for item in layouts):
        raise ValueError('模型识别达到生成上限，未导出可能不完整的文件；请换用支持该文档的 OCR 模型。')
    if extension == '.docx':
        from docx import Document
        from contextlib import ExitStack
        from docx.shared import Pt
        from docx.enum.section import WD_SECTION_START
        if __package__:
            from .pdf_word_layout import native_page, position, add_provenance, place_table, repair_table_grids, restore_native_cells, restore_native_text_pages
        else:
            from pdf_word_layout import native_page, position, add_provenance, place_table, repair_table_grids, restore_native_cells, restore_native_text_pages
        document = Document()
        document.styles['Normal'].font.name = 'SimSun'
        document.styles['Normal'].font.size = Pt(11)
        with ExitStack() as stack:
            import pdfplumber
            native = stack.enter_context(pdfplumber.open(source)) if source else None
            if native:
                if __package__:
                    from .pdf_word_layout import annotate_pdf_emphasis
                else:
                    from pdf_word_layout import annotate_pdf_emphasis
                annotate_pdf_emphasis(source,native.pages)
            if native and all(len(p.chars) >= 50 for p in native.pages):
                # PDF fonts, vector rules and image resources are more accurate than
                # inferring them from OCR. Preserve the real model output in the package.
                from pdf2docx import Converter
                converter = Converter(str(source))
                try:
                    converter.convert(str(out), multi_processing=False)
                    native_layout = converter.store()
                finally:
                    converter.close()
                document = Document(out)
                repair_table_grids(document)
                restore_native_cells(document, native.pages, native_layout)
                restore_native_text_pages(document, native.pages, images)
                for item in layouts:
                    item['rendering'] = 'native-pdf-layout'
                add_provenance(document, layouts)
                document.save(out)
                print('PDF · 保留原始字体、图片和表格；模型原始识别及坐标已嵌入 Word', file=sys.stderr, flush=True)
                return
            for index, (value, _) in enumerate(pages):
                from PIL import Image
                image = stack.enter_context(Image.open(BytesIO(images[index])))
                section = document.sections[0] if not index else document.add_section(WD_SECTION_START.NEW_PAGE)
                width, height = sizes[index]
                section.page_width, section.page_height = Pt(width), Pt(height)
                section.left_margin = section.right_margin = Pt(24)
                section.top_margin = section.bottom_margin = Pt(24)
                anchor = document.add_paragraph()
                anchor.paragraph_format.space_after = Pt(0)
                anchor.paragraph_format.line_spacing = Pt(1)
                page = native.pages[index] if native else None
                if page is not None and len(page.chars) >= 50:
                    print(f'PDF · 第 {index+1} 页 · 原始字体/坐标/合并表格 + {models.name} 识别记录', file=sys.stderr, flush=True)
                    layouts[index]['rendering'] = 'native-pdf-layout'
                    native_page(document, page, image)
                else:
                    if any('上限' in warning for warning in layouts[index]['warnings']):
                        raise ValueError(f'第 {index+1} 页模型识别达到生成上限，请更换模型；未生成不完整的 Word。')
                    regions = layouts[index]['regions']
                    if regions:
                        layouts[index]['rendering'] = 'model-regions'
                        for item in regions:
                            x0,y0,x1,y1 = item['bbox']
                            label = item['label'].lower()
                            if label in {'image','picture','figure'}:
                                crop = image.crop((x0*image.width,y0*image.height,x1*image.width,y1*image.height))
                                stream = BytesIO()
                                crop.save(stream,'PNG')
                                stream.seek(0)
                                paragraph = document.add_paragraph()
                                position(paragraph,x0*width,y0*height,(x1-x0)*width)
                                paragraph.add_run().add_picture(stream,width=Pt((x1-x0)*width))
                            else:
                                start = len(document.paragraphs)
                                table_start = len(document.tables)
                                write_recognized_word(document, item['text'])
                                new_tables = document.tables[table_start:]
                                if len(new_tables) == 1:
                                    place_table(new_tables[0], item['bbox'], (width,height))
                                new = document.paragraphs[start:]
                                if len(new) == 1 and label != 'table':
                                    position(new[0],x0*width,y0*height,(x1-x0)*width+4)
                                    # Bounding boxes imply approximate size, not the original font.
                                    for run in new[0].runs:
                                        run.font.size = Pt(max(8,min(36,(y1-y0)*height*.8)))
                                        run.bold = label in {'title','section_header'}
                    else:
                        layouts[index]['rendering'] = 'model-reading-order'
                        write_recognized_word(document, value)
                if page is not None:
                    page.close()
        add_provenance(document, layouts)
        document.save(out)
    elif extension in {'.xlsx', '.csv'}:
        tables = [(index+1, rows) for index, (_, content) in enumerate(pages)
                  for kind, rows in content if kind == 'table']
        if not tables:
            raise ValueError(f'{models.name}: 未识别到表格；该模型可能不支持此页的表格结构，请更换模型或导出文本。')
        if extension == '.csv':
            with out.open('w', encoding='utf-8-sig', newline='') as stream:
                writer = csv.writer(stream)
                for index, (_, rows) in enumerate(tables):
                    if index:
                        writer.writerow([])
                    writer.writerows([[csv_text(cell) for cell in row] for row in rows])
        else:
            from openpyxl import Workbook
            workbook = Workbook()
            workbook.remove(workbook.active)
            for index, (page, rows) in enumerate(tables, 1):
                sheet = workbook.create_sheet(f'Page {page} Table {index}')
                for row in rows:
                    sheet.append([str(cell) for cell in row])
                    for cell in sheet[sheet.max_row]:
                        cell.data_type = 's'
            # HTML tables carry spans that CSV/Markdown row arrays cannot represent.
            if __package__:
                from .pdf_word_layout import table_layout
            else:
                from pdf_word_layout import table_layout
            sheet_index = 0
            for value, content in pages:
                fragments = re.findall(r'<table\b.*?</table>|(?:^\s*\|[^\n]+\|[ \t]*(?:\n|$))+',
                                       value, flags=re.S | re.M)
                for fragment in fragments:
                    if not markdown_table_rows(fragment):
                        continue
                    sheet = workbook.worksheets[sheet_index]
                    sheet_index += 1
                    if not fragment.lstrip().startswith('<table'):
                        continue
                    sheet.delete_rows(1, sheet.max_row)
                    for r,c,rs,cs,text in table_layout(fragment):
                        cell = sheet.cell(r+1,c+1,str(text).strip())
                        cell.data_type = 's'
                        if rs > 1 or cs > 1:
                            sheet.merge_cells(start_row=r+1,start_column=c+1,end_row=r+rs,end_column=c+cs)
            workbook.save(out)
            workbook.close()
    elif extension == '.pptx':
        from pptx import Presentation
        from pptx.util import Inches, Pt
        presentation = Presentation()
        for page_index, (_, content) in enumerate(pages, 1):
            # Split recognized content across slides to avoid text overflowing the page.
            lines = []
            for kind, value in content:
                lines.extend((' | '.join(row) for row in value) if kind == 'table' else value.splitlines())
            lines = [line[start:start+60] for line in lines for start in range(0, max(1,len(line)),60)]
            for start in range(0, max(1,len(lines)), 16):
                slide = presentation.slides.add_slide(presentation.slide_layouts[6])
                box = slide.shapes.add_textbox(Inches(.5), Inches(.4), Inches(9), Inches(6.5))
                frame = box.text_frame
                frame.word_wrap = True
                frame.text = f'Page {page_index}\n' + '\n'.join(lines[start:start+16])
                for paragraph in frame.paragraphs:
                    paragraph.font.size = Pt(18)
        presentation.save(out)
    elif extension == '.md':
        out.write_text('\n\n---\n\n'.join(value for value, _ in pages), 'utf-8')
    elif extension == '.txt':
        out.write_text('\n\n'.join('\n'.join('\t'.join(row) for row in value) if kind == 'table' else value
                                   for _, content in pages for kind, value in content), 'utf-8')
    elif extension == '.html':
        if __package__:
            from .pdf_word_layout import HTMLTable
        else:
            from pdf_word_layout import HTMLTable
        output = ['<!doctype html><html><head><meta charset="utf-8"></head><body>']
        for source_value, content in pages:
            output.append('<section>')
            html_tables = iter(re.findall(r'<table\b.*?</table>|(?:^\s*\|[^\n]+\|[ \t]*(?:\n|$))+', source_value, flags=re.S | re.M))
            for kind, value in content:
                if kind == 'table':
                    original = next(html_tables, None)
                    if original and original.lstrip().startswith('<table'):
                        parser = HTMLTable()
                        parser.feed(original)
                        output.append('<table border="1">' + ''.join('<tr>' + ''.join(
                            f'<td rowspan="{c["rowspan"]}" colspan="{c["colspan"]}">'+html.escape(c['text']).replace('\n','<br>')+'</td>'
                            for c in row)+'</tr>' for row in parser.rows)+'</table>')
                    else:
                        output.append('<table border="1">' + ''.join('<tr>' + ''.join('<td>'+html.escape(cell)+'</td>' for cell in row)+'</tr>' for row in value)+'</table>')
                else:
                    output.append('<p>'+html.escape(value).replace('\n','<br>')+'</p>')
            output.append('</section>')
        out.write_text(''.join(output)+'</body></html>', 'utf-8')
