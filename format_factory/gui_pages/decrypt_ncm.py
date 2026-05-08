import struct
import json
import base64
from Crypto.Cipher import AES
import sys
import os
import mutagen
from mutagen.id3 import ID3, TIT2, TPE1, TALB, APIC, ID3NoHeaderError
from mutagen.flac import FLAC, Picture
from mutagen.mp4 import MP4, MP4Cover

CORE_KEY = bytes.fromhex("687a4852416d736f356b496e62617857")
META_KEY = bytes.fromhex("2331346C6A6B5F215C5D2630553C2728")

def unpad(s):
    return s[:-s[-1]]

def get_keystream(key):
    s = list(range(256))
    key_len = len(key)
    j = 0
    for i in range(256):
        j = (s[i] + j + key[i % key_len]) & 0xff
        s[i], s[j] = s[j], s[i]
        
    keystream = bytearray(256)
    for i in range(256):
        idx = (i + 1) & 0xff
        n = s[idx]
        a = s[(idx + n) & 0xff]
        keystream[i] = s[(n + a) & 0xff]
        
    return keystream

def decrypt_ncm(filepath, out_dir=None):
    with open(filepath, 'rb') as f:
        data = f.read()

    magic = struct.unpack('<II', data[:8])
    if magic[0] != 0x4e455443 or magic[1] != 0x4d414446:
        print("Not a valid NCM file")
        return None

    offset = 10

    # Extract RC4 key
    key_len = struct.unpack('<I', data[offset:offset+4])[0]
    offset += 4
    key_data = bytearray(data[offset:offset+key_len])
    for i in range(len(key_data)):
        key_data[i] ^= 0x64

    cipher = AES.new(CORE_KEY, AES.MODE_ECB)
    decrypted_key = unpad(cipher.decrypt(bytes(key_data)))
    rc4_key = decrypted_key[17:]

    offset += key_len

    # Extract metadata
    meta_len = struct.unpack('<I', data[offset:offset+4])[0]
    offset += 4
    meta_json = {}
    if meta_len > 0:
        meta_data = bytearray(data[offset:offset+meta_len])
        for i in range(len(meta_data)):
            meta_data[i] ^= 0x63
        
        meta_data_decoded = base64.b64decode(meta_data[22:])
        cipher_meta = AES.new(META_KEY, AES.MODE_ECB)
        decrypted_meta = unpad(cipher_meta.decrypt(meta_data_decoded)).decode('utf-8')
        meta_json = json.loads(decrypted_meta[6:])
        print(f"Metadata: {meta_json.get('musicName', 'Unknown')} - {meta_json.get('artist', [['Unknown']])[0][0]}")
        offset += meta_len

    # Gap and Padding
    # skip crc32 (4 bytes) and some reserved 5 bytes gap before image data
    offset += 9
    
    # image
    img_gap = struct.unpack('<I', data[offset:offset+4])[0]
    img_data = data[offset+4 : offset+4+img_gap]
    offset += 4 + img_gap
    
    # Payload
    payload = bytearray(data[offset:])

    # Generate keystream mapping
    mapped_key = get_keystream(rc4_key)

    # Decrypt payload
    for i in range(len(payload)):
        payload[i] ^= mapped_key[i & 0xff]

    # Save decrypted file
    ext = meta_json.get('format', 'mp3')
    filename = os.path.basename(filepath)
    filename_no_ext = os.path.splitext(filename)[0]

    if out_dir:
        out_path = os.path.join(out_dir, filename_no_ext + '.' + ext)
    else:
        out_path = os.path.splitext(filepath)[0] + '.' + ext

    with open(out_path, 'wb') as f:
        f.write(payload)

    # Apply Metadata & Image
    try:
        if ext == 'mp3':
            try:
                audio = ID3(out_path)
            except ID3NoHeaderError:
                audio = ID3()

            if meta_json:
                title = meta_json.get('musicName', '')
                artist = meta_json.get('artist', [['']])[0][0]
                album = meta_json.get('album', '')

                if title:
                    audio.add(TIT2(encoding=3, text=title))
                if artist:
                    audio.add(TPE1(encoding=3, text=artist))
                if album:
                    audio.add(TALB(encoding=3, text=album))

            if img_data:
                audio.add(
                    APIC(
                        encoding=3,
                        mime='image/jpeg',
                        type=3,
                        desc='Front Cover',
                        data=img_data
                    )
                )
            audio.save(out_path, v2_version=3)

        elif ext == 'flac':
            audio = FLAC(out_path)

            if meta_json:
                title = meta_json.get('musicName', '')
                artist = meta_json.get('artist', [['']])[0][0]
                album = meta_json.get('album', '')

                if title:
                    audio['title'] = title
                if artist:
                    audio['artist'] = artist
                if album:
                    audio['album'] = album

            if img_data:
                pic = Picture()
                pic.type = 3
                pic.mime = "image/jpeg"
                pic.desc = "Front Cover"
                pic.data = img_data
                audio.add_picture(pic)

            audio.save()

        elif ext == 'm4a':
            audio = MP4(out_path)

            if meta_json:
                title = meta_json.get('musicName', '')
                artist = meta_json.get('artist', [['']])[0][0]
                album = meta_json.get('album', '')

                if title:
                    audio["\xa9nam"] = title
                if artist:
                    audio["\xa9ART"] = artist
                if album:
                    audio["\xa9alb"] = album

            if img_data:
                audio["covr"] = [
                    MP4Cover(img_data, imageformat=MP4Cover.FORMAT_JPEG)
                ]

            audio.save()
    except Exception as e:
        print(f"Failed to write metadata: {e}")

    print(f"Decrypted to {out_path}")
    return out_path

if __name__ == '__main__':
    if len(sys.argv) > 1:
        decrypt_ncm(sys.argv[1])
    else:
        print("Usage: python decrypt_ncm.py <file.ncm>")
