#!/usr/bin/env python3
"""隔离 Xvfb 或 Sway 上验证真实系统剪贴板与同步入口，不访问账号或网络。"""
import argparse
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'cloud'))
sys.path.insert(0, str(ROOT / 'tests'))
from 系统剪贴板 import DesktopClipboard
from 剪贴板同步 import Synchronizer
from test_clipboard_sync import MemoryGroup


def settle(check):
    """剪贴板工具在后台接管选区，等待外部写入生效。"""
    deadline = time.monotonic() + 2
    while not check():
        if time.monotonic() > deadline:
            raise AssertionError('剪贴板写入未生效')
        time.sleep(.05)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--backend', choices=('x11', 'wayland'), default='x11')
    args = parser.parse_args()
    with tempfile.TemporaryDirectory() as directory:
        display_file = Path(directory) / 'display'
        env = dict(os.environ)
        env.pop('WAYLAND_DISPLAY', None)
        env.pop('DISPLAY', None)
        if args.backend == 'x11':
            with display_file.open('wb') as stream:
                server = subprocess.Popen(['Xvfb', '-displayfd', str(stream.fileno()), '-screen', '0', '800x600x24', '-nolisten', 'tcp'],
                                          pass_fds=(stream.fileno(),), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        else:
            runtime = Path(directory) / 'runtime'
            runtime.mkdir(mode=0o700)
            config = Path(directory) / 'sway.conf'
            config.write_text('seat seat0 fallback true\nxwayland disable\n')
            env.update(XDG_RUNTIME_DIR=str(runtime), WLR_BACKENDS='headless', WLR_RENDERER='pixman', WLR_LIBINPUT_NO_DEVICES='1')
            server = subprocess.Popen(['sway', '-c', str(config)], env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        try:
            # CI 机器上虚拟桌面启动偶尔超过 5 秒，最多等 30 秒。
            for _ in range(300):
                ready = display_file.read_text().strip() if args.backend == 'x11' else next((p.name for p in runtime.glob('wayland-*') if not p.name.endswith('.lock')), '')
                if ready:
                    break
                if server.poll() is not None:
                    raise RuntimeError('隔离桌面启动失败')
                time.sleep(.1)
            if not ready:
                raise TimeoutError('隔离桌面未就绪')
            env['DISPLAY' if args.backend == 'x11' else 'WAYLAND_DISPLAY'] = ':' + ready if args.backend == 'x11' else ready
            assert DesktopClipboard('auto', env).backend == args.backend
            desktop = DesktopClipboard(args.backend, env)
            if args.backend == 'x11':
                subprocess.run(['xclip', '-selection', 'primary', '-in'], input=b'primary-stays-local', env=env, check=True,
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                settle(lambda: subprocess.run(['xclip', '-selection', 'primary', '-out'], env=env, capture_output=True).stdout
                       == b'primary-stays-local')
            desktop.write('已有文本\n', expected=desktop.read())
            group = MemoryGroup()
            sync = Synchronizer(desktop, group, Path(directory) / 'cursor.json')
            sync.step()
            assert not group.sent
            desktop.write('Linux 到手机\n\n', expected=desktop.read())
            sync.step()
            assert group.sent[0][0] == 'Linux 到手机\n\n'
            group.receive('手机到 Linux\n', version=7)
            sync.step()
            sync.step()
            assert desktop.read() == '手机到 Linux\n'
            assert len(group.sent) == 1
            assert (sync.status()['sent'], sync.status()['received']) == (1, 1)
            if args.backend == 'x11':
                actual = subprocess.check_output(['xclip', '-selection', 'primary', '-out'], env=env)
                assert actual == b'primary-stays-local'
            # 文件 URI 不属于首版文本同步范围。
            uri_command = ['xclip', '-selection', 'clipboard', '-in', '-target', 'text/uri-list'] if args.backend == 'x11' else ['wl-copy', '--type', 'text/uri-list']
            subprocess.run(uri_command,
                           input=b'file:///synthetic/example\n', env=env, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            settle(lambda: desktop.read() is None)
            sync.step()
            assert len(group.sent) == 1
            print(args.backend + ' 隔离桌面：双向 UTF-8、换行、首启基线、防回传、文件过滤均通过；官方网络请求为 0。')
        finally:
            server.terminate()
            try:
                server.wait(timeout=5)
            except subprocess.TimeoutExpired:
                server.kill()
                server.wait()


if __name__ == '__main__':
    main()
