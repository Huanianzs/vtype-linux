#!/usr/bin/env python3
"""从同组可用备份下载并解密快照，仅保存私有文件，不导入运行中的词库。"""
import argparse
import json
import os
from pathlib import Path
import sys
import time
import urllib.request
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'cloud'))
import 官方同步探针 as p
from 快照恢复 import Client
from 快照文件 import NoRedirect, download_available


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--state', type=Path, default=p.STATE)
    args = ap.parse_args()
    os.umask(0o077)
    client = Client(args.state)
    preferred = None
    pair = client.state / 'pair-result.json'
    if pair.exists():
        preferred = int(json.loads(pair.read_text())['peer']['uin'])
    output = client.state / ('snapshot-recovery-' + time.strftime('%Y%m%d-%H%M%S'))
    http = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())
    report = download_available(client, http, client.uin, output, preferred)
    # 只显示身份目录内的相对路径，报告不含来源标识、密钥或签名URL。
    print(json.dumps(report | {'saved_directory': output.name}, ensure_ascii=False, indent=2))
    return 0 if report['downloaded'] else 2


if __name__ == '__main__':
    try:
        sys.exit(main())
    except Exception as error:
        print(json.dumps({'error': type(error).__name__, 'message': '下载未完成；先检查身份和网络/代理，未自动重试。'}, ensure_ascii=False), file=sys.stderr)
        sys.exit(1)
