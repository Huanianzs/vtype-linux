"""工具失败不是空剪贴板，使用合成命令验证失败恢复和读取上限。"""
import os
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'cloud'))
from 系统剪贴板 import DesktopClipboard
from 剪贴板同步 import Synchronizer
from test_clipboard_sync import MemoryGroup


class DesktopClipboardTest(unittest.TestCase):
    def test_empty_wayland_selection_is_a_valid_baseline(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for name in ('wl-paste', 'wl-copy'):
                script = root / name
                script.write_text(f'#!{sys.executable}\nimport sys\nprint("Nothing is copied",file=sys.stderr);sys.exit(1)\n')
                script.chmod(0o700)
            desktop = DesktopClipboard('wayland', dict(os.environ, PATH=str(root), WAYLAND_DISPLAY='synthetic'))
            self.assertIsNone(desktop.read())

    def test_failed_first_tool_read_does_not_upload_preexisting_text_after_recovery(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            script = root / 'xclip'
            script.write_text(f'#!{sys.executable}\nimport os,sys\n'
                              'if os.path.exists(os.environ["SYNTHETIC_FAILURE"]):\n'
                              '    print("synthetic read failure",file=sys.stderr);sys.exit(1)\n'
                              'print("UTF8_STRING") if "TARGETS" in sys.argv else sys.stdout.write("preexisting")\n')
            script.chmod(0o700)
            failure = root / 'failure'
            failure.touch()
            env = dict(os.environ, PATH=str(root), DISPLAY=':synthetic', SYNTHETIC_FAILURE=str(failure))
            desktop = DesktopClipboard('x11', env)
            group = MemoryGroup()
            sync = Synchronizer(desktop, group, root / 'cursor.json')
            with self.assertRaises(RuntimeError):
                sync.step()
            failure.unlink()
            sync.step()
            self.assertEqual(group.sent, [])


if __name__ == '__main__':
    unittest.main()
