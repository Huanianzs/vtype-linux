#include "common_phrases.h"

#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <filesystem>
#include <fstream>
#include <stdexcept>
#include <string>
#include <utility>
#include <vector>

static void require(bool ok, const char *message) {
    if (!ok) throw std::runtime_error(message);
}

static void put(std::ofstream &file, uint32_t value) {
    const char bytes[4] = {char(value), char(value >> 8), char(value >> 16), char(value >> 24)};
    file.write(bytes, 4);
}

int main() {
    char name[] = "/tmp/wetype-phrases-test.XXXXXX";
    const char *dir = ::mkdtemp(name);
    if (!dir) return 1;
    struct Cleanup {
        std::filesystem::path path;
        ~Cleanup() { std::filesystem::remove_all(path); }
    } cleanup{dir};
    try {
        const std::vector<std::pair<std::string, std::string>> rows = {
            {"138", "13800001111"}, {"138", "13899990000"}, {"999", "测试内容"}, {"mail", "a@b.c"}, {"12", "12"}};
        const auto path = (cleanup.path / "phrases.bin").string();
        {
            std::ofstream file(path, std::ios::binary);
            file.write("WXP1", 4); put(file, rows.size());
            for (const auto &[code, text] : rows) {
                put(file, code.size()); put(file, text.size());
                file.write(code.data(), code.size()); file.write(text.data(), text.size());
            }
        }
        wetype::CommonPhrases phrases;
        phrases.setPath(path);
        require(phrases.digitLookup("13").empty(), "编码未输完不应命中");
        auto hits = phrases.digitLookup("138");
        require(hits.size() == 2 && hits[0].first == 3 && hits[0].second == "13800001111", "数字前缀命中两条");
        hits = phrases.digitLookup("1389");
        require(hits.size() == 1 && hits[0].second == "13899990000", "多输入一位按内容继续筛选");
        hits = phrases.digitLookup("999");
        require(hits.size() == 1 && hits[0].first == 0, "内容不以编码开头时需替换已输入数字");
        require(phrases.digitLookup("9999").empty(), "替换型只在编码完全相同时命中");
        require(phrases.digitLookup("12").empty(), "内容与已输入相同时无可补全部分");
        require(phrases.automaticLookup("mail").size() == 1, "字母编码不受影响");
    } catch (const std::exception &error) {
        std::fprintf(stderr, "%s\n", error.what());
        return 1;
    }
    return 0;
}
