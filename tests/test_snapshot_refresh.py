"""核对单成员重建请求的身份、请求时间及已有备份信息保留。"""
from pathlib import Path
import sys
import json
import tempfile
import unittest
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'cloud'))
import 官方同步探针 as p
from 快照恢复 import Client, make_refresh_request, validate_control

UIN, PEER, GROUP, NOW = 1001, 3003, 2002, 1800000000000


class Refresh(unittest.TestCase):
    def build(self, peer=PEER, detail=None):
        metadata = {3: [7]}
        if detail is not None:
            metadata[2] = [p.number(1, UIN) + p.blob(2, detail)]
        return make_refresh_request(UIN, peer, GROUP, {UIN, PEER}, metadata, NOW)

    def test_new_member_requests_one_peer_without_claiming_upload(self):
        body, original = self.build()
        validate_control(body, UIN, PEER, GROUP, NOW)
        detail = p.fields(p.one(p.fields(p.one(p.fields(body), 1)), 2))
        self.assertIsNone(original)
        self.assertEqual(detail, {1: [1], 6: [7], 9: [PEER], 10: [NOW]})

    def test_existing_upload_progress_and_address_preserved(self):
        previous = p.number(1, 1) + p.number(2, NOW - 1000) + p.number(6, 6) + p.number(7, 99) + p.blob(8, b'existing-url')
        body, original = self.build(detail=previous)
        self.assertEqual(original, previous)
        detail = p.fields(p.one(p.fields(p.one(p.fields(body), 1)), 2))
        for k, values in p.fields(previous).items():
            self.assertEqual(detail[k], values)

    def test_unknown_self_and_broadcast_target_refused(self):
        for peer in [UIN, 4004, 0, -1, 2**64-1]:
            with self.assertRaises(ValueError):
                self.build(peer)

    def test_existing_other_request_not_overwritten(self):
        detail = p.number(9, 4004) + p.number(10, NOW - 1000)
        with self.assertRaises(ValueError):
            self.build(detail=detail)

    def test_wrong_group_target_identity_and_stale_request_refused(self):
        body, _ = self.build()
        for uin, peer, gid, now in [(UIN+1, PEER, GROUP, NOW), (UIN, PEER+1, GROUP, NOW),
                                    (UIN, PEER, GROUP+1, NOW), (UIN, PEER, GROUP, NOW+120001)]:
            with self.assertRaises(ValueError):
                validate_control(body, uin, peer, gid, now)

    def test_refresh_and_cleanup_authorization_consumed_once(self):
        calls = []
        class Probe:
            def __init__(self, identity):
                pass
            def request(self, *args):
                import time
                return p.number(1, int(time.time()*1000))
            def api(self, sub, body, **kwargs):
                calls.append(sub)
                return p.number(1, 0)
        with tempfile.TemporaryDirectory() as tmp, patch.object(p, 'Probe', Probe), patch.object(p, 'STATE', Path(tmp)):
            state = Path(tmp)
            (state/'identity.json').write_text(json.dumps({'uin':UIN}))
            client = Client(state)
            body, _ = make_refresh_request(UIN, PEER, GROUP, {UIN, PEER}, {3:[7]}, client.now_ms())
            client.allowed_refresh = PEER, GROUP
            client(43, body)
            with self.assertRaises(ValueError):
                client(43, body)
            cleanup = p.blob(1,p.number(1,UIN)+p.blob(2,p.number(1,1)))+p.number(2,GROUP)
            client.allowed_cleanup = cleanup
            client(43, cleanup)
            with self.assertRaises(ValueError):
                client(43, cleanup)
            with self.assertRaises(ValueError):
                client(41, b'')
            self.assertEqual(calls, [43,43])


if __name__ == '__main__':
    unittest.main()
