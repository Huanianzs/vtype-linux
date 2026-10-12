#!/usr/bin/env python3
"""只读下载兼容公共词库到新目录，生成对应 harness 元数据；不改运行中的输入法。"""
import argparse
import fcntl
import hashlib
import io
import json
import os
import shutil
import sys
import urllib.parse
import urllib.request
import zipfile
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'cloud'))
import 官方同步探针 as p
from 公共资源 import request


def digest(data):
    return hashlib.md5(data).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runtime', type=Path, default=Path.home() / '.local/lib/wetype-ime/arm64')
    parser.add_argument('--output', type=Path, required=True, help='不存在的新输出目录；只在此写入')
    args = parser.parse_args(); os.umask(0o077)
    output = args.output.expanduser().resolve(); runtime = args.runtime.expanduser().resolve()
    if output.exists():
        raise ValueError('输出目录已存在，请使用新的目录；不会覆盖已有资源')
    if output == runtime or runtime in output.parents:
        raise ValueError('不接受运行时内部路径，请使用独立暂存目录')
    versions = json.loads((ROOT / 'cloud/resource_versions.json').read_text())
    index = {x['name']: x for x in json.loads((runtime / 'dicts/index.json').read_text())}
    # 收齐元数据后才创建输出目录；不落签名下载地址。
    with (p.STATE / 'identity.lock').open('a+') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        client = p.Probe(json.loads((p.STATE / 'identity.json').read_text()))
        payloads = [client.api(command, request(list(index.values()), versions, hot))
                    for command, hot in [(6, True), (5, False)]]
    output.mkdir(parents=True, mode=0o700)
    dicts = output / 'dicts'; shutil.copytree(runtime / 'dicts', dicts)
    http = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    updated = 0
    for payload in payloads:
        for raw in p.fields(payload).get(1, []):
            item = p.fields(raw); kind = p.one(item, 4)
            if kind not in (0, 1, 7, 9):
                continue
            if p.one(item, 12):
                raise ValueError('出现删除资源标志，需核对版本后再处理')
            name = p.one(item, 1, b'').decode()
            if not name or Path(name).name != name:
                raise ValueError('无效资源文件名')
            full = p.fields(p.one(item, 7, b''))
            url = p.one(full, 1, b'').decode()
            parsed = urllib.parse.urlparse(url)
            if parsed.scheme != 'https' or p.one(full, 8) not in (0, 1):
                raise ValueError('未知下载或加密格式')
            with http.open(url, timeout=30) as response:
                data = response.read(64 * 1024 * 1024 + 1)
            compression = p.one(full, 5)
            expected = p.one(full, 6 if compression == 1 else 2, b'').decode()
            if len(data) > 64 * 1024 * 1024 or digest(data) != expected:
                raise ValueError('下载资源校验失败')
            if compression == 1:
                with zipfile.ZipFile(io.BytesIO(data)) as archive:
                    files = [x for x in archive.infolist() if not x.is_dir()]
                    if len(files) != 1 or files[0].file_size > 200 * 1024 * 1024:
                        raise ValueError('未知压缩包结构')
                    data = archive.read(files[0])
                if digest(data) != p.one(full, 2, b'').decode():
                    raise ValueError('解压资源校验失败')
            elif compression != 0:
                raise ValueError('未知压缩格式')
            expected = p.one(item, 6, b'').decode()
            if digest(data) != expected:
                raise ValueError('最终资源校验失败')
            (dicts / name).write_bytes(data)
            index[name] = {'name': name, 'md5': expected, 'type': p.one(item, 3),
                           'uniqueID': p.one(item, 21, b'').decode() or name,
                           'version': p.one(item, 2), 'timestamp': p.one(item, 5),
                           'is_cell': kind == 1, 'in_ime_data': True, 'dict_type': kind,
                           'support_update': True}
            updated += 1
    if len(index) > 64:
        raise ValueError('超过固定版本词库表容量')
    rows = list(index.values())
    (dicts / 'index.json').write_text(json.dumps(rows, ensure_ascii=False))
    table = '/* 由已校验资源生成，is_cell 决定原生加载接口。 */\n'
    table += 'static const struct { const char *name; int type; int version; int is_cell; } g_dict_table[] = {\n'
    for row in rows:
        table += '    {' + json.dumps(row['name']) + ', ' + str(int(row['type'])) + ', '
        table += str(int(row['version'])) + ', ' + str(int(bool(row['is_cell']))) + '},\n'
    (output / 'dict_table.h').write_text(table + '};\n')
    print(json.dumps({'resources': len(rows), 'updated': updated, 'output': str(output),
                      'installed_runtime_changed': False}, ensure_ascii=False))


if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        # 不把含签名的 URL 或官方响应打印到共享终端。
        print('资源准备未完成：' + type(error).__name__ + '；检查网络、代理及版本。', file=sys.stderr)
        sys.exit(1)
