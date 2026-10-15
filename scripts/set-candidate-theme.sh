#!/usr/bin/env bash
# 查看和切换 fcitx5 classicui 的候选窗主题。
#
# 候选窗主题是全局的，配置在 ~/.config/fcitx5/conf/classicui.conf：
#   Theme=...         浅色主题
#   DarkTheme=...     深色主题
#   UseDarkTheme=...  是否跟随系统深浅色
# 本脚本只改这几个键，且先备份，不覆盖其他设置。
set -euo pipefail

conf="${XDG_CONFIG_HOME:-$HOME/.config}/fcitx5/conf/classicui.conf"
dirs=("$HOME/.local/share/fcitx5/themes" /usr/local/share/fcitx5/themes /usr/share/fcitx5/themes)

list() {
  local d t
  for d in "${dirs[@]}"; do
    [ -d "$d" ] || continue
    for t in "$d"/*/; do
      [ -f "$t/theme.conf" ] || continue
      printf '%s\n' "$(basename "$t")"
    done
  done | sort -u
}

usage() {
  cat <<'EOF'
用法：
  set-candidate-theme.sh list
      列出可用主题（来自用户目录和系统目录）。
  set-candidate-theme.sh set --light <主题名> [--dark <主题名>] [--follow-system]
      写入 classicui.conf。省略的项保持不变；--follow-system 打开“跟随系统深浅色”。
      例：set-candidate-theme.sh set --light wechat-light --dark ayaya-dark
EOF
}

action="${1:-}"; shift || true
case "$action" in
  list) list ;;
  set)
    light=""; dark=""; follow=""
    while [ $# -gt 0 ]; do
      case "$1" in
        --light) light="${2:-}"; shift 2 ;;
        --dark) dark="${2:-}"; shift 2 ;;
        --follow-system) follow=1; shift ;;
        *) echo "未知参数：$1" >&2; usage; exit 2 ;;
      esac
    done
    [ -n "$light" ] || [ -n "$dark" ] || [ -n "$follow" ] || { usage; exit 2; }
    available="$(list)"
    for name in "$light" "$dark"; do
      [ -z "$name" ] && continue
      if ! printf '%s\n' "$available" | grep -qxF "$name"; then
        echo "主题 '$name' 不存在。可用主题：" >&2; printf '%s\n' "$available" >&2; exit 1
      fi
    done
    mkdir -p "$(dirname "$conf")"
    if [ -f "$conf" ]; then
      bak="$conf.bak.$(date +%Y%m%d-%H%M%S)"
      cp -a "$conf" "$bak"; echo "已备份到 $bak"
    fi
    THEME_LIGHT="$light" THEME_DARK="$dark" FOLLOW="$follow" CONF="$conf" python3 - <<'PY'
import os, re, pathlib
conf = pathlib.Path(os.environ['CONF'])
updates = {}
if os.environ.get('THEME_LIGHT'): updates['Theme'] = os.environ['THEME_LIGHT']
if os.environ.get('THEME_DARK'): updates['DarkTheme'] = os.environ['THEME_DARK']
if os.environ.get('FOLLOW'): updates['UseDarkTheme'] = 'True'
lines = conf.read_text().splitlines() if conf.exists() else []
seen = set()
out = []
for line in lines:
    m = re.match(r'^(\w+)=(.*)$', line)
    if m and m.group(1) in updates:
        out.append(f"{m.group(1)}={updates[m.group(1)]}"); seen.add(m.group(1))
    else:
        out.append(line)
for k, v in updates.items():
    if k not in seen:
        out.append(f"{k}={v}")
conf.write_text("\n".join(out) + "\n")
print("已更新：", ", ".join(f"{k}={v}" for k, v in updates.items()))
PY
    echo "重启 Fcitx5 或重新登录后生效。"
    ;;
  *) usage; exit 2 ;;
esac
