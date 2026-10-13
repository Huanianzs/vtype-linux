"""验证当前密钥快照选择、404后选其他来源、完整结构检查及临时文件清理。"""
import io
import json
from pathlib import Path
import struct
import sys
import tempfile
import unittest
import urllib.error
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'cloud'))
import 官方同步探针 as p
from 快照文件 import MAGIC, candidates, decode_snapshot, download_available

KEY = b'K' * 16


def fixture():
    header = struct.pack('<II', MAGIC, 2) + bytes(24)
    word = '你好'.encode()
    value = bytearray(51) + word
    struct.pack_into('<H', value, 1, len(word))
    key = b'ni,hao'
    body = struct.pack('<HHI', 65535, 128, 0) + struct.pack('<H', len(key)) + key + struct.pack('<H', len(value)) + value
    footer = bytearray(48)
    struct.pack_into('<I', footer, 0, MAGIC)
    struct.pack_into('<I', footer, 28, MAGIC)
    plain = header + body + footer
    end = 32 + (len(plain)-32)//16*16
    enc = Cipher(algorithms.AES(KEY), modes.ECB()).encryptor()
    return plain[:32] + enc.update(plain[32:end]) + enc.finalize() + plain[end:]


class Response(io.BytesIO):
    status = 200
    def __init__(self, data):
        super().__init__(data)
        self.headers = {'Content-Length': str(len(data))}


class Recovery(unittest.TestCase):
    def api(self, sub, body):
        self.subs.append(sub)
        if sub == 34:
            group = p.number(1, 2002) + b''.join(p.blob(2, p.number(1, uid)) for uid in [1001, 3003, 4004])
            return p.blob(1, group) + p.number(2, 0)
        if sub == 44:
            rows = b''.join(p.blob(2, p.number(1, uid) + p.blob(2,
                p.number(2, 1800000000000) + p.number(6, 7) + p.blob(8, f'https://bucket.myqcloud.com/{uid}_7?s=old')))
                for uid in [3003, 4004])
            return p.number(1, 0) + rows + p.number(3, 7) + p.blob(4, KEY)
        self.assertEqual(sub, 60)
        extra = json.loads(p.one(p.fields(body), 2))
        return p.number(6, 65536) + p.blob(4, 'https://bucket.myqcloud.com/' + extra['key'] + '?s=secret')

    def setUp(self):
        self.subs, self.urls = [], []
        self.fail_first = True
        self.fail_all = False
        self.body = fixture()

    def open(self, url, timeout):
        self.urls.append(url)
        if self.fail_all or self.fail_first and '3003_' in url:
            raise urllib.error.HTTPError(url, 404, 'secret', {}, io.BytesIO(b'<Error><Code>NoSuchKey</Code></Error>'))
        return Response(self.body)

    def test_missing_preferred_source_falls_back_without_dictionary_changes(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp)/'result'
            result = download_available(self.api, self, 1001, output, 3003)
            self.assertTrue(result['downloaded'])
            self.assertEqual(result['section_records'], {128: 1})
            self.assertEqual(result['attempts'][0]['result'], 'object_missing')
            self.assertFalse(result['local_dictionary_opened'])
            self.assertFalse(list(output.glob('.snapshot-*')))
            for secret in ['3003', '4004', 'secret', 'https:']:
                self.assertNotIn(secret, json.dumps(result))
            self.assertNotIn(43, self.subs)
            self.assertNotIn(41, self.subs)

    def test_all_missing_waits_for_refresh(self):
        self.fail_all = True
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp)/'result'
            result = download_available(self.api, self, 1001, output)
            self.assertFalse(result['downloaded'])
            self.assertTrue(result['waiting_for_source_refresh'])
            self.assertFalse((output/'snapshot.decrypted').exists())
            self.assertEqual(len(self.urls), 2)

    def test_corrupted_data_never_published(self):
        self.fail_first = False
        self.body = b'corrupted'
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp)/'result'
            result = download_available(self.api, self, 1001, output)
            self.assertFalse(result['downloaded'])
            self.assertEqual([x.name for x in output.iterdir()], ['report.json'])

    def test_network_error_stops_without_retry(self):
        def fail(*args, **kwargs):
            raise urllib.error.URLError('private-url')
        self.open = fail
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp)/'result'
            with self.assertRaises(urllib.error.URLError):
                download_available(self.api, self, 1001, output)
            self.assertFalse(list(output.iterdir()))

    def test_old_key_and_other_group_candidates_skipped(self):
        def row(uid, version):
            return p.number(1, uid)+p.blob(2,p.number(6, version)+p.blob(8, f'https://bucket.myqcloud.com/{uid}_{version}?s=1'))
        metadata = {3: [7], 2: [row(3003, 6), row(9999, 7), row(4004, 7)]}
        self.assertEqual(candidates(metadata, {1001, 3003, 4004}), [(4004, '4004_7')])

    def test_wrong_key_and_truncated_file_rejected(self):
        for data, key in [(fixture(), b'X'*16), (fixture()[:-1], KEY), (bytes(80), KEY)]:
            with self.assertRaises(ValueError):
                decode_snapshot(data, key)


if __name__ == '__main__':
    unittest.main()
