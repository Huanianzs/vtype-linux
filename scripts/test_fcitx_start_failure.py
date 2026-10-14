#!/usr/bin/env python3
"""隔离验证引擎连续启动失败后的 Fcitx 存活，无需 APK、词库或账号。"""
import argparse
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--addon-prefix', type=Path, required=True)
    parser.add_argument('--private', action='store_true', help=argparse.SUPPRESS)
    args = parser.parse_args()
    prefix = args.addon_prefix.resolve()
    if not args.private:
        return subprocess.call(['dbus-run-session', '--', sys.executable, __file__,
                                '--addon-prefix', str(prefix), '--private'])
    import dbus
    from dbus.mainloop.glib import DBusGMainLoop
    DBusGMainLoop(set_as_default=True)
    with tempfile.TemporaryDirectory(prefix='vtype-start-failure-') as directory:
        root = Path(directory)
        config = root / 'config/fcitx5'
        config.mkdir(parents=True)
        (config / 'profile').write_text(
            '[Groups/0]\nName=Default\nDefault Layout=us\nDefaultIM=wetype-im\n'
            '[Groups/0/Items/0]\nName=keyboard-us\nLayout=\n'
            '[Groups/0/Items/1]\nName=wetype-im\nLayout=\n[GroupOrder]\n0=Default\n')
        os.environ.update(XDG_CONFIG_HOME=str(root / 'config'), XDG_DATA_HOME=str(root / 'data'),
            XDG_DATA_DIRS=str(prefix / 'share'), WETYPE_ENGINE_DIR=str(root / 'empty-engine'),
            WETYPE_WORK_DIR=str(root / 'dict'), WETYPE_HARNESS_LOG=str(root / 'engine.log'),
            WETYPE_PAGETEST_LOG=str(root / 'fcitx.log'), QEMU_AARCH64='/bin/false')
        for key in ('DISPLAY', 'WAYLAND_DISPLAY', 'WETYPE_CLOUD_CONFIG'):
            os.environ.pop(key, None)
        with (root / 'fcitx.log').open('wb') as log:
            proc = subprocess.Popen(['fcitx5', '--disable=classicui,xim,waylandim,wayland,xcb'],
                                    stdout=log, stderr=subprocess.STDOUT)
            try:
                os.environ['WETYPE_E2E_FCITX_PID'] = str(proc.pid)
                registry = dbus.SessionBus()
                for _ in range(100):
                    if registry.name_has_owner('org.fcitx.Fcitx5'):
                        break
                    assert proc.poll() is None, '隔离 Fcitx 启动失败'
                    time.sleep(.05)
                sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'fcitx5-wetype/e2e'))
                from dbus_test_client import Client, controller, pump
                client = Client('vtype-start-failure')
                client.focus()
                client.type('nihao', wait=False)
                deadline = time.monotonic() + 15
                while time.monotonic() < deadline:
                    assert proc.poll() is None, '引擎启动失败导致 Fcitx 崩溃'
                    if 'engine gave up after 5 failures' in (root / 'fcitx.log').read_text():
                        break
                    pump(.1)
                else:
                    raise AssertionError('未观察到有界的失败重试')
                assert controller.CurrentInputMethod() == 'wetype-im'
                pump(.5)
                assert proc.poll() is None
                print('PASS 引擎连续失败 5 次后 Fcitx 仍存活且 D-Bus 响应正常；不联网')
            finally:
                proc.terminate()
                try:
                    proc.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    proc.kill(); proc.wait()
    return 0


if __name__ == '__main__':
    sys.exit(main())
