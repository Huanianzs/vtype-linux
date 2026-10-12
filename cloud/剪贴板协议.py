"""官方设备组的纯文本剪贴板传输，协议依据见剪贴板文档。"""
from dataclasses import dataclass
import fcntl
import json
import time
import urllib.parse
import urllib.request
from pathlib import Path
import 官方同步探针 as p

# 发送只走内联文本；更长的文本官方改用 COS 链接，Linux 只接收不上传。
MAX_TEXT_BYTES = 256 * 1024
MAX_RECEIVE_TEXT_BYTES = 1024 * 1024
TEXT_INLINE = 1
TEXT_COS = 2


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
    url: str | None = None


@dataclass(frozen=True)
class GroupSnapshot:
    group: int
    own: int
    members: frozenset
    message: ClipboardMessage | None
    now_ms: int


def decode_text(data):
    try:
        text = data.decode('utf-8')
    except UnicodeError:
        return ''
    return text if '\0' not in text else ''


def cos_url(value):
    """只接受官方 COS 的 HTTPS 地址，与 wx-ime-sdk 的校验一致。"""
    url = urllib.parse.urlsplit(value)
    if (url.scheme != 'https' or url.username or url.password or url.port not in (None, 443)
            or not (url.hostname or '').endswith('.myqcloud.com') or url.fragment):
        raise ValueError('剪贴板文本链接不是官方 COS 地址')
    return value


def download_text(url, limit=MAX_RECEIVE_TEXT_BYTES, opener=urllib.request.urlopen):
    with opener(urllib.request.Request(cos_url(url)), timeout=10) as response:
        if response.status != 200:
            raise ValueError('剪贴板文本下载失败')
        data = response.read(limit + 1)
    if not data or len(data) > limit:
        raise ValueError('剪贴板文本为空或超过上限')
    return decode_text(data)


class OfficialClipboard:
    """只在读取身份时持锁，网络请求不占锁，避免挡住打字时的云候选；发送前重新验证组号与成员。"""
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
            data = p.one(fields, 6, b'') if kind in (TEXT_INLINE, TEXT_COS) else b''
            text, url = '', None
            if kind == TEXT_INLINE and len(data) <= MAX_RECEIVE_TEXT_BYTES:
                text = decode_text(data)
            elif kind == TEXT_COS and len(data) <= 4096:
                url = decode_text(data) or None
            # 远端内容不可信：无法解码的消息按非文本处理，不让异常卡住两个方向。
            message = ClipboardMessage(p.one(fields, 1), p.one(fields, 7), p.one(fields, 4), kind,
                                       text, decode_text(p.one(fields, 9, b'')), url)
        return GroupSnapshot(group_id, own, members, message, client.timestamp())

    def text(self, message):
        """返回消息的文本；COS 长文本此时才下载，失败时抛出异常并保留游标。"""
        if message.kind == TEXT_COS:
            return download_text(message.url) if message.url else ''
        return message.text

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
