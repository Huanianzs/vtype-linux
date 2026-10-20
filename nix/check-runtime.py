#!/usr/bin/env python3
"""验证包的运行库闭包及初始化入口；不下载 APK、不触碰用户运行目录。"""
import argparse
from pathlib import Path
import subprocess
import tempfile
import os

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--package', type=Path, required=True)
args = parser.parse_args()
package = args.package.resolve()
plugin = package / 'lib/fcitx5/libfcitx5-wetype.so'
assert os.fsencode(package / 'libexec/wetype-python') in plugin.read_bytes(), \
    '插件没有使用包内 Python 启动器，云代理会丢失包内依赖配置'
for name in ('wetype-harness', 'libandroid.so', 'libwetype-cloud.so',
             'sysroot/system/bin/linker64', 'sysroot/system/lib64/libc.so',
             'sysroot/system/lib64/libm.so', 'sysroot/system/lib64/libdl.so',
             'sysroot/system/lib64/liblog.so', 'sysroot/system/lib64/libz.so',
             'sysroot/system/lib64/libc++.so'):
    path = package / 'libexec' / name
    data = path.read_bytes()
    assert data[:4] == b'\x7fELF', name
    assert int.from_bytes(data[18:20], 'little') == 183, name  # AArch64
assert (package / 'libexec/sysroot/NOTICE').stat().st_size
assert (package / 'libexec/cloud_proxy.py').is_file()
with tempfile.TemporaryDirectory(prefix='vtype-package-check.') as directory:
    root = Path(directory)
    env = dict(os.environ, HOME=str(root), PATH='/nonexistent',
               XDG_DATA_HOME=str(root / 'data'), XDG_CACHE_HOME=str(root / 'cache'))
    env.pop('WETYPE_ENGINE_DIR', None)
    for name in ('wetype-setup', 'wetype-check', 'wetype-cloud'):
        subprocess.run([str(package / 'bin' / name), '--help'], env=env,
                       check=True, stdout=subprocess.DEVNULL)
    invalid = root / 'invalid.apk'
    invalid.write_bytes(b'invalid APK')
    result = subprocess.run([str(package / 'bin/wetype-setup'), '--apk', str(invalid)],
                            env=env, capture_output=True, text=True)
    assert result.returncode != 0 and 'SHA-256 mismatch' in result.stderr, result.stderr
    assert not (root / '.local/lib/wetype-ime/arm64').exists()
print('PASS ARM64 运行库闭包、离线命令入口和无效 APK 回滚')
