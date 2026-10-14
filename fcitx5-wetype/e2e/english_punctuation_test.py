#!/usr/bin/env python3
"""在私有 D-Bus 会话验证英文标点设置、中文组词、快捷键及配置持久化。"""
import os
from pathlib import Path
import string
import sys

import dbus

from dbus_test_client import Client, controller, paused_engine, pump

URI = 'fcitx://config/addon/wetype'
KEY = 'AlwaysEnglishPunctuation'
results = []


def check(name, ok, detail=''):
    results.append(bool(ok))
    print(('PASS ' if ok else 'FAIL ') + name + (' ' + detail if detail else ''), flush=True)


def configure(enabled):
    value, _ = controller.GetConfig(URI)
    value[KEY] = dbus.String('True' if enabled else 'False', variant_level=1)
    controller.SetConfig(URI, dbus.Dictionary(value, signature='sv', variant_level=1))
    pump()
    actual, _ = controller.GetConfig(URI)
    check('设置立即生效', str(actual[KEY]) == ('True' if enabled else 'False'))


client = Client('wetype-english-punctuation')
client.focus()
value, schema = controller.GetConfig(URI)
check('默认保留中文标点', str(value[KEY]) == 'False')
check('图形设置包含复选框', any(str(option[0]) == KEY and str(option[1]) == 'Boolean'
                           and str(option[2]) == '始终使用英文标点'
                           for section in schema for option in section[1]))
client.type('nihao')
client.press(',')
check('默认组词仍输出中文逗号', client.commits == ['你好，'], str(client.commits))

configure(True)
for mark in string.punctuation:
    client.commits.clear()
    consumed = client.press(mark)
    # 未组词时，翻页键沿用直通路径，由应用接收原字符。
    check('独立英文标点 ' + mark, client.commits == [mark] if consumed else not client.commits)

for mark in ',.!?;:\'"()[]{}<>\\~^_$`/#%&*@|':
    client.commits.clear()
    client.type('nihao')
    client.press(mark)
    check('中文候选加英文标点 ' + mark, client.commits == ['你好' + mark], str(client.commits))

client.commits.clear()
client.type('nihao')
client.press('!', states=1)
check('Shift 组合标点不切英文输入', client.commits == ['你好!'], str(client.commits))
client.commits.clear()
client.type('nihao')
client.press('1')
check('数字仍可选中文候选', client.commits == ['你好'], str(client.commits))
client.commits.clear()
check('Ctrl 标点快捷键仍直通', not client.press(',', states=4) and not client.commits)
check('标点释放事件不重复上屏', not client.press(',', release=True) and not client.commits)

client.type('nihao')
client.commits.clear()
for mark in '-=+':
    check('组词翻页键仍被处理 ' + mark, client.press(mark) and not client.commits)
client.press('esc')

with paused_engine():
    client.type('nihao', wait=False)
    client.press(',')
    check('引擎尚未响应时保留原拼音及英文标点', client.commits == ['nihao,'], str(client.commits))
pump(.5)
check('迟到候选不重复上屏', client.commits == ['nihao,'], str(client.commits))

config = Path(os.environ['XDG_CONFIG_HOME']) / 'fcitx5/conf/wetype.conf'
check('设置保存到配置文件', 'AlwaysEnglishPunctuation=True' in config.read_text())
controller.ReloadAddonConfig('wetype')
value, _ = controller.GetConfig(URI)
check('重新加载配置保留英文标点', str(value[KEY]) == 'True')
configure(False)
client.commits.clear()
client.type('nihao')
client.press(',')
check('关闭选项立即恢复中文标点', client.commits == ['你好，'], str(client.commits))
check('关闭选项也被保存', 'AlwaysEnglishPunctuation=False' in config.read_text())

print('SUMMARY english punctuation total=%d failed=%d' % (len(results), results.count(False)), flush=True)
sys.exit(0 if all(results) else 1)
