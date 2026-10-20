#include "config.h"

#include <fcitx-config/rawconfig.h>
#include <fcitx-utils/key.h>
#include <cassert>
#include <iostream>
#include <stdexcept>

int main() {
    using namespace fcitx;
    try {
        WeTypeConfig config;

        // 1. 默认配置验证
        const auto &prev = *config.prevPage;
        const auto &next = *config.nextPage;

        if (!Key(FcitxKey_minus).checkKeyList(prev)) throw std::runtime_error("default prevPage missing minus");
        if (!Key(FcitxKey_KP_Subtract).checkKeyList(prev)) throw std::runtime_error("default prevPage missing KP_Subtract");
        if (!Key(FcitxKey_Up).checkKeyList(prev)) throw std::runtime_error("default prevPage missing Up");
        if (!Key(FcitxKey_Page_Up).checkKeyList(prev)) throw std::runtime_error("default prevPage missing Page_Up");

        if (!Key(FcitxKey_equal).checkKeyList(next)) throw std::runtime_error("default nextPage missing equal");
        if (!Key(FcitxKey_plus).checkKeyList(next)) throw std::runtime_error("default nextPage missing plus");
        if (!Key(FcitxKey_KP_Add).checkKeyList(next)) throw std::runtime_error("default nextPage missing KP_Add");
        if (!Key(FcitxKey_Down).checkKeyList(next)) throw std::runtime_error("default nextPage missing Down");
        if (!Key(FcitxKey_Page_Down).checkKeyList(next)) throw std::runtime_error("default nextPage missing Page_Down");

        if (Key(FcitxKey_comma).checkKeyList(prev)) throw std::runtime_error("default prevPage unexpectedly matched comma");
        if (Key(FcitxKey_period).checkKeyList(next)) throw std::runtime_error("default nextPage unexpectedly matched period");

        // 2. 自定义逗号与句号翻页
        RawConfig raw;
        raw["PrevPage"]["0"] = "comma";
        raw["NextPage"]["0"] = "period";
        config.load(raw, true);

        const auto &customPrev = *config.prevPage;
        const auto &customNext = *config.nextPage;

        if (!Key(FcitxKey_comma).checkKeyList(customPrev)) throw std::runtime_error("custom prevPage failed to match comma");
        if (!Key(FcitxKey_period).checkKeyList(customNext)) throw std::runtime_error("custom nextPage failed to match period");
        if (Key(FcitxKey_minus).checkKeyList(customPrev)) throw std::runtime_error("custom prevPage still matched minus");
        if (Key(FcitxKey_equal).checkKeyList(customNext)) throw std::runtime_error("custom nextPage still matched equal");

        // 3. 自定义方括号翻页 (bracketleft / bracketright)
        RawConfig bracketRaw;
        bracketRaw["PrevPage"]["0"] = "bracketleft";
        bracketRaw["NextPage"]["0"] = "bracketright";
        config.load(bracketRaw, true);

        if (!Key(FcitxKey_bracketleft).checkKeyList(*config.prevPage)) throw std::runtime_error("custom bracketleft failed");
        if (!Key(FcitxKey_bracketright).checkKeyList(*config.nextPage)) throw std::runtime_error("custom bracketright failed");

        std::cout << "PASS paging_config: default keys, custom comma/period, bracket keys\n";
        return 0;
    } catch (const std::exception &err) {
        std::cerr << "FAIL " << err.what() << '\n';
        return 1;
    }
}
