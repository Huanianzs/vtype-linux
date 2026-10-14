#!/usr/bin/env python3
"""为同组单个官方来源设备请求新快照；默认只预览，--send发送一次控制请求。"""
import argparse
import fcntl
import json
import os
from pathlib import Path
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'cloud'))
import 官方同步探针 as p
from 快照恢复 import Client, group_and_metadata, make_refresh_request, encode


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--state', type=Path, default=p.STATE)
    ap.add_argument('--peer', type=int, help='来源设备编号；默认使用关联时的来源设备')
    actions = ap.add_mutually_exclusive_group()
    actions.add_argument('--send', action='store_true')
    actions.add_argument('--clear', action='store_true', help='清除本次重建请求，不删除来源快照')
    args = ap.parse_args()
    os.umask(0o077)
    client = Client(args.state)
    peer = args.peer
    if peer is None:
        pair = json.loads((client.state / 'pair-result.json').read_text())
        peer = int(pair['peer']['uin'])
    # 独立操作锁防止两次人工调用并发提交；API请求仍分别持identity.lock。
    with (client.state / 'snapshot-refresh.lock').open('a+') as operation:
        fcntl.flock(operation, fcntl.LOCK_EX | fcntl.LOCK_NB)
        gid, members, metadata = group_and_metadata(client, client.uin)
        timestamp = client.now_ms()
        receipt = client.state / 'snapshot-refresh-receipt.json'
        if args.clear:
            entry = json.loads(receipt.read_text())
            if (entry['uin'], entry['peer'], entry['group']) != (client.uin, peer, gid):
                raise ValueError('回执身份或组已变化')
            if entry.get('state') == 'cleared':
                print(json.dumps({'mode': 'clear', 'already_cleared': True}))
                return
            original = entry['original_detail_hex']
            detail = bytes.fromhex(original) if original is not None else encode({1: [1], 6: [p.one(metadata, 3)]})
            body = p.blob(1, p.number(1, client.uin) + p.blob(2, detail)) + p.number(2, gid)
            client.allowed_cleanup = body
            status = p.one(p.fields(client(43, body)), 1, -1)
            if status == 0:
                entry['state'] = 'cleared'
                receipt.write_text(json.dumps(entry))
            print(json.dumps({'mode': 'clear', 'server_accepted': status == 0,
                              'source_snapshots_deleted': False, 'local_dictionary_opened': False}))
            return 0 if status == 0 else 2
        body, original = make_refresh_request(client.uin, peer, gid, members, metadata, timestamp)
        report = {'mode': 'send' if args.send else 'preview', 'source_is_known_member': True,
                  'target_members': 1, 'group_members': len(members), 'local_dictionary_opened': False,
                  'linux_snapshot_uploaded': False, 'source_may_upload_existing_dictionary': True}
        if args.send:
            if receipt.exists():
                previous = json.loads(receipt.read_text())
                if previous.get('peer') == peer and timestamp - previous.get('timestamp_ms', 0) < 3600000:
                    raise ValueError('一小时内已有该来源请求；先查询结果，不重复发送')
            # 保存原状态与请求回执以便核对或恢复；不保存词库，不进入公开报告。
            entry = {'uin': client.uin, 'peer': peer, 'group': gid, 'timestamp_ms': timestamp,
                     'original_detail_hex': None if original is None else original.hex(), 'state': 'attempting'}
            receipt.write_text(json.dumps(entry));receipt.chmod(0o600)
            client.allowed_refresh = peer, gid
            response = client(43, body)
            status = p.one(p.fields(response), 1, -1)
            entry['state'] = 'accepted' if status == 0 else 'rejected'
            receipt.write_text(json.dumps(entry))
            report.update(server_accepted=status == 0, source_upload_observed=False)
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 2 if args.send and not report.get('server_accepted') else 0


if __name__ == '__main__':
    try:
        sys.exit(main() or 0)
    except Exception as error:
        print(json.dumps({'error': type(error).__name__, 'message': '操作未完成；未自动重试，先检查已有回执、身份与网络。'}, ensure_ascii=False), file=sys.stderr)
        sys.exit(1)
