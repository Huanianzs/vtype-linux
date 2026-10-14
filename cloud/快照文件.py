"""选择同组可解密快照，下载到私有目录并验证结构；不打开用户词库。"""
from pathlib import Path
import json
import os
import struct
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
import 官方同步探针 as p
from 快照恢复 import encode, group_and_metadata

MAGIC = 19921010
LIMIT = 128 * 1024 * 1024


def save_private(path, data):
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, 'wb') as output:
        output.write(data)


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *_args, **_kwargs):
        raise ValueError('拒绝跳转')


def candidates(metadata, members, preferred=None):
    version = p.one(metadata, 3)
    result = []
    for raw in metadata.get(2, []):
        record = p.fields(raw)
        device = p.one(record, 1)
        detail = p.fields(p.one(record, 2, b''))
        if device not in members or p.one(detail, 6) != version or not version:
            continue
        native = f'{device}_{version}'
        url = urllib.parse.urlparse(p.one(detail, 8, b'').decode())
        filename = url.path.rsplit('/', 1)[-1]
        if not filename:
            continue
        keys = [native] if filename == native else [native, filename]
        result.append((device != preferred, -p.one(detail, 2), device, keys))
    return [(device, key) for _, _, device, keys in sorted(result) for key in keys]


def decode_snapshot(data, key):
    if len(data) < 80 or struct.unpack_from('<II', data) != (MAGIC, 2):
        raise ValueError('快照文件头无效')
    end = 32 + (len(data) - 32) // 16 * 16
    decrypt = Cipher(algorithms.AES(key), modes.ECB()).decryptor()
    plain = data[:32] + decrypt.update(data[32:end]) + decrypt.finalize() + data[end:]
    if struct.unpack_from('<I', plain, len(plain)-48)[0] != MAGIC or struct.unpack_from('<I', plain, len(plain)-20)[0] != MAGIC:
        raise ValueError('快照解密尾标无效')
    pos, stop = 32, len(plain) - 48
    counts = {}
    while pos < stop:
        if pos + 8 > stop:
            raise ValueError('数据段头截断')
        marker, kind, reserved = struct.unpack_from('<HHI', plain, pos)
        if marker != 65535 or reserved or kind in counts:
            raise ValueError('数据段格式不兼容')
        pos += 8
        count = 0
        while pos < stop:
            if pos + 2 > stop:
                raise ValueError('记录头截断')
            size = struct.unpack_from('<H', plain, pos)[0]
            if size == 65535:
                break
            pos += 2
            if pos + size + 2 > stop:
                raise ValueError('记录键截断')
            pos += size
            length = struct.unpack_from('<H', plain, pos)[0]
            pos += 2
            if pos + length > stop:
                raise ValueError('记录值截断')
            if kind == 128:
                if length < 51 or plain[pos] != 0 or struct.unpack_from('<H', plain, pos + 1)[0] + 51 != length:
                    raise ValueError('拼音词条格式不兼容')
                plain[pos + 51:pos + length].decode('utf-8')
            pos += length
            count += 1
        counts[kind] = count
    if pos != stop or not counts.get(128):
        raise ValueError('快照缺少有效拼音词条')
    return plain, counts


def download_available(api, http, uin, output, preferred=None):
    gid, members, metadata = group_and_metadata(api, uin)
    choices = candidates(metadata, members, preferred)
    attempts = []
    output = Path(output)
    output.mkdir(mode=0o700, parents=True, exist_ok=False)
    for index, (device, key) in enumerate(choices, 1):
        extra = json.dumps({'group_id': str(gid), 'key': key}, separators=(',', ':'))
        credential = p.fields(api(60, p.number(1, 5) + p.blob(2, extra) + p.number(3, 7)))
        if not p.one(credential, 4, b''):
            attempts.append({'candidate': index, 'result': 'credential_failed'})
            continue
        url = p.one(credential, 4, b'').decode()
        parsed = urllib.parse.urlparse(url)
        if (parsed.scheme != 'https' or not parsed.hostname or not parsed.hostname.endswith('.myqcloud.com')
                or parsed.username or parsed.password or parsed.port not in (None, 443) or not parsed.query
                or parsed.path.rsplit('/', 1)[-1] != key or len(url) > 16384):
            raise ValueError('下载地址不兼容')
        temporary = None
        try:
            fd, temporary = tempfile.mkstemp(prefix='.snapshot-', dir=output)
            total = 0
            deadline = time.monotonic() + 180
            with os.fdopen(fd, 'wb') as target, http.open(url, timeout=30) as response:
                length = int(response.headers.get('Content-Length', 0))
                if length > LIMIT or response.status != 200:
                    raise ValueError('文件大小或HTTP状态不兼容')
                while True:
                    chunk = response.read(256 * 1024)
                    if not chunk:
                        break
                    total += len(chunk)
                    if total > LIMIT or time.monotonic() > deadline:
                        raise ValueError('文件超限')
                    target.write(chunk)
                if not total or length and total != length:
                    raise ValueError('文件长度不完整')
                target.flush()
                os.fsync(target.fileno())
            plain, counts = decode_snapshot(Path(temporary).read_bytes(), p.one(metadata, 4, b''))
            os.replace(temporary, output / 'snapshot.encrypted')
            temporary = None
            save_private(output / 'snapshot.decrypted', plain)
            save_private(output / 'metadata.pb', encode(metadata))
            save_private(output / 'selection.json', json.dumps({'device': device, 'key': key}).encode())
            report = {'downloaded': True, 'bytes': total, 'section_records': counts,
                      'local_dictionary_opened': False, 'attempts': attempts + [{'candidate': index, 'result': 'downloaded_and_structure_valid'}]}
            (output / 'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2))
            return report
        except urllib.error.HTTPError as error:
            raw = error.read(32769)
            code = None
            try:
                if len(raw) <= 32768:
                    code = ET.fromstring(raw).findtext('Code')
            except ET.ParseError:
                pass
            missing = error.code == 404 and code == 'NoSuchKey'
            attempts.append({'candidate': index, 'http_status': error.code,
                             'result': 'object_missing' if missing else 'http_failed'})
            if not missing:
                report = {'downloaded': False, 'local_dictionary_opened': False,
                          'waiting_for_source_refresh': False, 'http_failure_requires_check': True, 'attempts': attempts}
                (output / 'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2))
                return report
        except ValueError:
            attempts.append({'candidate': index, 'result': 'file_or_decryption_invalid'})
        finally:
            if temporary:
                Path(temporary).unlink(missing_ok=True)
    report = {'downloaded': False, 'current_key_candidates': len(choices),
              'local_dictionary_opened': False, 'waiting_for_source_refresh': True, 'attempts': attempts}
    (output / 'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2))
    return report
