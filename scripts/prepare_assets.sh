#!/usr/bin/env bash
# Fetch (or take) the pinned WeType APK and extract only the files this project uses.
# The binary patches target one exact build, so every APK is checked against its SHA-256.
# 实际工作在 fetch_apk.py（纯 python3 标准库），安装机无需 curl/unzip/sha256sum。
set -euo pipefail

WETYPE_VERSION=3.5.4

BASE="$(cd "$(dirname "$0")/.." && pwd)"
APK="${1:-}"

if [[ $# -gt 1 || "$APK" == -* ]]; then
  echo "Usage: $0 [/path/to/WeType-$WETYPE_VERSION.apk]" >&2
  echo "Without an APK, WeType $WETYPE_VERSION is downloaded from Tencent's official server." >&2
  exit 2
fi

command -v python3 >/dev/null || { echo "Missing dependency: python3" >&2; exit 1; }

exec python3 "$BASE/scripts/fetch_apk.py" ${APK:+"$APK"}
