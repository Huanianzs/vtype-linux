"""真实引擎验证行内编辑、Readline、配置回退及内嵌预编辑光标。"""
import dbus
from dbus_test_client import Client, controller, pump

URI = 'fcitx://config/addon/wetype'
c = Client('cursor-edit', capabilities=1 | 2 | 16 | (1 << 39))
c.focus()

def config(**values):
    raw, _ = controller.GetConfig(URI)
    for k, v in values.items():
        raw[k] = dbus.String(str(v), variant_level=1)
    controller.SetConfig(URI, dbus.Dictionary(raw, signature='sv', variant_level=1))
    pump()

def fresh(text='nihao'):
    c.press('esc')
    c.commits.clear()
    c.type(text)

def raw(expected):
    c.press('enter')
    assert c.commits == [expected], (expected, c.commits)

# 每个编辑命令都检查精确拼音，避免“有上屏”掩盖错误编辑。
for name, actions, expected in [
    ('left-insert', [('left', 0)] * 4 + [('u', 0)], 'shurufa'),
    ('home-insert', [(0xff50, 0), ('a', 0)], 'anihao'),
    ('end-insert', [(0xff50, 0), (0xff57, 0), ('a', 0)], 'nihaoa'),
    ('delete', [('left', 0)] * 3 + [(0xffff, 0)], 'niao'),
    ('backspace', [('left', 0)] * 3 + [('backspace', 0)], 'nhao'),
    ('ctrl-a-d', [('a', 4), ('d', 4)], 'ihao'),
    ('ctrl-e-h', [('a', 4), ('e', 4), ('h', 4)], 'niha'),
    ('ctrl-b-f', [('b', 4), ('b', 4), ('f', 4), ('d', 4)], 'niha'),
    ('ctrl-k', [('b', 4)] * 3 + [('k', 4)], 'ni'),
    ('ctrl-u', [('b', 4)] * 3 + [('u', 4)], 'hao'),
]:
    fresh('shrufa' if name == 'left-insert' else 'nihao')
    for key, state in actions:
        assert c.press(key, states=state), name
    raw(expected)
    print('PASS 精确编辑', name)

config(ShowPinyinInInput=True)
fresh()
c.press('left')
assert int(c.preedits[-1][1]) == 5, c.preedits[-1]
c.press('left')
assert int(c.preedits[-1][1]) == 4, c.preedits[-1]
c.press('a')
pump(.5)
assert ''.join(str(p[0]) for p in c.preedits[-1][0]) == 'ni ha ao', c.preedits[-1]
raw('nihaao')
print('PASS 内嵌预编辑精确编辑光标')

config(ReadlineKeyBindings=False, ArrowKeysMoveCursor=False)
fresh()
assert not c.press('a', states=4)
c.press('right')
raw('nihao')
config(ReadlineKeyBindings=True, ArrowKeysMoveCursor=True, ShowPinyinInInput=False)
print('PASS 关闭新配置保留快捷键透传与原方向键选词')
