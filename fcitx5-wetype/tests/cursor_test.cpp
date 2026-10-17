#include "config.h"
#include "pinyin_preedit.h"

#include <fcitx-config/rawconfig.h>
#include <fcitx-utils/key.h>
#include <cassert>
#include <iostream>
#include <stdexcept>

int main() {
    using namespace fcitx;
    try {
        // 1. 默认配置验证与自定义配置加载
        WeTypeConfig config;
        if (!*config.arrowKeysMoveCursor) {
            throw std::runtime_error("default arrowKeysMoveCursor must be true");
        }
        if (!*config.readlineKeyBindings) {
            throw std::runtime_error("default readlineKeyBindings must be true");
        }

        RawConfig raw;
        raw["ArrowKeysMoveCursor"] = "False";
        raw["ReadlineKeyBindings"] = "False";
        config.load(raw, true);

        if (*config.arrowKeysMoveCursor) {
            throw std::runtime_error("arrowKeysMoveCursor failed to load False");
        }
        if (*config.readlineKeyBindings) {
            throw std::runtime_error("readlineKeyBindings failed to load False");
        }

        // 2. 全拼分词与光标位置映射验证
        int dispCursor = -1;

        // "shrufa" 不包含合法完整首音节 ("sh" 只是声母)，作为整体未切分拼音显示
        // 光标在末尾 (cursor = 6) -> "shrufa", 光标在 6
        std::string disp = segmentPinyin("shrufa", 6, &dispCursor);
        if (disp != "shrufa" || dispCursor != 6) {
            throw std::runtime_error("shrufa at 6 failed: disp=" + disp + " cursor=" + std::to_string(dispCursor));
        }

        // "shrufa" 左移到 'h' 后面 (cursor = 2) -> "shrufa", 光标在 2 ("sh|rufa")
        disp = segmentPinyin("shrufa", 2, &dispCursor);
        if (disp != "shrufa" || dispCursor != 2) {
            throw std::runtime_error("shrufa at 2 failed: disp=" + disp + " cursor=" + std::to_string(dispCursor));
        }

        // 插入 'u' 后为 "shurufa", 光标在 3 -> "shu ru fa", 光标在 3 ("shu| ru fa")
        disp = segmentPinyin("shurufa", 3, &dispCursor);
        if (disp != "shu ru fa" || dispCursor != 3) {
            throw std::runtime_error("shurufa at 3 failed: disp=" + disp + " cursor=" + std::to_string(dispCursor));
        }

        // "nihao" 在 0 -> "|ni hao", 光标在 0
        disp = segmentPinyin("nihao", 0, &dispCursor);
        if (disp != "ni hao" || dispCursor != 0) {
            throw std::runtime_error("nihao at 0 failed: disp=" + disp + " cursor=" + std::to_string(dispCursor));
        }

        // "nihao" 在 2 -> "ni| hao", 光标在 2
        disp = segmentPinyin("nihao", 2, &dispCursor);
        if (disp != "ni hao" || dispCursor != 2) {
            throw std::runtime_error("nihao at 2 failed: disp=" + disp + " cursor=" + std::to_string(dispCursor));
        }

        // "nihao" 在 3 -> "ni h|ao", 光标在 4
        disp = segmentPinyin("nihao", 3, &dispCursor);
        if (disp != "ni hao" || dispCursor != 4) {
            throw std::runtime_error("nihao at 3 failed: disp=" + disp + " cursor=" + std::to_string(dispCursor));
        }

        // "nihao" 在 5 -> "ni hao|", 光标在 6
        disp = segmentPinyin("nihao", 5, &dispCursor);
        if (disp != "ni hao" || dispCursor != 6) {
            throw std::runtime_error("nihao at 5 failed: disp=" + disp + " cursor=" + std::to_string(dispCursor));
        }

        // 带隔音符: "xi'an" 在 2 -> "xi|'an", 光标在 2
        disp = segmentPinyin("xi'an", 2, &dispCursor);
        if (disp != "xi'an" || dispCursor != 2) {
            throw std::runtime_error("xi'an at 2 failed: disp=" + disp + " cursor=" + std::to_string(dispCursor));
        }
        // "xi'an" 在 3 -> "xi'|an", 光标在 3
        disp = segmentPinyin("xi'an", 3, &dispCursor);
        if (disp != "xi'an" || dispCursor != 3) {
            throw std::runtime_error("xi'an at 3 failed: disp=" + disp + " cursor=" + std::to_string(dispCursor));
        }

        // pinyinPreedit 返回的 Text 对象应携带 cursor
        Text t1 = pinyinPreedit("shurufa", false, 3);
        if (t1.toString() != "shu ru fa" || t1.cursor() != 3) {
            throw std::runtime_error("Text pinyinPreedit failed: text=" + t1.toString() + " cursor=" + std::to_string(t1.cursor()));
        }

        // 3. 双拼分词与光标位置映射验证
        Text t2 = pinyinPreedit("shrf", true, 2);
        if (t2.toString() != "sh rf" || t2.cursor() != 2) {
            throw std::runtime_error("double pinyin at 2 failed: text=" + t2.toString() + " cursor=" + std::to_string(t2.cursor()));
        }
        Text t3 = pinyinPreedit("shrf", true, 4);
        if (t3.toString() != "sh rf" || t3.cursor() != 5) {
            throw std::runtime_error("double pinyin at 4 failed: text=" + t3.toString() + " cursor=" + std::to_string(t3.cursor()));
        }

        // 4. Readline 快捷键匹配验证
        if (!Key(FcitxKey_a, KeyState::Ctrl).check(FcitxKey_a, KeyState::Ctrl)) {
            throw std::runtime_error("Ctrl+A check failed");
        }
        if (!Key(FcitxKey_e, KeyState::Ctrl).check(FcitxKey_e, KeyState::Ctrl)) {
            throw std::runtime_error("Ctrl+E check failed");
        }
        if (!Key(FcitxKey_b, KeyState::Ctrl).check(FcitxKey_b, KeyState::Ctrl)) {
            throw std::runtime_error("Ctrl+B check failed");
        }
        if (!Key(FcitxKey_f, KeyState::Ctrl).check(FcitxKey_f, KeyState::Ctrl)) {
            throw std::runtime_error("Ctrl+F check failed");
        }
        if (!Key(FcitxKey_d, KeyState::Ctrl).check(FcitxKey_d, KeyState::Ctrl)) {
            throw std::runtime_error("Ctrl+D check failed");
        }
        if (!Key(FcitxKey_h, KeyState::Ctrl).check(FcitxKey_h, KeyState::Ctrl)) {
            throw std::runtime_error("Ctrl+H check failed");
        }
        if (!Key(FcitxKey_k, KeyState::Ctrl).check(FcitxKey_k, KeyState::Ctrl)) {
            throw std::runtime_error("Ctrl+K check failed");
        }
        if (!Key(FcitxKey_u, KeyState::Ctrl).check(FcitxKey_u, KeyState::Ctrl)) {
            throw std::runtime_error("Ctrl+U check failed");
        }

        std::cout << "PASS cursor_test: config, pinyin segmentation cursor mapping, and readline keys\n";
        return 0;
    } catch (const std::exception &err) {
        std::cerr << "FAIL " << err.what() << '\n';
        return 1;
    }
}
