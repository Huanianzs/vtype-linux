"""显式启用的双向文本剪贴板同步，不保存剪贴板正文。"""
import hashlib
import argparse
import json
import os
import fcntl
import signal
import subprocess
import sys
import threading
import time
import secrets
from pathlib import Path
from 剪贴板协议 import MAX_RECEIVE_TEXT_BYTES, MAX_TEXT_BYTES, TEXT_COS, TEXT_INLINE, NotSent
from 运行支持 import write_doc

_UNSET = object()
REFRESH_AFTER = 600


def fingerprint(text):
    return hashlib.sha256(text.encode()).hexdigest() if text is not None else None


class Synchronizer:
    """一次 step 观察本地复制并按需查询远端；桌面和设备组可替换。"""
    def __init__(self, desktop, protocol, state_file, allowed=lambda: True):
        self.desktop = desktop
        self.protocol = protocol
        self.allowed = allowed
        self.state_file = Path(state_file)
        self.state = json.loads(self.state_file.read_text()) if self.state_file.exists() else {'consumed': {}}
        self.observed = _UNSET
        self.pending_text = None
        self.receiving_hash = None
        self.context = None
        self.counts = {'sent': 0, 'received': 0}

    def status(self):
        return dict(self.counts, send_unknown=bool(self.state.get('intent')))

    def checkpoint(self, value):
        write_doc(self.state_file, value)
        self.state = value

    def observe(self, current):
        digest = fingerprint(current)
        if self.receiving_hash is not None and digest == self.receiving_hash:
            self.observed = digest
            self.pending_text = None
            return
        if self.observed is not _UNSET and digest != self.observed:
            self.pending_text = current if current and len(current.encode()) <= MAX_TEXT_BYTES else None
            self.receiving_hash = None
        self.observed = digest

    def step(self, poll=True):
        if not self.allowed():
            return
        current = self.desktop.read()
        self.observe(current)
        if not poll or not self.allowed():
            return
        snapshot = self.protocol.fetch()
        key = f'{snapshot.own}:{snapshot.group}'
        if self.context is not None and self.context != key:
            self.pending_text = None
        self.context = key
        message = snapshot.message
        # 查询期间也可能发生复制；新的本地复制优先于同一轮读到的远端文字。
        current = self.desktop.read()
        self.observe(current)
        if self.pending_text is not None:
            if not self.allowed():
                return
            trace = secrets.token_hex(16)
            value = dict(self.state)
            value['intent'] = {'context': key, 'trace': trace, 'hash': fingerprint(self.pending_text),
                               'floor': message.version if message else value['consumed'].get(key, 0)}
            self.checkpoint(value)
            try:
                version = self.protocol.send(snapshot, self.pending_text, trace)
            except NotSent:
                value = dict(self.state); value.pop('intent', None)
                self.checkpoint(value)
                raise
            except Exception:
                self.pending_text = None
                raise
            self.pending_text = None
            value = dict(self.state)
            value.pop('intent', None)
            value['consumed'] = dict(value['consumed'], **{key: version})
            self.checkpoint(value)
            self.counts['sent'] += 1
            return
        intent = self.state.get('intent')
        if intent and intent['context'] == key and message:
            if (message.source == snapshot.own and message.trace == intent['trace']
                    and fingerprint(message.text) == intent['hash']):
                value = dict(self.state); value.pop('intent', None)
                value['consumed'] = dict(value['consumed'], **{key: message.version})
                self.checkpoint(value)
                self.counts['sent'] += 1
                return
            if message.version <= intent['floor']:
                return
        if not message or message.version <= self.state['consumed'].get(key, 0):
            return
        if (not message.source or message.source not in snapshot.members or message.source == snapshot.own
                or snapshot.own not in snapshot.members or message.expires * 1000 <= snapshot.now_ms
                or not message.trace or message.kind not in (TEXT_INLINE, TEXT_COS)):
            return
        if not self.allowed():
            return
        text = self.protocol.text(message)
        if not text or '\0' in text or len(text.encode()) > MAX_RECEIVE_TEXT_BYTES:
            return
        if not self.allowed():
            return
        # 写入工具可能已改变系统剪贴板，但确认读取失败；下轮仍须抑制回传。
        self.receiving_hash = fingerprint(text)
        self.desktop.write(text, expected=current)
        self.observed = fingerprint(text)
        value = dict(self.state)
        value.pop('intent', None)
        value['consumed'] = dict(value['consumed'], **{key: message.version})
        self.checkpoint(value)
        self.counts['received'] += 1


