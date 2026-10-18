"""检查真实 CMake 配置保留安装阶段才生成的 Python 启动器。"""
import json
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]


@unittest.skipUnless(shutil.which('cmake'), '需要 CMake 和插件构建依赖')
class PythonLauncherBuildTest(unittest.TestCase):
    def configure(self, directory, launcher=None):
        build = directory / 'build'
        command = ['cmake', '-S', str(ROOT / 'fcitx5-wetype'), '-B', str(build),
                   '-DBUILD_TESTING=OFF', '-DCMAKE_EXPORT_COMPILE_COMMANDS=ON']
        if launcher is not None:
            command.append('-DWETYPE_PYTHON_EXECUTABLE:FILEPATH=' + str(launcher))
        result = subprocess.run(command, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        cache = (build / 'CMakeCache.txt').read_text()
        configured = re.search(r'^WETYPE_PYTHON_EXECUTABLE:[^=]+=(.+)$', cache, re.M).group(1)
        entry = next(row for row in json.loads((build / 'compile_commands.json').read_text())
                     if row['file'].endswith('/src/wetype.cpp'))
        self.assertIn(configured, entry['command'])
        return configured

    def test_preserves_launcher_created_only_at_install_time(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            launcher = root / 'future-output/libexec/wetype-python'
            self.assertFalse(launcher.exists())
            self.assertEqual(self.configure(root, launcher), str(launcher))

    def test_default_python_is_found_when_not_explicitly_configured(self):
        with tempfile.TemporaryDirectory() as directory:
            configured = self.configure(Path(directory))
            self.assertTrue(Path(configured).is_file(), configured)


if __name__ == '__main__':
    unittest.main()
