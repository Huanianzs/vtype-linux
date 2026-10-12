#pragma once
// 官方常用语的本地只读缓存。内容不写日志，支持数字编码及换行文本。
#include <cstdint>
#include <algorithm>
#include <fstream>
#include <string>
#include <utility>
#include <vector>
#include <sys/stat.h>

namespace wetype {
class CommonPhrases {
public:
    void setPath(std::string path) { path_ = std::move(path); }
    bool reload() {
        struct stat info {};
        if (stat(path_.c_str(), &info)) { entries_.clear(); stamp_ = -1; nano_ = -1; return false; }
        if (info.st_size < 8 || info.st_size > 16 * 1024 * 1024) return false;
        if (stamp_ == info.st_mtim.tv_sec && nano_ == info.st_mtim.tv_nsec) return true;
        std::ifstream input(path_, std::ios::binary);
        char magic[4]; input.read(magic, 4);
        if (!input || std::string(magic, 4) != "WXP1") return false;
        const auto count = number(input);
        if (!input || count > 10000) return false;
        std::vector<std::pair<std::string, std::string>> next;
        for (uint32_t i = 0; i < count; ++i) {
            const auto keySize = number(input), valueSize = number(input);
            if (!input || keySize > 128 || !valueSize || valueSize > 65536) return false;
            std::string key(keySize, '\0'), value(valueSize, '\0');
            input.read(key.data(), keySize); input.read(value.data(), valueSize);
            if (!input) return false;
            next.emplace_back(std::move(key), std::move(value));
        }
        if (input.peek() != std::char_traits<char>::eof()) return false;
        entries_ = std::move(next); recommendations_.assign(entries_.size(), {});
        ++revision_; stamp_ = info.st_mtim.tv_sec; nano_ = info.st_mtim.tv_nsec;
        return true;
    }
    std::vector<std::string> lookup(const std::string &prefix) {
        reload(); std::vector<std::string> result;
        for (const auto &item : entries_)
            if (item.first.rfind(prefix, 0) == 0) result.push_back(item.second);
        return result;
    }
    const auto &entries() const { return entries_; }
    uint64_t revision() const { return revision_; }
    void setRecommendation(size_t index, uint64_t revision, std::string code) {
        if (revision == revision_ && index < recommendations_.size())
            recommendations_[index] = std::move(code);
    }
    std::vector<std::string> automaticLookup(const std::string &code) const {
        std::vector<std::string> result;
        if (code.empty()) return result;
        for (size_t i=0; i<entries_.size(); ++i) {
            const auto &entry = entries_[i];
            // 同步载荷中的 key 是官方实际生效的编码；有值时不能再附加推荐码。
            const auto &effective = entry.first.empty() ? recommendations_[i] : entry.first;
            const bool letters = effective.find_first_not_of("abcdefghijklmnopqrstuvwxyz") == std::string::npos;
            if (letters && effective == code)
                if (std::find(result.begin(),result.end(),entry.second) == result.end()) result.push_back(entry.second);
        }
        return result;
    }
    // 数字编码：已输入的数字以编码开头时命中。first 为可保留的已输入位数：
    // 内容以已输入数字开头时等于其长度（只补后半段），否则为 0（需先删除已输入数字）。
    std::vector<std::pair<size_t, std::string>> digitLookup(const std::string &typed) {
        reload(); std::vector<std::pair<size_t, std::string>> result;
        if (typed.empty()) return result;
        for (size_t i=0; i<entries_.size(); ++i) {
            const auto &entry = entries_[i];
            const auto &effective = entry.first.empty() ? recommendations_[i] : entry.first;
            if (effective.empty() || effective.find_first_not_of("0123456789") != std::string::npos) continue;
            if (typed.rfind(effective, 0) != 0) continue;
            if (entry.second.rfind(typed, 0) == 0) {
                if (entry.second.size() > typed.size()) result.emplace_back(typed.size(), entry.second);
            } else if (typed == effective) result.emplace_back(0, entry.second);
        }
        return result;
    }
private:
    static uint32_t number(std::istream &input) {
        unsigned char data[4] {}; input.read(reinterpret_cast<char *>(data), 4);
        return uint32_t(data[0]) | uint32_t(data[1]) << 8 | uint32_t(data[2]) << 16 | uint32_t(data[3]) << 24;
    }
    std::string path_;
    time_t stamp_ = -1; long nano_ = -1;
    std::vector<std::pair<std::string, std::string>> entries_;
    std::vector<std::string> recommendations_;
    uint64_t revision_ = 0;
};
}
