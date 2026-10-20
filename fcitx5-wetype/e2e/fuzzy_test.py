#!/usr/bin/env python3
"""在私有 D-Bus 会话验证模糊音设置与候选召回。"""

import sys
import dbus

from dbus_test_client import Client, controller, pump

URI = 'fcitx://config/addon/wetype'
results = []

def check(name, ok, detail=''):
    results.append(bool(ok))
    print(('PASS ' if ok else 'FAIL ') + name + (' ' + detail if detail else ''), flush=True)

client = Client('wetype-fuzzy-test')
client.focus()

value, schema = controller.GetConfig(URI)
fuzzy_keys = [
    "Fuzzy_Z_ZH", "Fuzzy_C_CH", "Fuzzy_S_SH", "Fuzzy_N_L",
    "Fuzzy_H_F", "Fuzzy_R_L", "Fuzzy_G_K", "Fuzzy_AN_ANG",
    "Fuzzy_EN_ENG", "Fuzzy_IN_ING", "Fuzzy_IAN_IANG",
    "Fuzzy_UAN_UANG", "Fuzzy_ON_ONG", "Fuzzy_ENG_ONG",
    "Fuzzy_UN_ONG", "Fuzzy_UN_IONG", "Fuzzy_AN_AI",
    "Fuzzy_HUI_FEI", "Fuzzy_HUANG_WANG"
]

for k in fuzzy_keys:
    check(f'导出配置 {k}', k in value and str(value[k]) == 'False')

check('图形设置包含全部19组模糊音复选框', all(
    any(str(option[0]) == k and str(option[1]) == 'Boolean'
        for section in schema for option in section[1])
    for k in fuzzy_keys
))

# 默认输入 san，不应包含山
client.type('san')
cands = [t for _, t in client.candidates]
check('默认不开启模糊音时 san 不含山', not any('山' in t for t in cands), f'cands={cands}')
client.press('esc')

# 动态开启 Fuzzy_S_SH
value['Fuzzy_S_SH'] = dbus.String('True', variant_level=1)
controller.SetConfig(URI, dbus.Dictionary(value, signature='sv', variant_level=1))
pump(2.5)

actual, _ = controller.GetConfig(URI)
check('Fuzzy_S_SH 设置生效', str(actual['Fuzzy_S_SH']) == 'True')

# 开启后输入 san，应召回山
client.type('san')
cands = [t for _, t in client.candidates]
check('开启 s=sh 模糊音后 san 候选包含山', any('山' in t for t in cands), f'cands={cands}')
client.press('esc')

# 关闭 Fuzzy_S_SH，开启 Fuzzy_N_L
value['Fuzzy_S_SH'] = dbus.String('False', variant_level=1)
value['Fuzzy_N_L'] = dbus.String('True', variant_level=1)
controller.SetConfig(URI, dbus.Dictionary(value, signature='sv', variant_level=1))
pump(2.5)

# 输入 lan，应召回男
client.type('lan')
cands = [t for _, t in client.candidates]
check('开启 n=l 模糊音后 lan 候选包含男', any('男' in t for t in cands), f'cands={cands}')
client.press('esc')

# 恢复默认全关
value['Fuzzy_N_L'] = dbus.String('False', variant_level=1)
controller.SetConfig(URI, dbus.Dictionary(value, signature='sv', variant_level=1))
pump(2.5)

client.type('lan')
cands = [t for _, t in client.candidates]
check('恢复关闭后 lan 不含男', not any('男' in t for t in cands), f'cands={cands}')
client.press('esc')

print('SUMMARY fuzzy pinyin total=%d failed=%d' % (len(results), results.count(False)), flush=True)
sys.exit(0 if all(results) else 1)
