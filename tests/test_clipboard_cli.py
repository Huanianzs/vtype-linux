"""验证用户命令的默认关闭、显式启用和可逆关闭；不操作真实 systemd。"""
import contextlib
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'cloud'))
import 官方同步探针 as p
import 配置与配对 as setup
from 运行支持 import write_doc
from test_clipboard_sync import MemoryClipboard, MemoryGroup


class ClipboardCliTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.original_state = p.STATE
        self.env = patch.dict(os.environ, {'XDG_CONFIG_HOME': str(self.root / 'config')})
        self.env.start()
        self.state = self.root / 'account'
        self.args = ['--state', str(self.state)]

    def tearDown(self):
        p.STATE = self.original_state
        self.env.stop()
        self.temp.cleanup()

    def test_status_and_disabled_run_do_not_create_identity_or_touch_clipboard(self):
        with contextlib.redirect_stdout(io.StringIO()) as output:
            setup.main(self.args + ['clipboard', 'status'])
        self.assertFalse(json.loads(output.getvalue())['enabled'])
        self.assertFalse(self.state.exists())
        with patch('系统剪贴板.DesktopClipboard') as desktop:
            self.assertEqual(setup.main(self.args + ['clipboard', 'run']), 0)
            desktop.assert_not_called()

    def test_clipboard_help_shows_its_own_commands_without_creating_identity(self):
        with contextlib.redirect_stdout(io.StringIO()) as output:
            with self.assertRaises(SystemExit) as caught:
                setup.main(self.args + ['clipboard', '--help'])
        self.assertEqual(caught.exception.code, 0)
        self.assertIn('enable', output.getvalue())
        self.assertIn('disable', output.getvalue())
        self.assertFalse(self.state.exists())

    def test_explicit_enable_creates_private_service_and_disable_keeps_identity(self):
        self.state.mkdir()
        identity = self.state / 'identity.json'
        identity.write_text('{"synthetic":true}')
        with patch('系统剪贴板.DesktopClipboard'), patch('运行支持.wxc_binary', return_value='/synthetic/wxc'), \
                patch('剪贴板同步.subprocess.run') as run, contextlib.redirect_stdout(io.StringIO()) as output:
            setup.main(self.args + ['clipboard', 'enable', '--backend', 'x11'])
            config = self.root / 'config/wetype-ime/clipboard.json'
            self.assertTrue(json.loads(config.read_text())['enabled'])
            self.assertEqual(config.stat().st_mode & 0o777, 0o600)
            unit = self.root / 'config/systemd/user/wetype-clipboard.service'
            self.assertIn('clipboard run', unit.read_text())
            self.assertIn('WantedBy=graphical-session.target default.target', unit.read_text())
            self.assertIn('微信输入法服务器', output.getvalue())
            self.assertTrue(any('enable' in call.args[0] for call in run.call_args_list))
            setup.main(self.args + ['clipboard', 'disable'])
        self.assertFalse(json.loads(config.read_text())['enabled'])
        self.assertEqual(identity.read_text(), '{"synthetic":true}')

    def test_enable_without_pairing_never_creates_config_or_starts_service(self):
        with patch('剪贴板同步.subprocess.run') as run:
            with self.assertRaises(RuntimeError):
                setup.main(self.args + ['clipboard', 'enable'])
            run.assert_not_called()
        self.assertFalse((self.root / 'config/wetype-ime/clipboard.json').exists())

    def test_enable_does_not_overwrite_unrelated_systemd_unit(self):
        self.state.mkdir()
        (self.state / 'identity.json').write_text('{}')
        unit = self.root / 'config/systemd/user/wetype-clipboard.service'
        unit.parent.mkdir(parents=True)
        unit.write_text('[Service]\nExecStart=/synthetic/other')
        with patch('系统剪贴板.DesktopClipboard'), patch('运行支持.wxc_binary', return_value='/synthetic/wxc'):
            with self.assertRaises(RuntimeError):
                setup.main(self.args + ['clipboard', 'enable'])
        self.assertIn('/synthetic/other', unit.read_text())

    def test_running_command_stops_when_disabled_and_does_not_log_text(self):
        self.state.mkdir()
        (self.state / 'identity.json').write_text('{}')
        config = self.root / 'config/wetype-ime/clipboard.json'
        write_doc(config, {'enabled': True, 'state_dir': str(self.state), 'backend': 'x11'})
        desktop = MemoryClipboard('私有文本')
        group = MemoryGroup()
        original = desktop.read
        def read_and_stop():
            write_doc(config, {'enabled': False, 'state_dir': str(self.state), 'backend': 'x11'})
            return original()
        desktop.read = read_and_stop
        with patch('系统剪贴板.DesktopClipboard', return_value=desktop), \
                patch('剪贴板协议.OfficialClipboard', return_value=group), patch('运行支持.refresh_client'):
            self.assertEqual(setup.main(self.args + ['clipboard', 'run']), 0)
        self.assertEqual(group.sent, [])
        self.assertNotIn('私有文本', (self.state / 'clipboard-status.json').read_text())


if __name__ == '__main__':
    unittest.main()
