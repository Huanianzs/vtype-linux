"""无真实账户/网络：核对状态隔离、配对防覆盖和配置可逆性。"""
import contextlib
import io
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'cloud'))
import 官方同步探针 as p
import 配置与配对 as setup
from 运行支持 import atomic


class CloudSetupTest(unittest.TestCase):
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
        self.env.stop(); self.temp.cleanup()

    def test_status_does_not_create_identity(self):
        with contextlib.redirect_stdout(io.StringIO()) as out:
            setup.main(self.args + ['status'])
        self.assertFalse(json.loads(out.getvalue())['paired'])
        self.assertFalse(self.state.exists())

    def test_pair_never_replaces_existing_identity(self):
        self.state.mkdir(); identity = self.state / 'identity.json'
        identity.write_text('{"synthetic":true}')
        with patch.object(setup.subprocess, 'run') as run:
            with self.assertRaises(RuntimeError):
                setup.main(self.args + ['pair', '--code', '123456'])
            run.assert_not_called()
        self.assertEqual(identity.read_text(), '{"synthetic":true}')

    def test_bad_pairing_code_sends_nothing(self):
        with patch.object(setup.subprocess, 'run') as run:
            with self.assertRaises(ValueError):
                setup.main(self.args + ['pair', '--code', 'bad'])
            run.assert_not_called()

    def test_disable_retains_account_and_other_config(self):
        self.state.mkdir(); identity = self.state / 'identity.json'; identity.write_text('{}')
        config = self.root / 'config/wetype-ime/cloud.json'
        atomic(config, b'{"enabled":true,"native_sync":true}')
        with patch.object(setup.subprocess, 'run'), contextlib.redirect_stdout(io.StringIO()):
            setup.main(self.args + ['disable'])
        self.assertFalse(json.loads(config.read_text())['enabled'])
        self.assertTrue(json.loads(config.read_text())['native_sync'])
        self.assertTrue(identity.exists())
        self.assertEqual(config.stat().st_mode & 0o777, 0o600)

    def test_export_keeps_official_key_and_empty_fallback(self):
        from 导出官方常用语 import entries
        rows = p.blob(2, p.blob(2, 'mail') + p.blob(3, 'synthetic@example.invalid'))
        rows += p.blob(2, p.blob(3, '测试常用语'))
        self.assertEqual(entries(rows), [('mail', 'synthetic@example.invalid'), ('', '测试常用语')])


if __name__ == '__main__':
    unittest.main()
