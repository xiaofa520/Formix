"""Only source attribution may appear in PDF-derived Office documents."""
import os
from datetime import datetime, timezone
from pathlib import Path
import tempfile
import xml.etree.ElementTree as ET
import zipfile

DC = 'http://purl.org/dc/elements/1.1/'
CP = 'http://schemas.openxmlformats.org/package/2006/metadata/core-properties'
DCTERMS = 'http://purl.org/dc/terms/'
XSI = 'http://www.w3.org/2001/XMLSchema-instance'
ET.register_namespace('dcterms', DCTERMS)
ET.register_namespace('xsi', XSI)

RDF = 'http://www.w3.org/1999/02/22-rdf-syntax-ns#'


def source_author(source):
    import pypdfium2
    with pypdfium2.PdfDocument(str(source)) as pdf:
        author = pdf.get_metadata_value('Author').strip()
    if author:
        return author
    # PDF Creator/Producer identify software, not the author.
    try:
        import pymupdf
    except ImportError:
        return ''
    with pymupdf.open(str(source)) as pdf:
        xml = pdf.get_xml_metadata()
    if not xml:
        return ''
    try:
        root = ET.fromstring(xml)
    except ET.ParseError:
        return ''
    return '; '.join(node.text.strip() for node in root.findall(
        './/{'+DC+'}creator//{'+RDF+'}li') if node.text and node.text.strip())


def finalize_authorship(source, output, author=None):
    output = Path(output)
    if output.suffix.lower() not in {'.docx', '.xlsx', '.pptx'}:
        return
    if author is None:
        author = source_author(source) if source else ""
    with zipfile.ZipFile(output) as archive:
        part = 'docProps/core.xml'
        root = ET.fromstring(archive.read(part))
        creators = root.findall('{'+DC+'}creator')
        modifiers = root.findall('{'+CP+'}lastModifiedBy')
        for node in creators + modifiers:
            root.remove(node)
        if author:
            ET.SubElement(root, '{'+DC+'}creator').text = author
        # Office templates contain historical dates and library advertising.
        # Store UTC; Explorer/Office display it in the user's local timezone.
        for tag in ('{'+DC+'}description', '{'+DCTERMS+'}created', '{'+DCTERMS+'}modified'):
            for node in root.findall(tag):
                root.remove(node)
        now = datetime.now(timezone.utc).isoformat(timespec='seconds').replace('+00:00', 'Z')
        for name in ('created', 'modified'):
            node = ET.SubElement(root, '{'+DCTERMS+'}'+name)
            node.set('{'+XSI+'}type', 'dcterms:W3CDTF')
            node.text = now
        payload = ET.tostring(root, encoding='utf-8', xml_declaration=True)
        fd, temporary = tempfile.mkstemp(prefix='.authors-', suffix=output.suffix, dir=output.parent)
        os.close(fd)
        try:
            with zipfile.ZipFile(temporary, 'w') as revised:
                for item in archive.infolist():
                    revised.writestr(item, payload if item.filename == part else archive.read(item))
        except BaseException:
            Path(temporary).unlink(missing_ok=True)
            raise
    try:
        os.replace(temporary, output)
    finally:
        Path(temporary).unlink(missing_ok=True)
