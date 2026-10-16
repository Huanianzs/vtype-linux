#include "config.h"
#include "fuzzy_pinyin.h"

#include <fcitx-config/rawconfig.h>
#include <cassert>
#include <iostream>
#include <stdexcept>

int main() {
    using namespace fcitx;
    try {
        // 1. 验证 C 语言位掩码解析
        if (wetype_parse_fuzzy_flags(nullptr) != 0) throw std::runtime_error("null parsed non-zero");
        if (wetype_parse_fuzzy_flags("") != 0) throw std::runtime_error("empty parsed non-zero");
        if (wetype_parse_fuzzy_flags("0") != 0) throw std::runtime_error("zero parsed non-zero");
        if (wetype_parse_fuzzy_flags("5") != 5) throw std::runtime_error("number 5 mismatch");
        if (wetype_parse_fuzzy_flags("0x105") != 0x105) throw std::runtime_error("hex mismatch");

        // 验证字符串解析 (按 key 或 field 名)
        uint32_t parsed = wetype_parse_fuzzy_flags("z_zh,s_sh,n_l");
        uint32_t expected = WETYPE_FUZZY_Z_ZH | WETYPE_FUZZY_S_SH | WETYPE_FUZZY_N_L;
        if (parsed != expected) throw std::runtime_error("comma string parse mismatch");

        parsed = wetype_parse_fuzzy_flags("enable_c_ch, enable_ang; enable_huang_wang");
        expected = WETYPE_FUZZY_C_CH | WETYPE_FUZZY_AN_ANG | WETYPE_FUZZY_HUANG_WANG;
        if (parsed != expected) throw std::runtime_error("field string parse mismatch");

        // 2. 验证 WeTypeConfig 默认值 (模糊音全关)
        WeTypeConfig config;
        if (config.fuzzyFlags() != 0) throw std::runtime_error("default fuzzyFlags not 0");

        // 3. 验证从 RawConfig 加载
        RawConfig raw;
        raw["Fuzzy_Z_ZH"] = "True";
        raw["Fuzzy_S_SH"] = "True";
        raw["Fuzzy_IN_ING"] = "True";
        config.load(raw, true);

        expected = WETYPE_FUZZY_Z_ZH | WETYPE_FUZZY_S_SH | WETYPE_FUZZY_IN_ING;
        if (config.fuzzyFlags() != expected) throw std::runtime_error("load raw config mismatch");

        // 4. 验证 setFuzzyFlags
        uint32_t allFlags = (1u << WETYPE_FUZZY_PAIRS_COUNT) - 1;
        config.setFuzzyFlags(allFlags);
        if (config.fuzzyFlags() != allFlags) throw std::runtime_error("all flags set mismatch");

        config.setFuzzyFlags(0);
        if (config.fuzzyFlags() != 0) throw std::runtime_error("clear all flags mismatch");

        std::cout << "PASS fuzzy_pinyin_test\n";
        return 0;
    } catch (const std::exception &err) {
        std::cerr << "FAIL " << err.what() << '\n';
        return 1;
    }
}