def config_path():
    return Path(os.environ.get('XDG_CONFIG_HOME', Path.home() / '.config')) / 'wetype-ime/clipboard.json'


def service_path():
    return config_path().parents[1] / 'systemd/user/wetype-clipboard.service'


def configure_service(state, entry):
    from 配置与配对 import quote_unit
    from 运行支持 import atomic, wxc_binary
    unit = service_path()
    if unit.exists() and '# VType clipboard service' not in unit.read_text():
        raise RuntimeError('wetype-clipboard.service 已被其他服务使用')
    body = ('# VType clipboard service\n[Unit]\nDescription=WeType clipboard text sync\n'
            # 不少桌面（如 KDE 5.24 默认会话）不激活 graphical-session.target，同时挂到 default.target；
            # 早于桌面启动时拿不到显示环境会失败退出，由 Restart 每 10 秒重试，直到桌面就绪。
            'PartOf=graphical-session.target\nAfter=graphical-session.target\nStartLimitIntervalSec=0\n'
            '[Service]\nType=simple\nUMask=0077\nNoNewPrivileges=yes\nRestart=on-failure\nRestartSec=10\n'
            # 剪贴板工具后台持有已收到的文字；停同步不终止其所有权进程。
            'KillMode=process\n'
            'Environment=' + quote_unit('WETYPE_WXC=' + wxc_binary()) + '\n'
            'Environment=' + quote_unit('PATH=' + os.environ.get('PATH', '/usr/bin:/bin')) + '\n'
            + ('Environment=' + quote_unit('WETYPE_SNAPPY_LIBRARY=' + os.environ['WETYPE_SNAPPY_LIBRARY']) + '\n'
               if os.environ.get('WETYPE_SNAPPY_LIBRARY') else '')
            + 'ExecStart=' + quote_unit(sys.executable) + ' ' + quote_unit(entry) +
            ' --state ' + quote_unit(state) + ' clipboard run\n'
            '[Install]\nWantedBy=graphical-session.target default.target\n')
    atomic(unit, body.encode())


def disable():
    path = config_path()
    if path.exists():
        value = json.loads(path.read_text())
        value['enabled'] = False
        write_doc(path, value)
    unit = service_path()
    if unit.exists() and '# VType clipboard service' in unit.read_text():
        subprocess.run(['systemctl', '--user', 'disable', '--now', 'wetype-clipboard.service'],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=15)


def running(state):
    lock = Path(state) / 'clipboard.lock'
    if not lock.exists():
        return False
    with lock.open('rb') as stream:
        try:
            fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return True
    return False


