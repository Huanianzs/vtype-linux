#!/usr/bin/env bash
# Fetch (or take) the pinned WeType APK and extract only the files this project uses.
# The binary patches target one exact build, so every APK is checked against its SHA-256.
set -euo pipefail

WETYPE_VERSION=3.5.4
WETYPE_APK_URL="https://download.z.weixin.qq.com/app/android/$WETYPE_VERSION/wxkb_1308_32.apk"
WETYPE_APK_SHA256=7b57a5a9ab3aefd30413165f298213961bd201815ab48c6ad205c3b2950a90fb

BASE="$(cd "$(dirname "$0")/.." && pwd)"
APK="${1:-}"
DEST="${WETYPE_APK_ROOT:-$BASE/.deps/wechat-ime}"
CACHE="${WETYPE_APK_CACHE:-${XDG_CACHE_HOME:-$HOME/.cache}/wetype-ime}"

if [[ $# -gt 1 || "$APK" == -* ]]; then
  echo "Usage: $0 [/path/to/WeType-$WETYPE_VERSION.apk]" >&2
  echo "Without an APK, WeType $WETYPE_VERSION is downloaded from Tencent's official server." >&2
  exit 2
fi
for tool in unzip sha256sum; do
  command -v "$tool" >/dev/null || { echo "Missing dependency: $tool" >&2; exit 1; }
done

apk_ok() { [[ "$(sha256sum "$1" | cut -d' ' -f1)" == "$WETYPE_APK_SHA256" ]]; }

if [[ -z "$APK" ]]; then
  APK="$CACHE/wetype_$WETYPE_VERSION.apk"
  if [[ -f "$APK" ]] && apk_ok "$APK"; then
    echo "Using cached WeType $WETYPE_VERSION APK: $APK"
  else
    mkdir -p "$CACHE"
    echo "Downloading WeType $WETYPE_VERSION APK (214 MB) from $WETYPE_APK_URL"
    if command -v curl >/dev/null; then
      curl -fL --retry 3 -o "$APK.part" "$WETYPE_APK_URL"
    elif command -v wget >/dev/null; then
      wget -O "$APK.part" "$WETYPE_APK_URL"
    else
      echo "Missing dependency: curl or wget" >&2
      exit 1
    fi
    mv "$APK.part" "$APK"
  fi
elif [[ ! -f "$APK" ]]; then
  echo "APK not found: $APK" >&2
  exit 1
fi

if ! apk_ok "$APK"; then
  echo "SHA-256 mismatch for $APK" >&2
  echo "Only WeType $WETYPE_VERSION ($WETYPE_APK_SHA256) is supported." >&2
  exit 1
fi

TMP="$(mktemp -d "${TMPDIR:-/tmp}/wetype-apk.XXXXXX")"
trap 'rm -rf "$TMP"' EXIT

unzip -q "$APK" 'lib/arm64-v8a/*' 'assets/config/beta/*' -d "$TMP"
[[ -f "$TMP/lib/arm64-v8a/libwxhld_jni.so" ]] || {
  echo "APK is missing lib/arm64-v8a/libwxhld_jni.so" >&2
  exit 1
}
[[ -f "$TMP/assets/config/beta/index.json" ]] || {
  echo "APK is missing assets/config/beta/index.json" >&2
  exit 1
}

mkdir -p "$DEST"
rm -rf "$DEST/lib" "$DEST/assets"
cp -a "$TMP/lib" "$TMP/assets" "$DEST/"
printf 'Prepared APK inputs at %s\n' "$DEST"
