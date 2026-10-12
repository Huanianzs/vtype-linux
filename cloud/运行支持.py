"""宿主路径、原子私有文件写入与既有设备握手；不读写个人词库。"""
import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

DATA = Path(os.environ.get('XDG_DATA_HOME', Path.home() / '.local/share')) / 'wetype-ime'
PROD = DATA / 'dict'


def atomic(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd, temporary = tempfile.mkstemp(dir=path.parent, prefix='.pending-')
    try:
        with os.fdopen(fd, 'wb') as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def write_doc(path, value):
    atomic(path, json.dumps(value, ensure_ascii=False, indent=2).encode())


def wxc_binary():
    configured = os.environ.get('WETYPE_WXC')
    candidate = configured or shutil.which('wxc') or str(DATA / 'tools/node_modules/.bin/wxc')
    if not os.access(candidate, os.X_OK):
        raise RuntimeError('找不到 wxc；请安装 @mkdir700/wxc@0.1.0 或设置 WETYPE_WXC')
    return str(Path(candidate).resolve())


def refresh_client():
    import 官方同步探针 as p
    if not (p.STATE / 'identity.json').is_file():
        raise RuntimeError('尚未关联官方客户端，请先执行 pair')
    p.STATE.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd = os.open(p.STATE / 'handshake.log', os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, 'wb') as log:
        result = subprocess.run([wxc_binary(), '--state', str(p.STATE), '--timeout', '20',
                                 '--json', 'devices'], stdout=log, stderr=subprocess.STDOUT, timeout=30)
    if result.returncode:
        raise RuntimeError('已有设备握手失败；详情保存在私有 handshake.log')
    return json.loads((p.STATE / 'identity.json').read_text())
