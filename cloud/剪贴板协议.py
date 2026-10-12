"""官方设备组的纯文本剪贴板传输，协议依据见剪贴板文档。"""
from dataclasses import dataclass
import fcntl
import json
import time
from pathlib import Path
import 官方同步探针 as p

MAX_TEXT_BYTES = 256 * 1024


class SendUnknown(RuntimeError):
    """发送请求已经开始，无法确认服务器是否收到了文本。"""


class NotSent(RuntimeError):
    """发送前检查失败，本次没有发送文本。"""


@dataclass(frozen=True)
class ClipboardMessage:
    version: int
    source: int
    expires: int
    kind: int
    text: str
    trace: str


@dataclass(frozen=True)
class GroupSnapshot:
    group: int
    own: int
    members: frozenset
    message: ClipboardMessage | None
    now_ms: int


class OfficialClipboard:
    """单次操作期间持身份锁；发送前重新验证组号与成员。"""
    def __init__(self, state, probe_factory=p.Probe):
        self.state = Path(state)
        self.probe_factory = probe_factory
        self.client = None
        self.calibrated = 0

    def session(self):
        from contextlib import contextmanager
        @contextmanager
        def locked():
            with (self.state / 'identity.lock').open('a+') as lock:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
                identity = json.loads((self.state / 'identity.json').read_text())
                if (self.client is None or self.client.identity.get('server_key') != identity.get('server_key')
                        or self.client.identity.get('uin') != identity.get('uin')):
                    self.client = self.probe_factory(identity)
                    self.client.timeout = 2
                    self.calibrated = 0
                if time.monotonic() - self.calibrated > 60:
                    started = int(time.time() * 1000)
                    stamp = p.one(p.fields(self.client.request('/timestamp', b'')), 1)
                    self.client.offset = stamp - (started + int(time.time() * 1000)) // 2
                    self.calibrated = time.monotonic()
                yield self.client
        return locked()

    def group(self, client, include_clipboard):
        own = client.identity['uin']
        request = p.number(1, own) + p.number(2, 1) + p.number(3, 3 if include_clipboard else 1)
        if include_clipboard:
            request += p.number(4, 0)
        response = p.fields(client.api(34, request, persist_errors=False))
        if p.one(response, 2) != 0:
            raise NotSent('设备组查询失败')
        group = p.fields(p.one(response, 1, b''))
        group_id = p.one(group, 1)
        members = frozenset(p.one(p.fields(raw), 1) for raw in group.get(2, []))
        if not group_id or not own or own not in members or not any(member and member != own for member in members):
            raise NotSent('设备尚未关联到有效设备组')
        raw_message = p.one(group, 3, b'')
        message = None
        if raw_message:
            fields = p.fields(raw_message)
            kind = p.one(fields, 2)
            data = p.one(fields, 6, b'') if kind == 1 else b''
            if len(data) > MAX_TEXT_BYTES:
                data = b''
            message = ClipboardMessage(p.one(fields, 1), p.one(fields, 7), p.one(fields, 4), kind,
                                       data.decode('utf-8'), p.one(fields, 9, b'').decode('utf-8'))
        return GroupSnapshot(group_id, own, members, message, client.timestamp())

    def fetch(self):
        with self.session() as client:
            return self.group(client, True)

    def send(self, snapshot, text, trace):
        if not text or '\0' in text or len(text.encode()) > MAX_TEXT_BYTES:
            raise NotSent('文本必须为 1 到 256 KiB 的 UTF-8 内容')
        try:
            with self.session() as client:
                current = self.group(client, False)
                if (current.group, current.own) != (snapshot.group, snapshot.own):
                    raise NotSent('设备组已变化，本次未发送')
                message = p.number(2, 1) + p.blob(6, text) + p.blob(9, trace)
                request = p.number(1, current.own) + p.number(2, 1) + p.blob(3, message) + p.number(4, current.group)
                try:
                    response = p.fields(client.api(36, request, persist_errors=False))
                    if p.one(response, 1) != 0 or p.one(response, 2) <= 0:
                        raise SendUnknown('服务器没有确认发送版本')
                    return p.one(response, 2)
                except Exception:
                    raise SendUnknown('发送结果不明，等待核对远端状态') from None
        except (NotSent, SendUnknown):
            raise
        except Exception:
            raise NotSent('发送前连接或身份检查失败') from None
