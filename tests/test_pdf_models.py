import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'src'))
from formix import worker
from formix.pdf_model import normalize


def text_pdf(path):
    content = b'BT /F1 18 Tf 20 150 Td (Original text) Tj ET'
    objects = [b'<< /Type /Catalog /Pages 2 0 R >>',
               b'<< /Type /Pages /Kids [3 0 R] /Count 1 >>',
               b'<< /Type /Page /Parent 2 0 R /MediaBox [0 0 300 200] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>',
               b'<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>',
               b'<< /Length '+str(len(content)).encode()+b' >>\nstream\n'+content+b'\nendstream']
    data = b'%PDF-1.4\n'
    offsets = [0]
    for index, value in enumerate(objects, 1):
        offsets.append(len(data))
        data += str(index).encode()+b' 0 obj\n'+value+b'\nendobj\n'
    position = len(data)
    data += b'xref\n0 6\n0000000000 65535 f \n'
    data += b''.join(f'{offset:010} 00000 n \n'.encode() for offset in offsets[1:])
    data += b'trailer\n<< /Size 6 /Root 1 0 R >>\nstartxref\n'+str(position).encode()+b'\n%%EOF'
    path.write_bytes(data)


class PDFModelsTests(unittest.TestCase):
    def test_all_dropdown_models_route_all_document_exports_through_reader(self):
        from docx import Document
        from pptx import Presentation
        from openpyxl import load_workbook
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root/'text.pdf'
            text_pdf(source)
            for key in worker.MODEL_PROFILES:
                model = root/key
                model.mkdir()
                (model/'READY').touch()
                text = '# Recognized\n\n| Name | Value |\n| --- | --- |\n| Model result | =1+1 |'
                if key == 'pp-ocrv5-mobile':
                    text = 'Recognized\n<table data-formix-grid="1"><tr><td>Model result</td><td>=1+1</td></tr></table>'
                elif key == 'dots-ocr':
                    text = json.dumps([{'category':'Text','text':text}])
                for extension in ('docx','xlsx','csv','pptx','txt','md','html'):
                    with self.subTest(model=key, extension=extension):
                        target = root/f'{key}.{extension}'
                        with patch.object(worker, 'recognize', return_value=lambda _: text) as reader:
                            worker.pdf(source, target, model)
                            reader.assert_called_once()
                            self.assertEqual(reader.call_args.args[0], model)
                        self.assertGreater(target.stat().st_size, 0)
                        if extension == 'docx':
                            self.assertTrue(Document(target).tables)
                        elif extension == 'pptx':
                            self.assertTrue(Presentation(target).slides)
                        elif extension == 'xlsx':
                            workbook = load_workbook(target)
                            cells = [cell for sheet in workbook for row in sheet for cell in row]
                            self.assertTrue(any(cell.value == '=1+1' and cell.data_type == 's' for cell in cells))
                            workbook.close()
                        else:
                            exported = target.read_text('utf-8-sig')
                            self.assertIn('Model result', exported)
                            self.assertNotIn('Original text', exported)
                            if extension == 'csv':
                                self.assertIn("'=1+1", exported)

    def test_missing_selected_model_uses_original_engine_not_another_installed_model(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root/'smoldocling').mkdir()
            (root/'smoldocling/READY').touch()
            source = root/'text.pdf'
            text_pdf(source)
            with patch.object(worker, 'recognize', side_effect=AssertionError('Model called')):
                worker.pdf(source, root/'out.txt', root/'not-downloaded')
                self.assertIn('Original text', (root/'out.txt').read_text('utf-8'))
                worker.pdf(source, root/'pages.zip', root/'smoldocling')
                self.assertTrue((root/'pages.zip').is_file())

    def test_models_without_table_structure_fail_explicitly(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            model = root/'smolvlm-500m'
            model.mkdir()
            (model/'READY').touch()
            text_pdf(root/'text.pdf')
            with patch.object(worker, 'recognize', return_value=lambda _: 'plain text only'):
                with self.assertRaisesRegex(ValueError, '未识别到表格'):
                    worker.pdf(root/'text.pdf', root/'out.xlsx', model)
            self.assertFalse((root/'out.xlsx').exists())

    def test_empty_and_invalid_model_outputs_are_not_success(self):
        for result in (None, ''):
            with self.assertRaises(ValueError):
                normalize(result, 'deepseek-ocr')


if __name__ == '__main__':
    unittest.main()