def run_daemon(config, state):
    from 系统剪贴板 import DesktopClipboard
    from 剪贴板协议 import OfficialClipboard
    from 运行支持 import refresh_client
    import 官方同步探针 as p
    p.STATE = state
    if Path(config['state_dir']).resolve() != state or not (state / 'identity.json').is_file():
        raise RuntimeError('启用配置与设备身份目录不一致，请重新启用剪贴板同步')
    stopped = threading.Event()
    path = config_path()
    def allowed():
        if stopped.is_set() or not path.exists():
            return False
        current = json.loads(path.read_text())
        return (bool(current.get('enabled')) and Path(current.get('state_dir', '')).resolve() == state
                and current.get('backend', 'auto') == config.get('backend', 'auto'))
    with (state / 'clipboard.lock').open('a+') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise RuntimeError('已有剪贴板同步进程，请勿重复运行') from None
        desktop = DesktopClipboard(config.get('backend', 'auto'))
        sync = Synchronizer(desktop, OfficialClipboard(state), state / 'clipboard-state.json', allowed)
        previous = {sig: signal.signal(sig, lambda *_: stopped.set()) for sig in (signal.SIGTERM, signal.SIGINT)}
        next_poll = next_refresh = 0
        failures = 0
        result = {'backend': desktop.backend if hasattr(desktop, 'backend') else config['backend'], 'error': None}
        try:
            while allowed():
                now = time.monotonic()
                if now >= next_refresh:
                    # 五分钟刷新任务会续期身份；只在身份久未更新时自己握手，wxc 握手期间独占身份锁。
                    try:
                        if time.time() - (state / 'identity.json').stat().st_mtime > REFRESH_AFTER:
                            refresh_client()
                        result['refresh_error'] = None
                    except Exception as error:
                        result['refresh_error'] = type(error).__name__
                    next_refresh = time.monotonic() + 60
                poll = now >= next_poll
                try:
                    sync.step(poll=poll)
                    result['error'] = None
                    if poll:
                        failures = 0
                        next_poll = now + 5
                except Exception as error:
                    # 只记录错误类别；异常正文可能包含网络响应或私有文件信息。
                    result['error'] = type(error).__name__
                    if poll:
                        failures = min(failures + 1, 4)
                        next_poll = time.monotonic() + min(60, 5 * 2 ** failures)
                result.update(sync.status(), updated=int(time.time()), send_unknown=bool(sync.state.get('intent')))
                write_doc(state / 'clipboard-status.json', result)
                if allowed():
                    stopped.wait(1)
        finally:
            for sig, handler in previous.items():
                signal.signal(sig, handler)
    return 0


def main(argv=None, state=None, entry=None):
    os.umask(0o077)
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='action', required=True)
    commands.add_parser('status', help='显示开关及运行状态，不输出剪贴板内容')
    commands.add_parser('run', help='运行已启用的同步，关闭时直接退出')
    enable = commands.add_parser('enable', help='启用自动双向文本同步，会发送之后新复制的文本')
    enable.add_argument('--backend', choices=('auto', 'x11', 'wayland'), default='auto')
    commands.add_parser('disable', help='关闭剪贴板同步，保留设备身份')
    args = parser.parse_args(argv)
    path = config_path()
    config = json.loads(path.read_text()) if path.exists() else {}
    state = Path(state).resolve()
    if args.action == 'status':
        private_status = state / 'clipboard-status.json'
        result = json.loads(private_status.read_text()) if private_status.exists() else {}
        result.update(enabled=bool(config.get('enabled')), running=running(state))
        print(json.dumps(result, ensure_ascii=False))
        return 0
    if args.action == 'disable':
        disable()
        print('剪贴板同步已关闭，设备身份保留。')
        return 0
    if args.action == 'enable':
        from 系统剪贴板 import DesktopClipboard
        from 运行支持 import wxc_binary
        state = Path(state).resolve()
        if not (state / 'identity.json').is_file():
            raise RuntimeError('尚未关联官方客户端，请先执行 pair')
        desktop = DesktopClipboard(args.backend)
        desktop.read()
        wxc_binary()
        configure_service(state, entry)
        value = {'enabled': True, 'state_dir': str(state), 'backend': args.backend}
        print('启用期间，新复制的文本会发给微信输入法服务器，并接收同组设备的文本。')
        print('请先在官方客户端开启跨设备复制粘贴；图片和文件不会同步，超过 256 KiB 的文本只接收不发送。')
        try:
            names = [name for name in ('DISPLAY', 'WAYLAND_DISPLAY', 'XAUTHORITY', 'XDG_RUNTIME_DIR', 'XDG_SESSION_TYPE') if os.environ.get(name)]
            subprocess.run(['systemctl', '--user', 'import-environment', *names], check=True, timeout=15)
            subprocess.run(['systemctl', '--user', 'daemon-reload'], check=True, timeout=15)
            write_doc(path, value)
            subprocess.run(['systemctl', '--user', 'enable', 'wetype-clipboard.service'], check=True, timeout=15)
            subprocess.run(['systemctl', '--user', 'restart', 'wetype-clipboard.service'], check=True, timeout=15)
        except Exception:
            value['enabled'] = False
            write_doc(path, value)
            raise RuntimeError('未能启动用户服务，剪贴板同步已关闭') from None
        print('自动剪贴板同步已启用；clipboard status 查看状态，clipboard disable 关闭。')
        return 0
    if not config.get('enabled'):
        return 0
    return run_daemon(config, state)
