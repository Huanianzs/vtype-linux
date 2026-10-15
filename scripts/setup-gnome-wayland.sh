#!/usr/bin/env bash
# 为 Wayland 会话里的 fcitx5（微信拼音）配置所需的桌面环境变量。
#
# 是否需要这些变量取决于【桌面】，而不是发行版版本号：
#   * GNOME / Mutter 不实现 Wayland 输入法协议，fcitx5 只能作用于走 XWayland
#     的程序；应用跑原生 Wayland 时候选窗坐标会漂移。→ 需要本脚本。
#   * KDE Plasma、Sway、Hyprland、Niri 等实现了 input-method 协议 →
#     原生 Wayland 即可，不需要强制 XWayland。
#   * X11 会话 → fcitx5 本来就能用。
#
# 因此在 Ubuntu 22.04 / 24.04 / 26.04，以及 Pop!_OS、Linux Mint、Kubuntu 等
# Ubuntu 系发行版上都用同一套桌面判断，不依赖具体版本。
#
# 变量取值必须合法，写错会让对应程序起不来：
#   GDK_BACKEND=x11      GTK 的后端名就是 x11
#   QT_QPA_PLATFORM=xcb  Qt 的平台插件叫 xcb，不是 x11
#                        （写成 x11，微信这类静态链接 Qt 的程序会找不到
#                          平台插件，启动即 abort）
#   ELECTRON_OZONE_PLATFORM_HINT=x11   Electron/Chromium 用 x11
set -euo pipefail

case "${1:-}" in
  --dry-run) dry_run=1 ;;
  -h|--help) sed -n '2,20p' "$0"; exit 0 ;;
  *) dry_run=0 ;;
esac

conf_dir="${XDG_CONFIG_HOME:-$HOME/.config}/environment.d"
conf="$conf_dir/00-ime.conf"

session_type="${XDG_SESSION_TYPE:-}"
if [ -z "$session_type" ]; then
  if [ -n "${WAYLAND_DISPLAY:-}" ]; then session_type=wayland; else session_type=x11; fi
fi
desktop="${XDG_CURRENT_DESKTOP:-}"

if [ -r /etc/os-release ]; then
  # shellcheck disable=SC1091
  . /etc/os-release
  echo "发行版：${PRETTY_NAME:-未知}（ID=${ID:-}  ID_LIKE=${ID_LIKE:-}）"
fi
echo "会话：XDG_SESSION_TYPE=$session_type  XDG_CURRENT_DESKTOP=${desktop:-（空）}"

if [ "$session_type" != "wayland" ]; then
  echo "非 Wayland 会话：fcitx5 按常规方式配置即可，无需本脚本。"
  exit 0
fi

if printf '%s' "$desktop" | grep -qi gnome; then
  :
elif printf '%s' "$desktop" | grep -qiE 'kde|plasma|sway|hyprland|niri|river|wayfire|cosmic'; then
  echo "桌面 ${desktop} 已经实现 Wayland 输入法协议，不需要强制 XWayland，跳过。"
  exit 0
else
  echo "未识别的桌面：${desktop:-（空）}，为避免误伤不做改动。" >&2
  echo "若确实是 GNOME，请在 GNOME 会话内重跑；否则手动设置变量，见 docs/安装与使用.md 第 6 节。" >&2
  exit 0
fi

if [ "$dry_run" = 1 ]; then
  echo "[dry-run] 将写入 $conf（含 XMODIFIERS / GDK_BACKEND=x11 / QT_QPA_PLATFORM=xcb 等）"
  exit 0
fi

mkdir -p "$conf_dir"
if [ -e "$conf" ]; then
  bak="$conf.bak.$(date +%Y%m%d-%H%M%S)"
  cp -a "$conf" "$bak"
  echo "已备份原配置到 $bak"
fi

cat > "$conf" <<'EOF'
# 由 vtype-linux scripts/setup-gnome-wayland.sh 生成
# GNOME Wayland：让应用走 XWayland，fcitx5 的 X11 候选窗才能对准光标。
XMODIFIERS=@im=fcitx
SDL_IM_MODULE=fcitx

# GTK / Qt / Electron / Firefox 的 X11 后端。
# 值必须合法：GDK 用 x11；Qt 平台插件叫 xcb（写成 x11 会让 Qt 程序启动即崩）。
GDK_BACKEND=x11
QT_QPA_PLATFORM=xcb
QT_IM_MODULE=fcitx
ELECTRON_OZONE_PLATFORM_HINT=x11
MOZ_ENABLE_WAYLAND=0
EOF

echo "已写入 $conf"
echo "注销并重新登录后生效（environment.d 只在登录时读取）。"
echo
echo "注意："
echo "  * GNOME 会弹 Desktop Icons NG 的'X11 while on Wayland'警告，这是强制 XWayland 的副作用，可忽略。"
echo "  * 个别应用若在 XWayland 下异常（如某些 Qt 程序），给它单独用 .desktop 覆盖即可，不要动这里。"
