"""验证云候选有效期配置的默认值和边界，不启动引擎或访问网络。"""
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'cloud'))
from 实时云桥接 import cloud_timeout_ms


class CloudTimeout(unittest.TestCase):
    def test_default(self):
        self.assertEqual(cloud_timeout_ms({}), 1500)

    def test_valid_limits(self):
        for value in (200, 1500, 5000):
            self.assertEqual(cloud_timeout_ms({'cloud_timeout_ms': value}), value)

    def test_invalid_configuration(self):
        for value in (None, True, False, '1500', 1500.0, 199, 5001, -1):
            with self.subTest(value=value), self.assertRaises(ValueError):
                cloud_timeout_ms({'cloud_timeout_ms': value})


if __name__ == '__main__':
    unittest.main()
