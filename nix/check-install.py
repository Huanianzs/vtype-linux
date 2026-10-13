#!/usr/bin/env python3
"""从空 HOME 安装真实 APK，验证本地输入和离线云代理启动；只用私有 D-Bus。"""
import argparse
import importlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from test_bionic_upgrade import isolated_bus


def run(package, apk):
    with tempfile.TemporaryDirectory(prefix='vtype-clean-install.') as directory:
        root = Path(directory)
        home = root / 'home'
        home.mkdir()
        env = dict(os.environ, HOME=str(home), XDG_CONFIG_HOME=str(root / 'config'),
                   XDG_DATA_HOME=str(root / 'data'), XDG_STATE_HOME=str(root / 'state'),
                   XDG_CACHE_HOME=str(root / 'cache'), XDG_DATA_DIRS=str(package / 'share'))
        for name in ('WETYPE_ENGINE_DIR', 'WETYPE_SYSROOT', 'WETYPE_DICT_DIR', 'WETYPE_WORK_DIR',
                     'WETYPE_CLOUD_CONFIG', 'QEMU_AARCH64', 'DISPLAY', 'WAYLAND_DISPLAY'):
            env.pop(name, None)
        engine = home / '.local/lib/wetype-ime/arm64'
        setup = [str(package / 'bin/wetype-setup'), '--apk', str(apk)]
        subprocess.run(setup, env=dict(env, PATH='/nonexistent'), check=True)
        subprocess.run([str(package / 'bin/wetype-check')], env=env, check=True)
        print('PASS 空 HOME 初始化与引擎自检', flush=True)
        subprocess.run([str(package / 'bin/wetype-check')],
                       env=dict(env, QEMU_SET_ENV='LD_PRELOAD=' + str(package / 'libexec/libwetype-cloud.so')),
                       check=True)
        print('PASS 云桥接库在 bionic 引擎中加载（不联网）', flush=True)
        # 重复初始化保留已更新的预置词库和个人数据；包资源仍指向当前版本。
        (engine / 'dicts/local-sentinel').write_text('keep preset')
        personal = root / 'data/wetype-ime/dict/keep-sentinel'
        personal.parent.mkdir(parents=True, exist_ok=True)
        personal.write_text('keep personal')
        subprocess.run(setup, env=env, check=True)
        assert (engine / 'dicts/local-sentinel').read_text() == 'keep preset'
        assert personal.read_text() == 'keep personal'
        assert list(engine.parent.glob('arm64-backup.*'))
        print('PASS 重复初始化、备份和数据保留', flush=True)

        # 合成 enable --timer 的完整配置；不关联设备、不调用网络或真实 systemd。
        launcher = re.search(r'^exec (\S+)', (package / 'bin/wetype-cloud').read_text(), re.MULTILINE).group(1)
        code = """import sys
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0, sys.argv[1])
import 配置与配对 as setup
with patch.object(setup, 'refresh_client'), patch.object(setup, 'query_group'), patch.object(setup.subprocess, 'run'):
    setup.main(['enable', '--timer'])
"""
        subprocess.run([launcher, '-c', code, str(package / 'share/vtype-linux/cloud')], env=env, check=True)
        cloud = root / 'config/wetype-ime/cloud.json'
        config = json.loads(cloud.read_text())
        assert Path(config['shim']).is_file()
        assert Path(config['protocol_dir']).resolve() == (package / 'share/vtype-linux/cloud').resolve()
        service = (root / 'config/systemd/user/wetype-sync.service').read_text()
        assert '/usr/bin/python3' not in service and 'WETYPE_WXC=' in service
        cloud.write_text('{"enabled": false}')
        print('PASS 云配置、桥接库和定时刷新路径（合成身份，不联网）', flush=True)

        with isolated_bus(directory) as address:
            os.environ.clear()
            os.environ.update(env, DBUS_SESSION_BUS_ADDRESS=address)
            config_dir = root / 'config/fcitx5'
            config_dir.mkdir(parents=True)
            (config_dir / 'profile').write_text(
                '[Groups/0]\nName=Default\nDefault Layout=us\nDefaultIM=wetype-im\n'
                '[Groups/0/Items/0]\nName=keyboard-us\nLayout=\n'
                '[Groups/0/Items/1]\nName=wetype-im\nLayout=\n[GroupOrder]\n0=Default\n')
            import dbus
            from dbus.mainloop.glib import DBusGMainLoop
            DBusGMainLoop(set_as_default=True)
            registry = dbus.SessionBus()
            for mode in ('local', 'cloud-launcher'):
                log_path = root / (mode + '.log')
                os.environ['WETYPE_PAGETEST_LOG'] = str(log_path)
                if mode == 'local':
                    os.environ['WETYPE_CLOUD_CONFIG'] = str(root / 'absent.json')
                else:
                    os.environ['WETYPE_CLOUD_CONFIG'] = str(cloud)
                with log_path.open('wb') as log:
                    process = subprocess.Popen(
                        ['fcitx5', '--disable=classicui,xim,waylandim,wayland,xcb'],
                        stdout=log, stderr=subprocess.STDOUT)
                    try:
                        os.environ['WETYPE_E2E_FCITX_PID'] = str(process.pid)
                        for _ in range(100):
                            if registry.name_has_owner('org.fcitx.Fcitx5'):
                                break
                            assert process.poll() is None, '私有 Fcitx 启动失败'
                            time.sleep(.05)
                        else:
                            raise AssertionError('私有 Fcitx 未就绪')
                        sys.path.insert(0, str(ROOT / 'fcitx5-wetype/e2e'))
                        sys.modules.pop('dbus_test_client', None)
                        client_module = importlib.import_module('dbus_test_client')
                        client = client_module.Client('nix-clean-install')
                        client.focus()
                        client_module.pump(2)
                        client.type('nihao')
                        assert any('你好' in text for _, text in client.candidates), client.candidates
                        client.press('space', delay=.5)
                        assert client.commits[-1] == '你好', client.commits
                        print('PASS Nix 插件候选与上屏：' + mode, flush=True)
                    except BaseException:
                        print(log_path.read_text(errors='replace')[-3000:], file=sys.stderr)
                        raise
                    finally:
                        process.terminate()
                        process.wait(timeout=15)
                for _ in range(100):
                    if not registry.name_has_owner('org.fcitx.Fcitx5'):
                        break
                    time.sleep(.05)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--package', type=Path, required=True)
    parser.add_argument('--apk', type=Path, required=True)
    args = parser.parse_args()
    run(args.package.resolve(), args.apk.resolve())
