"""Streaming NCM decryption with a reusable on-disk source cache."""
import base64
import hashlib
import json
import os
import struct
import tempfile
import time
from pathlib import Path

from Crypto.Cipher import AES
from Crypto.Util.strxor import strxor

MAX_NCM_FILE_BYTES = 512 * 1024 * 1024
MAX_NCM_KEY_BYTES = 1024 * 1024
MAX_NCM_META_BYTES = 4 * 1024 * 1024
MAX_NCM_COVER_BYTES = 25 * 1024 * 1024
CHUNK_SIZE = 256 * 1024
_KEY_SEED_DEFAULT = [90, 60, 126, 145, 163, 213, 232, 31, 70, 184, 205, 43, 105, 244, 131, 7]
_CORE_KEY_DEFAULT = "MkY2w+K4m3Bz04RFC5X7UA=="
_META_KEY_DEFAULT = "eQ1K/cm+tz4a5esbPMikLw=="
_ALLOWED_EXTENSIONS = {"mp3", "flac", "m4a", "aac", "wav", "ogg", "opus"}


def _derived_key(encoded):
    raw = base64.b64decode(encoded, validate=True)
    seed_text = os.environ.get("FORMIX_NCM_KEY_SEED", "")
    try:
        seed = bytes(int(value.strip()) for value in seed_text.split(",")) if seed_text else bytes(_KEY_SEED_DEFAULT)
    except ValueError:
        seed = bytes(_KEY_SEED_DEFAULT)
    if len(seed) != 16:
        seed = bytes(_KEY_SEED_DEFAULT)
    return bytes(raw[index] ^ seed[index] for index in range(16))


def _unpad(data):
    if not data:
        raise ValueError("Invalid NCM padding")
    size = data[-1]
    if size < 1 or size > len(data) or data[-size:] != bytes([size]) * size:
        raise ValueError("Invalid NCM padding")
    return data[:-size]


def _read_exact(stream, size, label, maximum):
    if size < 0 or size > maximum:
        raise ValueError(f"Invalid NCM {label} length")
    data = stream.read(size)
    if len(data) != size:
        raise ValueError(f"Truncated NCM {label}")
    return data


def _read_length(stream, label):
    data = stream.read(4)
    if len(data) != 4:
        raise ValueError(f"Truncated NCM {label}")
    return struct.unpack("<I", data)[0]


def _keystream(key):
    state = list(range(256))
    j = 0
    for i in range(256):
        j = (state[i] + j + key[i % len(key)]) & 0xff
        state[i], state[j] = state[j], state[i]
    table = bytearray(256)
    for i in range(256):
        index = (i + 1) & 0xff
        n = state[index]
        a = state[(index + n) & 0xff]
        table[i] = state[(n + a) & 0xff]
    return table


def _metadata_bytes(encoded):
    if not encoded:
        return {}
    data = bytearray(encoded)
    for index in range(len(data)):
        data[index] ^= 0x63
    block = base64.b64decode(data[22:], validate=True)
    if not block or len(block) % AES.block_size:
        raise ValueError("Invalid NCM metadata block")
    cipher = AES.new(_derived_key(os.environ.get("FORMIX_NCM_META_KEY", _META_KEY_DEFAULT)), AES.MODE_ECB)
    result = json.loads(_unpad(cipher.decrypt(block)).decode("utf-8")[6:])
    if not isinstance(result, dict):
        raise ValueError("Invalid NCM metadata object")
    return result


def _metadata_values(meta):
    title = str(meta.get("musicName") or "").strip()
    album = str(meta.get("album") or "").strip()
    artists = meta.get("artist") or []
    artist = str(artists[0][0]).strip() if artists and isinstance(artists[0], (list, tuple)) and artists[0] else ""
    return title, artist, album


def _write_tags(path, extension, meta, cover):
    title, artist, album = _metadata_values(meta)
    try:
        if extension == "mp3":
            from mutagen.id3 import ID3, TIT2, TPE1, TALB, APIC, ID3NoHeaderError
            try:
                tags = ID3(path)
            except ID3NoHeaderError:
                tags = ID3()
            if title:
                tags.add(TIT2(encoding=3, text=title))
            if artist:
                tags.add(TPE1(encoding=3, text=artist))
            if album:
                tags.add(TALB(encoding=3, text=album))
            if cover:
                tags.add(APIC(encoding=3, mime="image/jpeg", type=3, desc="Front Cover", data=cover))
            tags.save(path, v2_version=3)
        elif extension == "flac":
            from mutagen.flac import FLAC, Picture
            audio = FLAC(path)
            if title:
                audio["title"] = title
            if artist:
                audio["artist"] = artist
            if album:
                audio["album"] = album
            if cover:
                picture = Picture()
                picture.type, picture.mime, picture.desc, picture.data = 3, "image/jpeg", "Front Cover", cover
                audio.add_picture(picture)
            audio.save()
        elif extension == "m4a":
            from mutagen.mp4 import MP4, MP4Cover
            audio = MP4(path)
            if title:
                audio["\xa9nam"] = title
            if artist:
                audio["\xa9ART"] = artist
            if album:
                audio["\xa9alb"] = album
            if cover:
                audio["covr"] = [MP4Cover(cover, imageformat=MP4Cover.FORMAT_JPEG)]
            audio.save()
    except Exception:
        # Some NCM payloads are valid audio but contain tags Mutagen cannot rewrite.
        pass


