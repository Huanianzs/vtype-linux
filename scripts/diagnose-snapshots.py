#!/usr/bin/env python3
"""只读检查官方快照可达性，输出不含设备标识、词条与签名地址的报告。"""
import argparse
import fcntl
import json
import os
from pathlib import Path
import struct
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'cloud'))
import 官方同步探针 as p

ERROR_CODES = {'NoSuchKey', 'AccessDenied', 'SignatureDoesNotMatch',
               'RequestTimeTooSkewed', 'ExpiredToken', 'RequestHasExpired', 'NoSuchBucket'}


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *_args, **_kwargs):
        raise ValueError('拒绝跳转')


def validate_url(url):
    parsed = urllib.parse.urlparse(url)
    if (parsed.scheme != 'https' or not parsed.hostname
            or not parsed.hostname.endswith('.myqcloud.com')
            or parsed.username or parsed.password or parsed.port not in (None, 443)
            or not parsed.query or len(url) > 16384):
        raise ValueError('下载地址格式不兼容')
    return parsed


def read_header(http, url):
    """读取32字节，HTTP错误只提取状态码和已知COS错误码。"""
    validate_url(url)
    try:
        with http.open(urllib.request.Request(url, headers={'Range': 'bytes=0-31'}), timeout=30) as response:
            header = response.read(32)
            valid = len(header) == 32 and struct.unpack_from('<II', header) == (19921010, 2)
            return {'http_status': response.status, 'bytes_read': len(header),
                    'valid_snapshot_header': valid}
    except urllib.error.HTTPError as error:
        raw = error.read(32769)
        code = None
        try:
            if len(raw) <= 32768:
                code = ET.fromstring(raw).findtext('Code')
        except ET.ParseError:
            pass
        return {'http_status': error.code, 'bytes_read': 0,
                'cos_error_code': code if code in ERROR_CODES else 'Other'}


def diagnose(api, http, uin, max_records=32, now=None):
    now = time.time() if now is None else now
    group_raw = api(34, p.number(1, uin) + p.number(2, 1) + p.number(3, 13) + p.number(5, 0))
    group_fields = p.fields(group_raw)
    if p.one(group_fields, 2, -1) != 0:
        raise ValueError('设备组查询失败')
    group = p.one(p.fields(p.one(group_fields, 1, b'')), 1)
    if not isinstance(group, int) or group <= 0:
        raise ValueError('没有可用设备组')
    metadata = p.fields(api(44, p.number(1, uin) + p.number(2, group)))
    if p.one(metadata, 1, -1) != 0:
        raise ValueError('快照元数据查询失败')
    records = metadata.get(2, [])
    rows = []
    for index, raw in enumerate(records[:max_records], 1):
        record = p.fields(raw)
        device = p.one(record, 1)
        detail = p.fields(p.one(record, 2, b''))
        version = p.one(detail, 6)
        metadata_url = urllib.parse.urlparse(p.one(detail, 8, b'').decode())
        filename = metadata_url.path.rsplit('/', 1)[-1]
        keys = [('metadata_filename', filename)] if filename else []
        native_key = f'{device}_{version}'
        if isinstance(device, int) and device > 0 and isinstance(version, int) and version > 0 and native_key != filename:
            keys.append(('device_version', native_key))
        common = {'record': index, 'metadata_has_url': bool(metadata_url.netloc),
                  'metadata_filename_matches_native_key': filename == native_key,
                  'key_version_matches_current': version == p.one(metadata, 3)}
        modified = p.one(detail, 2)
        if isinstance(modified, int) and 946684800000 <= modified <= (now + 86400) * 1000:
            common['metadata_age_days'] = round((now - modified / 1000) / 86400, 2)
        if not keys:
            rows.append(common | {'result': 'no_snapshot_key'})
        for source, key in keys:
            row = common | {'candidate': source}
            extra = json.dumps({'group_id': str(group), 'key': key}, separators=(',', ':'))
            credential = p.fields(api(60, p.number(1, 5) + p.blob(2, extra) + p.number(3, 7)))
            # COS响应不是通用status消息；字段6不能当成错误码。
            if not p.one(credential, 4, b''):
                rows.append(row | {'result': 'credential_failed'})
                continue
            url = p.one(credential, 4, b'').decode()
            parsed = validate_url(url)
            row.update(credential_filename_matches_requested=parsed.path.rsplit('/', 1)[-1] == key,
                       credential_host_matches_metadata=parsed.hostname == metadata_url.hostname,
                       credential_parent_matches_metadata=parsed.path.rsplit('/', 1)[0] == metadata_url.path.rsplit('/', 1)[0])
            if not row['credential_filename_matches_requested']:
                rows.append(row | {'result': 'credential_path_mismatch'})
                continue
            row.update(read_header(http, url))
            if row.get('valid_snapshot_header'):
                row['result'] = 'snapshot_header_available'
            elif row.get('http_status') == 404 and row.get('cos_error_code') == 'NoSuchKey':
                row['result'] = 'metadata_object_not_found'
            else:
                row['result'] = 'download_or_header_failed'
            rows.append(row)
    return {'metadata_records': len(records), 'records_checked': min(len(records), max_records),
            'valid_snapshot_headers': sum(row.get('valid_snapshot_header', False) for row in rows),
            'missing_objects': sum(row.get('result') == 'metadata_object_not_found' for row in rows),
            'rows': rows}


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--state', type=Path, default=p.STATE, help='已有的关联身份目录')
    ap.add_argument('--max-records', type=int, default=32, choices=range(1, 65), metavar='1-64')
    args = ap.parse_args()
    os.umask(0o077)
    p.STATE = args.state.expanduser().resolve()
    with (p.STATE / 'identity.lock').open('a+') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        identity = json.loads((p.STATE / 'identity.json').read_text())
    uin = identity['uin']

    def api(sub, body):
        if sub not in (34, 44, 60):
            raise ValueError('拒绝非只读请求')
        deadline = time.monotonic() + 20
        with (p.STATE / 'identity.lock').open('a+') as lock:
            while True:
                try:
                    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    break
                except BlockingIOError:
                    if time.monotonic() >= deadline:
                        raise TimeoutError('身份锁忙')
                    time.sleep(.2)
            current = json.loads((p.STATE / 'identity.json').read_text())
            if current['uin'] != uin:
                raise ValueError('关联身份已变化')
            client = p.Probe(current)
            started = int(time.time() * 1000)
            stamp = p.one(p.fields(client.request('/timestamp', b'')), 1)
            client.offset = stamp - (started + int(time.time() * 1000)) // 2
            return client.api(sub, body)

    http = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())
    print(json.dumps(diagnose(api, http, uin, args.max_records), ensure_ascii=False, indent=2))


if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        # 异常文本可能含签名URL、请求头或私有路径，不能直接输出。
        print(json.dumps({'error': type(error).__name__,
                          'message': '检查失败，先核对身份状态与网络/代理；未自动重试。'}, ensure_ascii=False), file=sys.stderr)
        sys.exit(1)
