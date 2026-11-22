"""Materialize untrusted VOD playlists before FFmpeg sees any resource URI."""
import http.client
import ipaddress
from pathlib import Path
import re
import socket
import ssl
import time
from urllib.parse import unquote, urljoin, urlsplit
from urllib.request import url2pathname


def public_addresses(host, port):
    addresses = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    ips = [ipaddress.ip_address(item[4][0].split('%')[0]) for item in addresses]
    if not addresses or any(not ip.is_global or ip.is_multicast or ip.is_reserved for ip in ips):
        raise ValueError('HLS network resources must use public Internet addresses')
    return addresses


class _PinnedConnection(http.client.HTTPConnection):
    def __init__(self, host, port, addresses, secure):
        super().__init__(host, port, timeout=30)
        self.addresses, self.secure = addresses, secure

    def connect(self):
        error = None
        for family, kind, protocol, _, address in self.addresses:
            sock = socket.socket(family, kind, protocol)
            sock.settimeout(self.timeout)
            try:
                sock.connect(address)  # Already validated; never resolve a second time.
                if self.secure:
                    sock = ssl.create_default_context().wrap_socket(sock, server_hostname=self.host)
                self.sock = sock
                return
            except OSError as exc:
                error = exc
                sock.close()
        raise error or OSError('No usable HLS address')


def http_resource(url, destination, limit, deadline, redirects=0):
    if redirects > 5:
        raise ValueError('Too many HLS redirects')
    parsed = urlsplit(url)
    if (parsed.scheme not in {'http', 'https'} or not parsed.hostname or parsed.username
            or parsed.password or parsed.fragment or '\\' in url):
        raise ValueError('Invalid HLS network resource URL')
    host = parsed.hostname.encode('idna').decode('ascii')
    port = parsed.port or (443 if parsed.scheme == 'https' else 80)
    connection = _PinnedConnection(host, port, public_addresses(host, port), parsed.scheme == 'https')
    try:
        target = parsed.path or '/'
        if parsed.query:
            target += '?' + parsed.query
        connection.request('GET', target, headers={'User-Agent': 'Formix', 'Accept-Encoding': 'identity'})
        response = connection.getresponse()
        if response.status in {301, 302, 303, 307, 308}:
            location = response.getheader('Location')
            if not location:
                raise ValueError('Missing HLS redirect target')
            response.close()
            connection.close()
            return http_resource(urljoin(url, location), destination, limit, deadline, redirects + 1)
        if response.status != 200:
            raise ValueError(f'HLS resource returned HTTP {response.status}')
        size = 0
        with destination.open('wb') as output:
            while True:
                if time.monotonic() > deadline:
                    raise TimeoutError('HLS download time limit exceeded')
                chunk = response.read1(min(1024*1024, limit - size + 1))
                if not chunk:
                    break
                size += len(chunk)
                if size > limit:
                    raise ValueError('HLS download size limit exceeded')
                output.write(chunk)
        return size, url
    finally:
        connection.close()


