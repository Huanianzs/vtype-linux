"""核对固定引擎同步状态的成员偏移，保证补拉不覆盖已有进度与密钥。"""
import importlib.util
from pathlib import Path
import unittest

spec = importlib.util.spec_from_file_location('snapshot_copy', Path(__file__).resolve().parents[1] / 'scripts/pull-snapshot-copy.py')
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)
p = m.p


def state(count=0, key=b'', detail=b''):
    header = bytearray(192)
    header[:8] = (1).to_bytes(8, 'little')
    header[8:24] = bytes(range(16))
    # 144是普通头字段，不是成员数；取非零值防止测试依赖它总是零。
    header[144:152] = (37).to_bytes(8, 'little')
    header[184:192] = count.to_bytes(8, 'little')
    return bytes(header) + bytes(range(64)) * count + len(key).to_bytes(8, 'little') + key + len(detail).to_bytes(8, 'little') + detail


class Bootstrap(unittest.TestCase):
    def test_initial_state(self):
        value = state()
        result = m.mark_full_pull_value(value, 3003)
        self.assertEqual(result[:208], value[:200] + len(p.number(1, 1) + p.number(9, 3003)).to_bytes(8, 'little'))
        self.assertEqual(p.fields(result[208:]), {1: [1], 9: [3003]})

    def test_existing_members_key_and_local_fields_preserved(self):
        detail = p.number(1, 1) + p.number(6, 7) + p.number(9, 1111) + p.blob(8, b'existing-path')
        value = state(10, b'K' * 16, detail)
        result = m.mark_full_pull_value(value, 3003)
        end = 192 + 10 * 64 + 8 + 16
        self.assertEqual(result[:48], value[:48])
        self.assertEqual(result[144:end], value[144:end])
        actual = p.fields(result[end + 8:])
        self.assertEqual(actual[9], [3003])
        self.assertEqual(actual[6], [7])
        self.assertEqual(actual[8], [b'existing-path'])

    def test_truncated_or_unknown_state_refused(self):
        for value in [state()[:-1], state(10)[:-65], bytes(208), state(key=b'bad')]:
            with self.assertRaises(AssertionError):
                m.mark_full_pull_value(value, 3003)

    def test_invalid_peer_refused(self):
        for peer in [0, -1, 2**64, '3003']:
            with self.assertRaises(AssertionError):
                m.mark_full_pull_value(state(), peer)


if __name__ == '__main__':
    unittest.main()
