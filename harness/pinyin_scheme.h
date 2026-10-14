#ifndef WETYPE_PINYIN_SCHEME_H
#define WETYPE_PINYIN_SCHEME_H

/* 官方 3.5.4 DoublePinSolution：0=全拼，3=小鹤；其他方案编号为 1..7。
 * 只接受完整的一位数字；未设置或错误配置退回全拼。 */
static inline int wetype_double_pin_solution(const char *value) {
    return value && value[0] >= '0' && value[0] <= '7' && value[1] == '\0'
        ? value[0] - '0' : 0;
}

#endif