def _cache_key(source):
    info = source.stat()
    signature = f"{source.resolve()}\0{info.st_size}\0{info.st_mtime_ns}".encode("utf-8", "surrogatepass")
    digest = hashlib.sha256(signature).hexdigest()[:16]
    stem = "".join(char if char.isalnum() or char in "-_" else "_" for char in source.stem).strip("._")[:64]
    return f"{stem or 'audio'}-{digest}", info.st_size


def decrypt_to_cache(source_path, cache_dir, progress=None):
    source = Path(source_path)
    if source.stat().st_size > MAX_NCM_FILE_BYTES:
        raise ValueError(f"NCM file exceeds {MAX_NCM_FILE_BYTES // (1024 * 1024)} MB limit")
    cache_dir = Path(cache_dir)
    cache_dir.mkdir(parents=True, exist_ok=True)
    stem, _ = _cache_key(source)
    stale_before = time.time() - 24 * 60 * 60
    for partial in cache_dir.glob(f".{stem}-*.part"):
        try:
            if partial.stat().st_mtime < stale_before:
                partial.unlink()
        except OSError:
            pass
    for extension in _ALLOWED_EXTENSIONS:
        cached = cache_dir / f"{stem}.{extension}"
        if cached.is_file() and cached.stat().st_size:
            if progress:
                progress(25, 100)
            return cached

    with source.open("rb") as stream:
        if stream.read(8) != b"CTENFDAM":
            raise ValueError("Not a valid NCM file")
        stream.read(2)
        key_data = bytearray(_read_exact(stream, _read_length(stream, "key"), "key", MAX_NCM_KEY_BYTES))
        for index in range(len(key_data)):
            key_data[index] ^= 0x64
        if not key_data or len(key_data) % AES.block_size:
            raise ValueError("Invalid NCM key block")
        core_key = os.environ.get("FORMIX_NCM_CORE_KEY", _CORE_KEY_DEFAULT)
        key = _unpad(AES.new(_derived_key(core_key), AES.MODE_ECB).decrypt(bytes(key_data)))[17:]
        if not key:
            raise ValueError("Invalid NCM stream key")

        meta = _metadata_bytes(_read_exact(stream, _read_length(stream, "metadata"), "metadata", MAX_NCM_META_BYTES))
        _read_exact(stream, 9, "cover header", 9)  # CRC32 and reserved bytes.
        cover_size = _read_length(stream, "cover")
        cover = _read_exact(stream, cover_size, "cover", MAX_NCM_COVER_BYTES)
        payload_size = max(0, source.stat().st_size - stream.tell())
        extension = str(meta.get("format", "mp3") or "mp3").strip().lower().lstrip(".")
        if extension not in _ALLOWED_EXTENSIONS:
            raise ValueError(f"Unsupported NCM audio format: {extension}")

        fd, temp_name = tempfile.mkstemp(prefix=f".{stem}-", suffix=".part", dir=cache_dir)
        temp_path = Path(temp_name)
        table = bytes(_keystream(key))
        payload_offset = 0
        try:
            with os.fdopen(fd, "wb") as output:
                while True:
                    chunk = stream.read(CHUNK_SIZE)
                    if not chunk:
                        break
                    phase = payload_offset & 0xff
                    rotated_key = table[phase:] + table[:phase]
                    key_stream = (rotated_key * ((len(chunk) + 255) // 256 + 1))[:len(chunk)]
                    output.write(strxor(chunk, key_stream))
                    payload_offset += len(chunk)
                    if progress and payload_size:
                        progress(min(25, int(payload_offset * 25 / payload_size)), 100)
                output.flush()
                os.fsync(output.fileno())
            if not payload_offset:
                raise ValueError("NCM audio payload is empty")
            final_path = cache_dir / f"{stem}.{extension}"
            os.replace(temp_path, final_path)
        except Exception:
            temp_path.unlink(missing_ok=True)
            raise

    if progress:
        progress(25, 100)
    _write_tags(final_path, extension, meta, cover)
    return final_path
