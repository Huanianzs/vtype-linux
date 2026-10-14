"""检查脱敏诊断、元数据候选键及只读小范围下载，不连接真实服务。"""
import importlib.util
import io
import json
from pathlib import Path
import struct
import unittest
import urllib.error

spec = importlib.util.spec_from_file_location('snapshot_diagnosis', Path(__file__).resolve().parents[1] / 'scripts/diagnose-snapshots.py')
d = importlib.util.module_from_spec(spec)
spec.loader.exec_module(d)
p = d.p


class Response(io.BytesIO):
    status = 206


class Http:
    def __init__(self, status=206, body=None):
        self.status = status
        self.body = body if body is not None else struct.pack('<II', 19921010, 2) + bytes(24)
        self.calls = []

    def open(self, request, timeout):
        self.calls.append(request)
        if self.status != 206:
            raise urllib.error.HTTPError(request.full_url, self.status, 'signed-secret', {}, io.BytesIO(self.body))
        return Response(self.body)


class Diagnosis(unittest.TestCase):
    def api(self, sub, body):
        self.calls.append(sub)
        if sub == 34:
            return p.blob(1, p.number(1, 2002)) + p.number(2, 0)
        if sub == 44:
            detail = p.number(2, 1750000000000) + p.number(6, 7) + p.blob(8, self.metadata_url)
            return p.number(1, 0) + p.blob(2, p.number(1, 3003) + p.blob(2, detail)) + p.number(3, 7)
        self.assertEqual(sub, 60)
        f = p.fields(body)
        self.assertEqual((p.one(f, 1), p.one(f, 3)), (5, 7))
        extra = json.loads(p.one(f, 2, b''))
        self.assertEqual(extra['group_id'], '2002')
        self.keys.append(extra['key'])
        return p.blob(4, 'https://bucket.myqcloud.com/path/' + extra['key'] + '?signature=secret') + p.number(6, 0)

    def setUp(self):
        self.calls, self.keys = [], []
        self.metadata_url = 'https://bucket.myqcloud.com/path/3003_7?signature=old-secret'

    def test_success_reads_only_header_and_redacts_identifiers(self):
        http = Http(body=struct.pack('<II', 19921010, 2) + bytes(128))
        report = d.diagnose(self.api, http, 1001)
        self.assertEqual(report['valid_snapshot_headers'], 1)
        self.assertEqual(report['rows'][0]['bytes_read'], 32)
        self.assertEqual(http.calls[0].get_header('Range'), 'bytes=0-31')
        self.assertEqual(self.calls, [34, 44, 60])
        for secret in ('secret', '3003', '2002', '1001', 'myqcloud', 'https:'):
            self.assertNotIn(secret, json.dumps(report))

    def test_mismatched_metadata_and_native_keys_both_checked(self):
        self.metadata_url = 'https://bucket.myqcloud.com/path/legacy-object?signature=secret'
        report = d.diagnose(self.api, Http(), 1001)
        self.assertEqual(self.keys, ['legacy-object', '3003_7'])
        self.assertEqual(len(report['rows']), 2)

    def test_metadata_and_credential_success_can_still_be_missing_object(self):
        http = Http(404, b'<Error><Code>NoSuchKey</Code><Key>private-key</Key></Error>')
        report = d.diagnose(self.api, http, 1001)
        self.assertEqual(report['missing_objects'], 1)
        self.assertEqual(report['rows'][0]['result'], 'metadata_object_not_found')
        self.assertNotIn('private-key', json.dumps(report))

    def test_signature_failure_distinct_from_missing_object(self):
        report = d.diagnose(self.api, Http(403, b'<Error><Code>SignatureDoesNotMatch</Code></Error>'), 1001)
        self.assertEqual(report['missing_objects'], 0)
        self.assertEqual(report['rows'][0]['cos_error_code'], 'SignatureDoesNotMatch')

    def test_non_snapshot_body_rejected(self):
        report = d.diagnose(self.api, Http(body=b'not a snapshot'), 1001)
        self.assertEqual(report['valid_snapshot_headers'], 0)

    def test_unknown_error_body_not_exposed(self):
        result = d.read_header(Http(404, b'<Error><Code>private-new-code</Code></Error>'), self.metadata_url)
        self.assertEqual(result['cos_error_code'], 'Other')
        self.assertNotIn('private', json.dumps(result))

    def test_external_url_and_redirect_refused(self):
        for url in ['http://bucket.myqcloud.com/x?s=1', 'https://myqcloud.com.evil.test/x?s=1',
                    'https://user@bucket.myqcloud.com/x?s=1', 'https://bucket.myqcloud.com:444/x?s=1']:
            with self.assertRaises(ValueError):
                d.read_header(Http(), url)
        with self.assertRaises(ValueError):
            d.NoRedirect().redirect_request()

    def test_cos_field6_is_not_assumed_to_be_status(self):
        def api(sub, body):
            response = self.api(sub, body)
            if sub == 60:
                fields = p.fields(response)
                response = p.blob(4, p.one(fields, 4)) + p.number(6, 65536)
            return response
        self.assertEqual(d.diagnose(api, Http(), 1001)['valid_snapshot_headers'], 1)


if __name__ == '__main__':
    unittest.main()
