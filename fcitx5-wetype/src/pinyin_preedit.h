#pragma once

#include <fcitx/text.h>
#include <algorithm>
#include <sstream>
#include <string>
#include <unordered_set>

namespace fcitx {

// Display-only segmentation. The original unsegmented buffer is still sent to
// the WeType engine, so this never changes composition or candidate matching.
static inline std::string segmentPinyin(const std::string &raw, int rawCursor = -1, int *displayCursor = nullptr) {
    static const std::unordered_set<std::string> syllables = [] {
        static const char *data =
            "a ai an ang ao e ei en eng er o ou "
            "ba bai ban bang bao bei ben beng bi bian biao bie bin bing bo bu "
            "pa pai pan pang pao pei pen peng pi pian piao pie pin ping po pou pu "
            "ma mai man mang mao me mei men meng mi mian miao mie min ming miu mo mou mu "
            "fa fan fang fei fen feng fo fou fu "
            "da dai dan dang dao de dei den deng di dia dian diao die ding diu dong dou du duan dui dun duo "
            "ta tai tan tang tao te teng ti tian tiao tie ting tong tou tu tuan tui tun tuo "
            "na nai nan nang nao ne nei nen neng ng ni nian niang niao nie nin ning niu nong nou nu nuan nue nuo nv nve "
            "la lai lan lang lao le lei leng li lia lian liang liao lie lin ling liu long lou lu luan lue lun luo lv "
            "ga gai gan gang gao ge gei gen geng gong gou gu gua guai guan guang gui gun guo "
            "ka kai kan kang kao ke kei ken keng kong kou ku kua kuai kuan kuang kui kun kuo "
            "ha hai han hang hao he hei hen heng hong hou hu hua huai huan huang hui hun huo "
            "za zai zan zang zao ze zei zen zeng zha zhai zhan zhang zhao zhe zhei zhen zheng zhi zhong zhou zhu zhua zhuai zhuan zhuang zhui zhun zhuo zi zong zou zu zuan zui zun zuo "
            "ca cai can cang cao ce cen ceng cha chai chan chang chao che chen cheng chi chong chou chu chua chuai chuan chuang chui chun chuo ci cong cou cu cuan cui cun cuo "
            "sa sai san sang sao se sen seng sha shai shan shang shao she shei shen sheng shi shou shu shua shuai shuan shuang shui shun shuo si song sou su suan sui sun suo "
            "ra ran rang rao re ren reng ri rong rou ru ruan rui run ruo "
            "ji jia jian jiang jiao jie jin jing jiong jiu ju juan jue jun "
            "qi qia qian qiang qiao qie qin qing qiong qiu qu quan que qun "
            "xi xia xian xiang xiao xie xin xing xiong xiu xu xuan xue xun "
            "ya yan yang yao ye yi yin ying yo yong you yu yuan yue yun "
            "wa wai wan wang wei wen weng wo wu "
            "bo bei ben beng bian bie bin bing "
            "ge gei gen geng gong gou gua guai guan guang gui gun guo "
            "jiong juan jue jun";
        std::unordered_set<std::string> result;
        std::istringstream input(data);
        std::string item;
        while (input >> item) result.insert(item);
        return result;
    }();

    std::string out;
    int dispCursor = -1;
    if (rawCursor == 0) {
        dispCursor = 0;
    }
    for (size_t i = 0; i < raw.size();) {
        if (raw[i] == '\'') {
            out += raw[i++];
            if (static_cast<int>(i) == rawCursor) dispCursor = static_cast<int>(out.size());
            continue;
        }
        size_t match = 0;
        const size_t limit = std::min(raw.size(), i + 6);
        for (size_t end = limit; end > i; --end) {
            if (raw.find('\'', i) < end) continue;
            if (syllables.count(raw.substr(i, end - i))) {
                match = end - i;
                break;
            }
        }
        if (match) {
            if (!out.empty() && out.back() != '\'' && out.back() != ' ') out += ' ';
            for (size_t m = 0; m < match; ++m) {
                out += raw[i++];
                if (static_cast<int>(i) == rawCursor) dispCursor = static_cast<int>(out.size());
            }
        } else {
            if (!out.empty() && out.back() != '\'' && out.back() != ' ') out += ' ';
            while (i < raw.size()) {
                out += raw[i++];
                if (static_cast<int>(i) == rawCursor) dispCursor = static_cast<int>(out.size());
            }
            break;
        }
    }
    if (displayCursor) {
        if (dispCursor < 0 && rawCursor >= 0) dispCursor = static_cast<int>(out.size());
        *displayCursor = dispCursor;
    }
    return out;
}

static inline Text pinyinPreedit(const std::string &buffer, bool doublePin, int cursor = -1) {
    Text text;
    std::string display;
    int displayCursor = -1;
    if (doublePin) {
        // 双拼编码每两键一个音节；不按全拼词表切分，也不改动引擎输入。
        if (cursor == 0) displayCursor = 0;
        for (size_t i = 0; i < buffer.size();) {
            if (i && !display.empty() && display.back() != ' ') display += ' ';
            for (size_t k = 0; k < 2 && i < buffer.size(); ++k) {
                display += buffer[i++];
                if (static_cast<int>(i) == cursor) displayCursor = static_cast<int>(display.size());
            }
        }
        if (cursor >= 0 && displayCursor < 0) displayCursor = static_cast<int>(display.size());
    } else {
        display = segmentPinyin(buffer, cursor, &displayCursor);
    }
    if (!display.empty()) {
        text.append(display, TextFormatFlag::NoFlag);
        if (displayCursor >= 0) {
            text.setCursor(displayCursor);
        }
    }
    return text;
}

}  // namespace fcitx
