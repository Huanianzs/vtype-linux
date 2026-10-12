#!/usr/bin/env python3
"""检查 Git 待发布源码；只报告文件名和问题类别，不打印敏感内容。"""
import re
import subprocess
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
FORBIDDEN = {'.deps', 'private-state', 'research', 'downloads', 'logs', 'runtime',
             'AppDir', 'node_modules', '__pycache__'}
PRIVATE_NAMES = {'identity.json', 'cloud.json', 'pair-result.json', 'common-phrases.bin',
                 'AGENTS.md', 'context.md'}
PRIVATE_KEY = re.compile(rb'-----BEGIN (?:[A-Z]+ )?PRIVATE KEY-----')
SIGNED_URL = re.compile(rb'[?&](?:q-signature|X-Amz-Signature|Signature)=[a-zA-Z0-9%]{24,}')


def main():
    # 暂存变更后的完整树才是发布对象；不扫描被忽略的构建缓存和用户状态。
    names = subprocess.check_output(['git', '-C', str(ROOT), 'ls-files', '-z']).split(b'\0')
    problems = []
    for raw in names:
        if not raw:
            continue
        relative = Path(raw.decode())
        if FORBIDDEN.intersection(relative.parts) or relative.name in PRIVATE_NAMES:
            problems.append((str(relative), '私有或构建目录'))
        if relative.suffix.lower() in ('.apk', '.appimage', '.so', '.pem', '.key', '.pb', '.bin'):
            problems.append((str(relative), '二进制/私有文件类型'))
        try:
            data = subprocess.check_output(['git', '-C', str(ROOT), 'show', ':' + str(relative)])
        except subprocess.CalledProcessError:
            problems.append((str(relative), '无法读取暂存内容')); continue
        if PRIVATE_KEY.search(data) or SIGNED_URL.search(data):
            problems.append((str(relative), '疑似私钥或签名地址'))
        if re.search(rb'/(?:home|Users)/[A-Za-z0-9_.-]+/', data):
            problems.append((str(relative), '用户目录绝对路径'))
    for name, category in problems:
        print(category + '：' + name)
    print('公开源码检查：' + ('未通过' if problems else '通过'))
    return 1 if problems else 0


if __name__ == '__main__':
    sys.exit(main())