class PlaylistCache:
    def __init__(self, source, directory, *, max_bytes=8*1024**3, max_resources=10000, timeout=3600):
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)
        self.remote = isinstance(source, str) and urlsplit(source).scheme in {'http', 'https'}
        self.source = source if self.remote else Path(source).resolve()
        self.root = None if self.remote else self.source.parent
        self.remaining, self.max_resources = max_bytes, max_resources
        self.deadline = time.monotonic() + timeout
        self.cached, self.visiting = {}, set()

    def resolve(self, base, reference):
        parsed = urlsplit(reference)
        base_remote = isinstance(base, str) and urlsplit(base).scheme in {'http', 'https'}
        if self.remote or base_remote:
            result = urljoin(str(base), reference)
            if urlsplit(result).scheme not in {'http', 'https'}:
                raise ValueError('Remote HLS cannot reference local files or other protocols')
            return result
        if parsed.scheme in {'http', 'https'}:
            return reference
        if parsed.netloc:
            raise ValueError('Local HLS cannot reference a network file share')
        if parsed.scheme == 'file':
            result = Path(url2pathname(parsed.path)).resolve()
        elif parsed.scheme and not Path(reference).is_absolute():
            raise ValueError('Unsupported local HLS protocol')
        else:
            result = (Path(base).parent / unquote(reference)).resolve()
        if not result.is_relative_to(self.root):
            raise ValueError('HLS resource is outside the selected playlist directory')
        return result

    def resource(self, source, playlist=False, depth=0):
        key = (str(source), playlist)
        if key in self.visiting or depth > 8:
            raise ValueError('Cyclic or excessively nested HLS playlist')
        if key in self.cached:
            return self.cached[key]
        if len(self.cached) >= self.max_resources or time.monotonic() > self.deadline:
            raise ValueError('HLS resource or time limit exceeded')
        suffix = '.m3u8' if playlist else Path(urlsplit(str(source)).path).suffix.lower()
        if suffix not in {'.m3u8', '.ts', '.m4s', '.mp4', '.aac', '.mp3', '.vtt', '.webvtt', '.key'}:
            suffix = '.bin'
        dest = self.directory / (f'resource-{len(self.cached):05d}' + suffix)
        self.cached[key] = dest
        limit = min(self.remaining, 4*1024**2 if playlist else 512*1024**2)
        network = isinstance(source, str) and urlsplit(source).scheme in {'http', 'https'}
        if network:
            size, base = http_resource(str(source), dest, limit, self.deadline)
        else:
            source = Path(source).resolve()
            if not source.is_relative_to(self.root) or not source.is_file():
                raise ValueError('Invalid local HLS resource')
            size, base = source.stat().st_size, source
            if size > limit:
                raise ValueError('HLS download size limit exceeded')
            with source.open('rb') as incoming, dest.open('wb') as outgoing:
                size = 0
                while chunk := incoming.read(1024*1024):
                    size += len(chunk)
                    if size > limit or time.monotonic() > self.deadline:
                        raise ValueError('HLS resource size or time limit exceeded')
                    outgoing.write(chunk)
        self.remaining -= size
        with dest.open('rb') as incoming:
            is_manifest = incoming.read(10).lstrip(b'\xef\xbb\xbf').startswith(b'#EXTM3U')
        if not playlist and (is_manifest or dest.suffix == '.m3u8'):
            if size > 4*1024**2:
                raise ValueError('HLS playlist is too large')
            playlist = True
            manifest = dest.with_suffix('.m3u8')
            dest.rename(manifest)
            dest = manifest
            self.cached[key] = dest
        if playlist:
            self.visiting.add(key)
            text = dest.read_text('utf-8-sig')
            if not text.startswith('#EXTM3U'):
                raise ValueError('Invalid M3U8 playlist')
            master = '#EXT-X-STREAM-INF:' in text
            if not master and '#EXT-X-ENDLIST' not in text:
                raise ValueError('Live HLS is not supported; select a completed VOD playlist')
            lines = []
            next_playlist = False
            for line in text.splitlines():
                if line.startswith('#'):
                    if 'URI=' in line:
                        is_playlist = line.startswith(('#EXT-X-MEDIA:', '#EXT-X-I-FRAME-STREAM-INF:'))
                        def rewrite(match):
                            resource = self.resolve(base, match[1])
                            return 'URI="' + self.resource(resource, is_playlist, depth+1).name + '"'
                        line = re.sub(r'URI="([^"\r\n]+)"', rewrite, line)
                        if re.search(r'URI=(?!")', line):
                            raise ValueError('Malformed HLS URI')
                    if line.startswith('#EXT-X-STREAM-INF:'):
                        next_playlist = True
                elif line.strip():
                    line = self.resource(self.resolve(base, line.strip()), next_playlist, depth+1).name
                    next_playlist = False
                lines.append(line)
            dest.write_text('\n'.join(lines)+'\n', 'utf-8')
            self.visiting.remove(key)
        return dest


def materialize(source, directory):
    cache = PlaylistCache(source, directory)
    return cache.resource(cache.source, playlist=True)
