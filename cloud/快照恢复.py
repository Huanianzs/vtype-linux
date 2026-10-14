"""受限的单成员快照重建控制请求；不发送词条、不修改本地词库。"""
import fcntl
from contextlib import contextmanager
import json
from pathlib import Path
import time
import 官方同步探针 as p


@contextmanager
def identity_lock(state):
    deadline = time.monotonic() + 20
    with (Path(state) / 'identity.lock').open('a+') as lock:
        while True:
            try:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except BlockingIOError:
                if time.monotonic() >= deadline:
                    raise TimeoutError('身份锁忙')
                time.sleep(.2)
        yield lock


def encode(message):
    return b''.join(p.number(k, v) if isinstance(v, int) else p.blob(k, v)
                    for k, values in message.items() for v in values)


def group_and_metadata(api, uin):
    raw = api(34, p.number(1, uin) + p.number(2, 1) + p.number(3, 13) + p.number(5, 0))
    response = p.fields(raw)
    if p.one(response, 2, -1) != 0:
        raise ValueError('设备组查询失败')
    group = p.fields(p.one(response, 1, b''))
    gid = p.one(group, 1)
    members = {p.one(p.fields(row), 1) for row in group.get(2, [])}
    if not isinstance(gid, int) or gid <= 0 or uin not in members:
        raise ValueError('关联身份不属于有效设备组')
    metadata_raw = api(44, p.number(1, uin) + p.number(2, gid))
    metadata = p.fields(metadata_raw)
    if p.one(metadata, 1, -1) != 0:
        raise ValueError('快照查询失败')
    return gid, members, metadata


def make_refresh_request(uin, peer, gid, members, metadata, timestamp_ms):
    if not isinstance(peer, int) or not 0 < peer < 2**64 - 1 or peer == uin or peer not in members:
        raise ValueError('来源必须是同组的单个其他成员')
    if not isinstance(timestamp_ms, int) or timestamp_ms <= 0:
        raise ValueError('请求时间无效')
    version = p.one(metadata, 3)
    if not isinstance(version, int) or version <= 0:
        raise ValueError('加密密钥版本无效')
    original = None
    for raw in metadata.get(2, []):
        record = p.fields(raw)
        if p.one(record, 1) == uin:
            original = p.one(record, 2, b'')
            break
    if original is None:
        # 44未提供本身份详情时，使用默认禁止整库上传的Linux身份最小状态。
        # 缺少条目不能证明服务器没有本设备状态，不虚构已上传文件或增量进度。
        detail = {1: [1], 6: [version]}
    else:
        detail = p.fields(original)
        # 不合并/覆盖另一项尚未完成的远端请求。
        pending = detail.get(9, [])
        if p.one(detail, 10) and any(value not in (peer, 2**64 - 1) for value in pending):
            raise ValueError('已有其他成员的重建请求')
    detail[9] = [peer]
    detail[10] = [timestamp_ms]
    record = p.number(1, uin) + p.blob(2, encode(detail))
    return p.blob(1, record) + p.number(2, gid), original


def validate_control(body, uin, peer, gid, now_ms):
    outer = p.fields(body)
    if set(outer) != {1, 2} or len(outer[1]) != 1 or outer[2] != [gid]:
        raise ValueError('控制请求的组或结构无效')
    record = p.fields(outer[1][0])
    if set(record) != {1, 2} or record[1] != [uin] or len(record[2]) != 1:
        raise ValueError('控制请求身份无效')
    detail = p.fields(record[2][0])
    if detail.get(9) != [peer] or not 0 < peer < 2**64 - 1 or peer == uin:
        raise ValueError('拒绝批量或其他成员请求')
    timestamp = p.one(detail, 10)
    if not isinstance(timestamp, int) or abs(timestamp - now_ms) > 120000:
        raise ValueError('控制请求时间过期')


class Client:
    def __init__(self, state):
        self.state = Path(state).expanduser().resolve()
        p.STATE = self.state
        with identity_lock(self.state):
            self.uin = json.loads((self.state / 'identity.json').read_text())['uin']
        self.allowed_refresh = None
        self.allowed_cleanup = None
        self.server_offset = 0

    def now_ms(self):
        return int(time.time() * 1000) + self.server_offset

    def __call__(self, sub, body):
        if sub not in (34, 44, 60, 43):
            raise ValueError('拒绝未核对请求')
        if sub == 43:
            if self.allowed_cleanup is not None and body == self.allowed_cleanup:
                self.allowed_cleanup = None
            elif self.allowed_refresh is None:
                raise ValueError('未启用单成员重建操作')
            else:
                peer, gid = self.allowed_refresh
                validate_control(body, self.uin, peer, gid, self.now_ms())
                # 请求在网络发送前即消耗；响应不明时不能自动重复发送。
                self.allowed_refresh = None
        with identity_lock(self.state):
            identity = json.loads((self.state / 'identity.json').read_text())
            if identity['uin'] != self.uin:
                raise ValueError('身份已变化')
            client = p.Probe(identity)
            start = int(time.time() * 1000)
            stamp = p.one(p.fields(client.request('/timestamp', b'')), 1)
            self.server_offset = stamp - (start + int(time.time() * 1000)) // 2
            client.offset = self.server_offset
            return client.api(sub, body, persist_errors=False)
