"""使用合成服务端元数据验证快照凭证校验，不联网、不读取真实身份。"""
import json
from pathlib import Path
import socket
import struct
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'cloud'))
import 官方同步探针 as p
from 实时云桥接 import SYNC_MAGIC, sync_service

UIN, GROUP, DEVICE, VERSION = 1001, 2002, 3003, 4004


def metadata(device=DEVICE, version=VERSION, status=0):
    detail = p.number(6, version) + p.blob(8, 'https://example.myqcloud.com/path/legacy-file')
    return p.number(1, status) + p.blob(2, p.number(1, device) + p.blob(2, detail)) + p.number(3, 7)


class SnapshotKeys(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        root = Path(self.temp.name)
        (root / 'identity.json').write_text('{"server_key":"synthetic"}')
        self.replies = [metadata()]
        self.calls = []
        test = self

        class Probe:
            def __init__(self, identity):
                self.identity = identity

            def request(self, *_):
                return p.number(1, 0)

            def api(self, sub, body):
                test.calls.append(sub)
                return test.replies.pop(0) if sub == 44 else b''

        self.patches = [patch.object(p, 'STATE', root), patch.object(p, 'Probe', Probe)]
        for item in self.patches:
            item.start()
        self.host, self.client = socket.socketpair()
        self.client.settimeout(2)
        self.thread = threading.Thread(target=sync_service,
            args=(p, self.host, UIN, GROUP, root / 'log.jsonl'),
            kwargs={'readonly': True, 'downloads': True}, daemon=True)
        self.thread.start()

    def tearDown(self):
        self.client.close()
        self.thread.join(2)
        self.host.close()
        for item in reversed(self.patches):
            item.stop()
        self.temp.cleanup()

    def call(self, sub, body):
        self.client.sendall(struct.pack('<5I', SYNC_MAGIC, 1, 4814, sub, len(body)) + body)
        def read(size):
            result = b''
            while len(result) < size:
                chunk = self.client.recv(size - len(result))
                self.assertTrue(chunk)
                result += chunk
            return result
        magic, task, code, size = struct.unpack('<IIiI', read(16))
        self.assertEqual((magic, task), (SYNC_MAGIC, 1))
        read(size)
        return code

    def refresh(self):
        return self.call(44, p.number(1, UIN) + p.number(2, GROUP))

    def token(self, key, group=GROUP, kind=5, method=7):
        return self.call(60, p.number(1, kind) + p.blob(2,
            json.dumps({'group_id': str(group), 'key': key})) + p.number(3, method))

    def test_engine_device_version_key(self):
        self.assertEqual(self.refresh(), 0)
        self.assertEqual(self.token(f'{DEVICE}_{VERSION}'), 0)
        self.assertEqual(self.calls, [44, 60])

    def test_legacy_url_and_own_version(self):
        self.refresh()
        self.assertEqual(self.token('legacy-file'), 0)
        self.assertEqual(self.token(f'{UIN}_7'), 0)

    def test_unknown_device_or_version(self):
        self.refresh()
        for key in [f'{DEVICE+1}_{VERSION}', f'{DEVICE}_{VERSION+1}', '../legacy-file']:
            self.assertEqual(self.token(key), -1)
        self.assertEqual(self.calls, [44])

    def test_other_group_type_and_upload_still_rejected(self):
        self.refresh()
        key = f'{DEVICE}_{VERSION}'
        self.assertEqual(self.token(key, group=GROUP+1), -1)
        self.assertEqual(self.token(key, kind=4), -1)
        self.assertEqual(self.token(key, method=1), -1)
        self.assertEqual(self.call(41, p.number(1, UIN) + p.number(3, GROUP)), -1)
        self.assertEqual(self.calls, [44])

    def test_refresh_revokes_previous_keys(self):
        self.refresh()
        self.replies.append(metadata(version=VERSION+1))
        self.refresh()
        self.assertEqual(self.token(f'{DEVICE}_{VERSION}'), -1)
        self.assertEqual(self.token(f'{DEVICE}_{VERSION+1}'), 0)

    def test_failed_response_does_not_add_keys(self):
        self.replies[0] = metadata(status=1)
        self.refresh()
        self.assertEqual(self.token(f'{DEVICE}_{VERSION}'), -1)

    def test_zero_device_or_version_not_authorized(self):
        self.replies[0] = metadata(device=0)
        self.refresh()
        self.assertEqual(self.token(f'0_{VERSION}'), -1)
        self.replies.append(metadata(version=0))
        self.refresh()
        self.assertEqual(self.token(f'{DEVICE}_0'), -1)


if __name__ == '__main__':
    unittest.main()
