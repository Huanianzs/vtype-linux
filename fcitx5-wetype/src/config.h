#pragma once

#include <fcitx-config/configuration.h>
#include <fcitx-config/enum.h>
#include <fcitx-config/option.h>
#include <fcitx-utils/i18n.h>
#include <fcitx-utils/key.h>
#include <fcitx-utils/keysym.h>

namespace fcitx {

enum class PinyinScheme { FullPinyin, Flypy };
FCITX_CONFIG_ENUM_NAME_WITH_I18N(PinyinScheme, N_("全拼"), N_("小鹤双拼"));

FCITX_CONFIGURATION(WeTypeConfig,
    OptionWithAnnotation<PinyinScheme, PinyinSchemeI18NAnnotation> pinyinScheme{
        this, "PinyinScheme", "拼音方案", PinyinScheme::FullPinyin};
    Option<bool> alwaysEnglishPunctuation{
        this, "AlwaysEnglishPunctuation", "始终使用英文标点", false};
    KeyListOption prevPage{
        this, "PrevPage", "上一页",
        {Key(FcitxKey_minus), Key(FcitxKey_KP_Subtract), Key(FcitxKey_Up), Key(FcitxKey_Page_Up)},
        KeyListConstrain(KeyConstrainFlag::AllowModifierLess)};
    KeyListOption nextPage{
        this, "NextPage", "下一页",
        {Key(FcitxKey_equal), Key(FcitxKey_plus), Key(FcitxKey_KP_Add), Key(FcitxKey_Down), Key(FcitxKey_Page_Down)},
        KeyListConstrain(KeyConstrainFlag::AllowModifierLess)};);

}  // namespace fcitx
