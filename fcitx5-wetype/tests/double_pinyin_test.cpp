#include "pinyin_scheme.h"
#include <cstdlib>
#include <iostream>

int main() {
    const char *invalid[] = {nullptr, "", "8", "9", "-1", "3x", "03", " 3", "3 "};
    for (const char *value : invalid) {
        if (wetype_double_pin_solution(value) != 0) {
            std::cerr << "错误方案未退回全拼\n";
            return EXIT_FAILURE;
        }
    }
    for (int expected = 0; expected <= 7; ++expected) {
        const char value[] = {static_cast<char>('0' + expected), '\0'};
        if (wetype_double_pin_solution(value) != expected) {
            std::cerr << "官方方案编号解析错误\n";
            return EXIT_FAILURE;
        }
    }
    return EXIT_SUCCESS;
}
