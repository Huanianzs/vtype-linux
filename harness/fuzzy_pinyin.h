#ifndef WETYPE_FUZZY_PINYIN_H
#define WETYPE_FUZZY_PINYIN_H

#include <stdint.h>
#include <stdlib.h>
#include <string.h>

#ifdef __cplusplus
extern "C" {
#endif

enum WeTypeFuzzyFlag {
    WETYPE_FUZZY_Z_ZH       = 1u << 0,
    WETYPE_FUZZY_C_CH       = 1u << 1,
    WETYPE_FUZZY_S_SH       = 1u << 2,
    WETYPE_FUZZY_N_L        = 1u << 3,
    WETYPE_FUZZY_H_F        = 1u << 4,
    WETYPE_FUZZY_R_L        = 1u << 5,
    WETYPE_FUZZY_G_K        = 1u << 6,
    WETYPE_FUZZY_AN_ANG     = 1u << 7,
    WETYPE_FUZZY_EN_ENG     = 1u << 8,
    WETYPE_FUZZY_IN_ING     = 1u << 9,
    WETYPE_FUZZY_IAN_IANG   = 1u << 10,
    WETYPE_FUZZY_UAN_UANG   = 1u << 11,
    WETYPE_FUZZY_ON_ONG     = 1u << 12,
    WETYPE_FUZZY_ENG_ONG    = 1u << 13,
    WETYPE_FUZZY_UN_ONG     = 1u << 14,
    WETYPE_FUZZY_UN_IONG    = 1u << 15,
    WETYPE_FUZZY_AN_AI      = 1u << 16,
    WETYPE_FUZZY_HUI_FEI    = 1u << 17,
    WETYPE_FUZZY_HUANG_WANG = 1u << 18,
};

typedef struct {
    const char *key;      /* 配置名 / 别名，如 "z_zh" */
    const char *field;    /* SessionConfig$InputAugmenter 字段名，如 "enable_z_zh" */
    const char *desc;     /* 人类可读说明，如 "z = zh" */
    uint32_t flag;        /* 对应位掩码 */
} WeTypeFuzzyPair;

static const WeTypeFuzzyPair WETYPE_FUZZY_PAIRS[] = {
    {"z_zh",       "enable_z_zh",       "z = zh",       WETYPE_FUZZY_Z_ZH},
    {"c_ch",       "enable_c_ch",       "c = ch",       WETYPE_FUZZY_C_CH},
    {"s_sh",       "enable_s_sh",       "s = sh",       WETYPE_FUZZY_S_SH},
    {"n_l",        "enable_nl",         "n = l",        WETYPE_FUZZY_N_L},
    {"h_f",        "enable_hf",         "h = f",        WETYPE_FUZZY_H_F},
    {"r_l",        "enable_rl",         "r = l",        WETYPE_FUZZY_R_L},
    {"g_k",        "enable_gk",         "g = k",        WETYPE_FUZZY_G_K},
    {"an_ang",     "enable_ang",        "an = ang",     WETYPE_FUZZY_AN_ANG},
    {"en_eng",     "enable_eng",        "en = eng",     WETYPE_FUZZY_EN_ENG},
    {"in_ing",     "enable_ing",        "in = ing",     WETYPE_FUZZY_IN_ING},
    {"ian_iang",   "enable_iang",       "ian = iang",   WETYPE_FUZZY_IAN_IANG},
    {"uan_uang",   "enable_uang",       "uan = uang",   WETYPE_FUZZY_UAN_UANG},
    {"on_ong",     "enable_ong",        "on = ong",     WETYPE_FUZZY_ON_ONG},
    {"eng_ong",    "enable_eng_ong",    "eng = ong",    WETYPE_FUZZY_ENG_ONG},
    {"un_ong",     "enable_un_ong",     "un = ong",     WETYPE_FUZZY_UN_ONG},
    {"un_iong",    "enable_un_iong",    "un = iong",    WETYPE_FUZZY_UN_IONG},
    {"an_ai",      "enable_an_ai",      "an = ai",      WETYPE_FUZZY_AN_AI},
    {"hui_fei",    "enable_hui_fei",    "hui = fei",    WETYPE_FUZZY_HUI_FEI},
    {"huang_wang", "enable_huang_wang", "huang = wang", WETYPE_FUZZY_HUANG_WANG},
};

static const size_t WETYPE_FUZZY_PAIRS_COUNT = sizeof(WETYPE_FUZZY_PAIRS) / sizeof(WETYPE_FUZZY_PAIRS[0]);

/* 解析环境变量为位掩码：支持数字/十六进制，也支持逗号分隔的 key（如 "z_zh,s_sh,n_l"）或 field 字段名 */
static inline uint32_t wetype_parse_fuzzy_flags(const char *env_val) {
    if (!env_val || !*env_val) return 0;
    char *end = NULL;
    unsigned long val = strtoul(env_val, &end, 0);
    if (end && *end == '\0') {
        return (uint32_t)val;
    }
    uint32_t flags = 0;
    const char *p = env_val;
    while (*p) {
        while (*p == ',' || *p == ' ' || *p == '\t' || *p == ';') p++;
        if (!*p) break;
        const char *start = p;
        while (*p && *p != ',' && *p != ' ' && *p != '\t' && *p != ';') p++;
        size_t len = p - start;
        for (size_t i = 0; i < WETYPE_FUZZY_PAIRS_COUNT; i++) {
            if (strlen(WETYPE_FUZZY_PAIRS[i].key) == len &&
                strncmp(WETYPE_FUZZY_PAIRS[i].key, start, len) == 0) {
                flags |= WETYPE_FUZZY_PAIRS[i].flag;
                break;
            }
            if (strlen(WETYPE_FUZZY_PAIRS[i].field) == len &&
                strncmp(WETYPE_FUZZY_PAIRS[i].field, start, len) == 0) {
                flags |= WETYPE_FUZZY_PAIRS[i].flag;
                break;
            }
        }
    }
    return flags;
}

#ifdef __cplusplus
}
#endif

#endif /* WETYPE_FUZZY_PINYIN_H */
