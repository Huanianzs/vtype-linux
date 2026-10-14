#!/bin/bash
# WeType 引擎 CLI 演示: wetype-ime-demo.sh <拼音串> → 候选词
# 用法: bash wetype-ime-demo.sh nihao    (引擎目录由 WETYPE_ENGINE_DIR 指定, 默认开发目录)
set -e
ulimit -c 0
WORD="${1:-nihao}"
# 引擎目录定位：脚本所在目录自身就是引擎目录（安装/AppImage 布局：arm64/{lib,dicts,...}）；
# 否则回退上一级（开发树布局：scripts 在 src/ 或仓库根下）。WETYPE_ENGINE_DIR 始终优先。
ENG="${WETYPE_ENGINE_DIR:-}"
if [ -z "$ENG" ]; then
  SELF="$(readlink -f -- "${BASH_SOURCE[0]}")"
  SELF_DIR="$(cd "$(dirname "$SELF")" && pwd)"
  if [ -d "$SELF_DIR/lib" ] || [ -x "$SELF_DIR/wetype-harness" ]; then ENG="$SELF_DIR"
  else ENG="$(cd "$SELF_DIR/.." && pwd)"
  fi
fi
HARNESS="$ENG/harness/jinterop"
[ -x "$HARNESS" ] || HARNESS="$ENG/wetype-harness"
if [ -z "${WETYPE_DOUBLE_PIN+x}" ]; then
  WETYPE_DOUBLE_PIN=0
  CONFIG="${XDG_CONFIG_HOME:-$HOME/.config}/fcitx5/conf/wetype.conf"
  if [ -r "$CONFIG" ]; then
    while IFS='=' read -r key value; do
      if [ "$key" = PinyinScheme ] && [ "$value" = 小鹤双拼 ]; then
        WETYPE_DOUBLE_PIN=3
      fi
    done < "$CONFIG"
  fi
  export WETYPE_DOUBLE_PIN
fi
LIBDIR="$ENG/lib"
[ -d "$LIBDIR" ] || LIBDIR="$ENG/runtime"   # 开发目录布局
DICTS="${WETYPE_DICT_DIR:-$ENG/dicts}"
[ -d "$DICTS" ] || DICTS="$ENG/.deps/wechat-ime/assets/config/beta"   # source checkout
WORK="${WETYPE_WORK_DIR:-${XDG_DATA_HOME:-$HOME/.local/share}/wetype-ime/dict}"
SYSROOT="${WETYPE_SYSROOT:-}"
if [ -z "$SYSROOT" ]; then   # bionic 运行时：安装目录 sysroot/，源码树 runtime/sysroot/
  if [ -d "$ENG/sysroot/system" ]; then SYSROOT="$ENG/sysroot"; else SYSROOT="$ENG/runtime/sysroot"; fi
fi
QEMU="${QEMU_AARCH64:-}"
if [ -z "$QEMU" ]; then   # 安装包自带 QEMU；ARM64 宿主无 QEMU 时直接运行（harness 解释器已指向 linker64）
  if [ -x "$ENG/qemu-aarch64-static" ]; then QEMU="$ENG/qemu-aarch64-static"
  elif [ "$(uname -m)" != aarch64 ]; then QEMU=qemu-aarch64-static   # 源码树回落到系统包
  fi
fi
RUN=()
if [ -n "$QEMU" ]; then
  # 默认的 max 会启用指针认证，QEMU 用软件计算，慢约 2 倍
  RUN=("$QEMU" -cpu "${QEMU_CPU:-cortex-a72}" -L "$SYSROOT")
else
  LIBDIR_EXTRA=":$SYSROOT/system/lib64"
fi

mkdir -p "$WORK/userdict/v5" "$WORK/userdict/user_hot_word"

# 拼音串 → L 命令序列
CMDS="PING"
for ((i=0; i<${#WORD}; i++)); do CMDS+="|L ${WORD:$i:1}"; done
CMDS+="|Q"

printf '%b\n' "${CMDS//|/\\n}" | \
  env LD_LIBRARY_PATH="$LIBDIR${LIBDIR_EXTRA:-}" WETYPE_DICT_DIR="$DICTS" \
      WETYPE_WORK_DIR="$WORK" \
  "${RUN[@]}" "$HARNESS" "$([ -f "$LIBDIR/libwxhld_jni.so" ] && echo "$LIBDIR/libwxhld_jni.so" || echo runtime/libwxhld_jni.so)" --daemon 2>/dev/null | \
  while IFS= read -r line; do
    case "$line" in
      CAND*) echo "候选: ${line#CAND$'\t'}" | tr '\t' ' ' ;;
    esac
  done
