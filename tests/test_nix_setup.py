#!/usr/bin/env python3
"""初始化失败、旧插件迁移和数据保留，不下载 APK、不访问桌面会话。"""
import importlib.util
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('nix_setup', Path(__file__).resolve().parents[1] / 'nix/setup.py')
setup = importlib.util.module_from_spec(spec)
spec.loader.exec_module(setup)


class SetupTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.package = self.root / 'package'
        self.engine = self.root / 'engine'
        self.data = self.root / 'data'
        for name in ('wetype-harness', 'libandroid.so', 'libwetype-cloud.so',
                     'cloud_proxy.py', 'qemu-aarch64-static', 'sysroot/system/bin/linker64'):
            target = self.package / 'libexec' / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(b'packaged runtime')
        (self.package / 'share/vtype-linux/cloud').mkdir(parents=True)
        (self.package / 'share/vtype-linux/wetype-cloud.py').touch()
        self.addCleanup(patch.stopall)
        patch.object(setup, 'active_engine', return_value=False).start()
        self.run = patch.object(setup.subprocess, 'run', side_effect=self.extract).start()

    def extract(self, command, **kwargs):
        if Path(command[1]).name == 'fetch_apk.py':
            inputs = Path(kwargs['env']['WETYPE_APK_ROOT'])
            libs = inputs / 'lib/arm64-v8a'
            libs.mkdir(parents=True)
            for name in setup.ENGINE_LIBS:
                (libs / name).write_bytes(b'fresh APK library')
            dicts = inputs / 'assets/config/beta'
            dicts.mkdir(parents=True)
            (dicts / 'index.json').write_text('fresh index')
            (dicts / 'main.dict').write_text('base dictionary')
        else:
            target = Path(command[2])
            target.write_bytes(target.read_bytes() + b' patched')
        return subprocess.CompletedProcess(command, 0)

    def prepare(self, **kwargs):
        setup.prepare(self.package, self.engine, data_home=self.data, **kwargs)

    def test_fresh_runtime_has_engine_and_cloud_dependencies(self):
        self.prepare()
        self.assertTrue((self.engine / 'sysroot/system/bin/linker64').is_file())
        self.assertTrue((self.engine / 'lib/libandroid.so').is_file())
        self.assertEqual((self.engine / 'lib/libwxhld.so').read_bytes(), b'fresh APK library patched patched')
        self.assertTrue((self.engine / 'cloud_proxy.py').is_file())
        self.assertTrue((self.engine / 'libwetype-cloud.so').is_file())
        self.assertEqual((self.engine / 'dicts/main.dict').read_text(), 'base dictionary')
        self.assertFalse((self.data / 'wetype-ime').exists())

    def test_upgrade_preserves_existing_dictionaries_and_unknown_files(self):
        (self.engine / 'dicts').mkdir(parents=True)
        (self.engine / 'dicts/main.dict').write_text('updated dictionary')
        (self.engine / 'notes').write_text('keep')
        (self.engine / 'lib').mkdir()
        (self.engine / 'lib/old.so').touch()
        self.prepare()
        self.assertEqual((self.engine / 'dicts/main.dict').read_text(), 'updated dictionary')
        self.assertEqual((self.engine / 'notes').read_text(), 'keep')
        self.assertFalse((self.engine / 'lib/old.so').exists())
        backup, = self.root.glob('engine-backup.*')
        self.assertTrue((backup / 'lib/old.so').exists())

    def test_failed_apk_preparation_leaves_old_runtime_and_registration(self):
        self.engine.mkdir()
        (self.engine / 'sentinel').write_text('old runtime')
        registration = setup.registrations(self.data)[0]
        registration.parent.mkdir(parents=True)
        registration.write_text('old registration')
        self.run.side_effect = subprocess.CalledProcessError(1, 'fetch_apk')
        with self.assertRaises(subprocess.CalledProcessError):
            self.prepare(migrate=True)
        self.assertEqual((self.engine / 'sentinel').read_text(), 'old runtime')
        self.assertEqual(registration.read_text(), 'old registration')
        self.assertFalse(list(self.root.glob('engine-backup.*')))

    def test_old_registration_requires_explicit_migration_and_is_backed_up(self):
        for registration in setup.registrations(self.data):
            registration.parent.mkdir(parents=True, exist_ok=True)
            registration.write_text(registration.name)
        with self.assertRaisesRegex(RuntimeError, '--migrate-fcitx'):
            self.prepare()
        self.run.assert_not_called()
        self.prepare(migrate=True)
        self.assertFalse(any(path.exists() for path in setup.registrations(self.data)))
        backup, = (self.data / 'fcitx5').glob('wetype-backup.*')
        self.assertEqual((backup / 'addon-wetype.conf').read_text(), 'wetype.conf')
        self.assertEqual((backup / 'inputmethod-wetype-im.conf').read_text(), 'wetype-im.conf')

    def test_running_engine_refuses_replacement(self):
        with patch.object(setup, 'active_engine', return_value=True):
            with self.assertRaisesRegex(RuntimeError, '仍在运行'):
                self.prepare()
        self.run.assert_not_called()

    def test_engine_starting_during_preparation_keeps_old_runtime(self):
        self.engine.mkdir()
        (self.engine / 'sentinel').write_text('old runtime')
        with patch.object(setup, 'active_engine', side_effect=[False, True]):
            with self.assertRaisesRegex(RuntimeError, '准备期间'):
                self.prepare()
        self.assertEqual((self.engine / 'sentinel').read_text(), 'old runtime')

    def test_registration_failure_rolls_back_runtime_and_prior_registration(self):
        self.engine.mkdir()
        (self.engine / 'sentinel').write_text('old runtime')
        registrations = setup.registrations(self.data)
        for registration in registrations:
            registration.parent.mkdir(parents=True, exist_ok=True)
            registration.write_text('old registration')
        original_rename = Path.rename

        def rename(path, target):
            if path == registrations[1]:
                raise PermissionError('synthetic migration failure')
            return original_rename(path, target)

        with patch.object(Path, 'rename', rename):
            with self.assertRaises(PermissionError):
                self.prepare(migrate=True)
        self.assertEqual((self.engine / 'sentinel').read_text(), 'old runtime')
        self.assertTrue(all(path.read_text() == 'old registration' for path in registrations))

    def test_symlink_engine_directory_is_not_replaced(self):
        real = self.root / 'real'
        real.mkdir()
        self.engine.symlink_to(real)
        with self.assertRaisesRegex(RuntimeError, '符号链接'):
            self.prepare()
        self.assertTrue(self.engine.is_symlink())


if __name__ == '__main__':
    unittest.main()
