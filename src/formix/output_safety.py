"""Make exported text inert and publish self-contained HTML resources."""
import base64
import html
import mimetypes
from pathlib import Path
import re
from urllib.parse import unquote, urlsplit


def csv_text(value):
    if not isinstance(value, str):
        return value
    # CSV quoting does not stop spreadsheet formula interpretation. Also guard
    # whitespace-prefixed formulas and control-character cell starts.
    stripped = value.lstrip()
    if (stripped.startswith(('=', '+', '-', '@')) or value.startswith(('\t', '\r', '\n'))):
        return "'" + value
    return value


def embed_html_assets(path):
    path = Path(path)
    root = path.parent.resolve()

    def data_uri(reference, directory=root, seen=frozenset()):
        reference = html.unescape(reference)
        parsed = urlsplit(reference)
        if parsed.scheme == 'data' or not parsed.path:
            return reference
        if parsed.scheme or parsed.netloc:
            raise ValueError('HTML export contains an external resource')
        asset = (directory / unquote(parsed.path)).resolve()
        if not asset.is_relative_to(root) or asset in seen:
            raise ValueError('Invalid HTML export resource path')
        mime = mimetypes.guess_type(asset.name)[0] or 'application/octet-stream'
        content = asset.read_bytes()
        if mime == 'text/css':
            content = embed_css(content.decode('utf-8'), asset.parent, seen | {asset}).encode('utf-8')
        return 'data:' + mime + ';base64,' + base64.b64encode(content).decode('ascii')

    def embed_css(text, directory=root, seen=frozenset()):
        def replace(match):
            value = match[1].strip().strip('"\'')
            return 'url("' + data_uri(value, directory, seen) + '")'
        return re.sub(r'url\(\s*([^)]*?)\s*\)', replace, text, flags=re.I)

    def tag(match):
        text = match[0]
        if text.startswith(('<!--', '<!', '<?', '</')):
            return text
        names = r'src|background|data'
        if re.match(r'<link\b', text, re.I) and re.search(r'\brel\s*=\s*["\']stylesheet["\']', text, re.I):
            names += '|href'
        return re.sub(r'\b(' + names + r')\s*=\s*(["\'])(.*?)\2',
                      lambda m: m[1] + '=' + m[2] + data_uri(m[3]) + m[2], text, flags=re.I | re.S)

    content = path.read_text('utf-8-sig')
    content = re.sub(r'<!--.*?-->|<[^>]+>', tag, content, flags=re.S)
    content = embed_css(content)
    pending = path.with_suffix('.embedded')
    pending.write_text(content, 'utf-8')
    pending.replace(path)
