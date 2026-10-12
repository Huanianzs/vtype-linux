"""在同步入口验证双向文本；只用合成数据，不需要账号或网络。"""
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'cloud'))
from 剪贴板同步 import Synchronizer
from 剪贴板协议 import ClipboardMessage, GroupSnapshot, SendUnknown, NotSent


class MemoryClipboard:
    def __init__(self, text='启动前已有文字'):
        self.text = text
        self.writes = []
        self.fail = False

    def read(self):
        return self.text

    def write(self, text, expected):
        if self.fail:
            raise OSError('synthetic failure')
        if self.text != expected:
            raise RuntimeError('clipboard changed')
        self.text = text
        self.writes.append(text)


class MemoryGroup:
    def __init__(self):
        self.snapshot = GroupSnapshot(20, 10, frozenset({10, 11}), None, 1000000)
        self.sent = []

    def fetch(self):
        return self.snapshot

    def send(self, snapshot, text, trace):
        self.sent.append((text, trace))
        return 6

    def receive(self, text='手机复制的文本', version=5, source=11, expires=2000, kind=1, trace='remote'):
        self.snapshot = GroupSnapshot(20, 10, frozenset({10, 11}),
                                      ClipboardMessage(version, source, expires, kind, text, trace), 1000000)


class ClipboardSyncTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.state = Path(self.temp.name) / 'clipboard-state.json'
        self.desktop = MemoryClipboard()
        self.group = MemoryGroup()
        self.sync = Synchronizer(self.desktop, self.group, self.state)

    def tearDown(self):
        self.temp.cleanup()

    def test_receive_text_without_uploading_existing_or_echoing_received_text(self):
        self.group.receive()
        self.sync.step()
        self.sync.step()
        self.assertEqual(self.desktop.text, '手机复制的文本')
        self.assertEqual(self.desktop.writes, ['手机复制的文本'])
        self.assertEqual(self.group.sent, [])
        self.assertEqual(self.sync.status()['received'], 1)

    def test_new_local_copy_sends_once_and_survives_restart_without_resending(self):
        self.sync.step()
        self.desktop.text = 'Linux 新复制\n末行\n'
        self.sync.step(poll=False)
        self.assertEqual(self.group.sent, [])
        self.sync.step()
        self.sync.step()
        resumed = Synchronizer(self.desktop, self.group, self.state)
        resumed.step()
        self.assertEqual([row[0] for row in self.group.sent], ['Linux 新复制\n末行\n'])
        self.assertEqual(self.sync.status()['sent'], 1)
        self.assertEqual(self.state.stat().st_mode & 0o777, 0o600)
        self.assertNotIn('Linux 新复制', self.state.read_text())

    def test_unknown_send_is_not_retried_and_old_remote_cannot_overwrite_it(self):
        self.group.receive()
        self.sync.step()
        self.desktop.text = '结果不明的本地文本'
        original = self.group.send
        def unknown(*args):
            original(*args)
            raise SendUnknown()
        self.group.send = unknown
        with self.assertRaises(SendUnknown):
            self.sync.step()
        self.sync.step()
        resumed = Synchronizer(self.desktop, self.group, self.state)
        resumed.step()
        self.assertEqual(len(self.group.sent), 1)
        self.assertEqual(self.desktop.text, '结果不明的本地文本')
        self.group.receive('结果不明的本地文本', version=6, source=10, trace=self.group.sent[0][1])
        resumed.step()
        self.assertFalse(resumed.status()['send_unknown'])
        self.assertNotIn('结果不明的本地文本', self.state.read_text())

    def test_receive_rejects_expired_foreign_self_non_text_and_zero_source(self):
        for options in ({'expires': 1000}, {'source': 12}, {'source': 10}, {'kind': 2},
                        {'text': ''}, {'text': '中' * 90000}, {'source': 0}):
            with self.subTest(options=options.keys()):
                self.group.receive(**options)
                if options.get('source') == 0:
                    self.group.snapshot = GroupSnapshot(20, 10, frozenset({0, 10, 11}), self.group.snapshot.message, 1000000)
                self.sync.step()
                self.assertEqual(self.desktop.text, '启动前已有文字')
        self.assertEqual(self.group.sent, [])

    def test_failed_desktop_write_retains_cursor_and_retries_after_recovery(self):
        self.group.receive()
        self.desktop.fail = True
        with self.assertRaises(OSError):
            self.sync.step()
        self.assertFalse(self.state.exists())
        self.desktop.fail = False
        self.sync.step()
        resumed = Synchronizer(self.desktop, self.group, self.state)
        resumed.step()
        self.assertEqual(self.desktop.writes, ['手机复制的文本'])

    def test_preflight_failure_retries_new_copy_without_replaying_old_contents(self):
        self.sync.step()
        self.desktop.text = '待发送'
        original = self.group.send
        self.group.send = lambda *args: (_ for _ in ()).throw(NotSent())
        with self.assertRaises(NotSent):
            self.sync.step()
        self.assertEqual(self.group.sent, [])
        self.group.send = original
        self.sync.step()
        self.assertEqual([row[0] for row in self.group.sent], ['待发送'])

    def test_cursor_save_failure_does_not_echo_or_consume_failed_receipt(self):
        self.group.receive()
        self.state.parent.chmod(0o500)
        try:
            with self.assertRaises(OSError):
                self.sync.step()
        finally:
            self.state.parent.chmod(0o700)
        self.sync.step()
        self.assertEqual(self.group.sent, [])
        self.assertEqual(self.sync.status()['received'], 1)
        resumed = Synchronizer(self.desktop, self.group, self.state)
        resumed.step()
        self.assertEqual(len(self.desktop.writes), 2)

    def test_group_change_discards_queued_copy_instead_of_sending_to_new_group(self):
        self.sync.step()
        self.desktop.text = '旧组的待发送文字'
        self.sync.step(poll=False)
        self.group.snapshot = GroupSnapshot(21, 10, frozenset({10, 12}), None, 1000000)
        self.sync.step()
        self.assertEqual(self.group.sent, [])
        self.desktop.text = '新组复制的文字'
        self.sync.step()
        self.assertEqual([row[0] for row in self.group.sent], ['新组复制的文字'])

    def test_write_that_changes_clipboard_but_fails_confirmation_is_never_echoed(self):
        self.sync.step()
        self.group.receive()
        original = self.desktop.write
        def write_without_confirmation(*args, **kwargs):
            original(*args, **kwargs)
            raise TimeoutError('synthetic confirmation failure')
        self.desktop.write = write_without_confirmation
        with self.assertRaises(TimeoutError):
            self.sync.step()
        self.desktop.write = original
        self.sync.step()
        self.assertEqual(self.group.sent, [])
        self.assertEqual(self.sync.status()['received'], 1)


if __name__ == '__main__':
    unittest.main()
