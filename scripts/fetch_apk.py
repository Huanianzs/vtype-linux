#!/usr/bin/env python3
"""Fetch (or take) the pinned WeType APK and extract only the files this project uses.

只依赖 python3 标准库（urllib/hashlib/zipfile），安装机上不再需要 curl/unzip/sha256sum。
用法与 prepare_assets.sh 保持一致：fetch_apk.py [/path/to/apk]，环境变量
WETYPE_APK_ROOT（解包目标）、WETYPE_APK_CACHE（APK 缓存目录）。
"""
import hashlib
import os
import shutil
import sys
import tempfile
import time
import urllib.request
import zipfile

WETYPE_VERSION = "3.5.4"
WETYPE_APK_URL = "https://download.z.weixin.qq.com/app/android/%s/wxkb_1308_32.apk" % WETYPE_VERSION
WETYPE_APK_SHA256 = "7b57a5a9ab3aefd30413165f298213961bd201815ab48c6ad205c3b2950a90fb"
PREFIXES = ("lib/arm64-v8a/", "assets/config/beta/")
CHUNK = 1 << 20


def die(msg):
    print(msg, file=sys.stderr)
    sys.exit(1)


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(CHUNK), b""):
            h.update(block)
    return h.hexdigest()


def download(url, dest):
    # Unique, same-directory temporary file: concurrent installers cannot share it.
    part = None
    last_err = None
    for attempt in range(3):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "wetype-ime-linux-installer"})
            with tempfile.NamedTemporaryFile(dir=os.path.dirname(os.path.abspath(dest)),
                                             suffix=".part", delete=False) as out:
                part = out.name
            with urllib.request.urlopen(req, timeout=60) as resp, open(part, "wb") as out:
                try:
                    total = max(0, int(resp.headers.get("Content-Length") or 0))
                except ValueError:
                    total = 0
                done, last_report = 0, 0
                while True:
                    block = resp.read(CHUNK)
                    if not block:
                        break
                    out.write(block)
                    done += len(block)
                    if total and done - last_report >= 16 * CHUNK:
                        last_report = done
                        print("  %d / %d MB (%d%%)" % (done >> 20, total >> 20, done * 100 // total),
                              flush=True)
            if total and done != total:
                raise OSError("Incomplete download: %d / %d bytes" % (done, total))
            if sha256_file(part) != WETYPE_APK_SHA256:
                raise ValueError("SHA-256 mismatch for downloaded APK")
            os.replace(part, dest)
            return
        except Exception as e:  # noqa: BLE001 - 报错后重试，最后一次失败再抛
            last_err = e
            if attempt < 2:
                print("下载失败（%s），重试 %d/3…" % (e, attempt + 1), flush=True)
                time.sleep(2 * (attempt + 1))
        finally:
            if part is not None and os.path.exists(part):
                os.remove(part)
    die("Download failed: %s" % last_err)


def safe_extract(apk, dest):
    """只抽取 PREFIXES 下的成员；规范化路径防止 ZIP 路径逃逸；保留权限位。"""
    dest = os.path.realpath(dest)
    extracted = 0
    with zipfile.ZipFile(apk) as z:
        for zi in z.infolist():
            if zi.is_dir():
                continue
            if not zi.filename.startswith(PREFIXES):
                continue
            target = os.path.realpath(os.path.join(dest, zi.filename))
            if (".." in zi.filename.split("/")
                    or os.path.commonpath((dest, target)) != dest or target == dest):
                die("Unsafe zip member: %s" % zi.filename)
            os.makedirs(os.path.dirname(target), exist_ok=True)
            # Do not propagate setuid/setgid/sticky bits or interpret DOS attributes.
            mode = ((zi.external_attr >> 16) & 0o777 or 0o644) if zi.create_system == 3 else 0o644
            with z.open(zi) as src, open(target, "wb") as out:
                shutil.copyfileobj(src, out, CHUNK)
            os.chmod(target, mode)
            extracted += 1
    if not extracted:
        die("APK has no members under %s" % "/".join(PREFIXES))


def main():
    args = sys.argv[1:]
    base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    dest = os.environ.get("WETYPE_APK_ROOT") or os.path.join(base, ".deps", "wechat-ime")
    cache = os.environ.get("WETYPE_APK_CACHE") or os.path.join(
        os.environ.get("XDG_CACHE_HOME") or os.path.expanduser("~/.cache"), "wetype-ime")
    apk = args[0] if args else ""
    if len(args) > 1 or apk.startswith("-"):
        print("Usage: %s [/path/to/WeType-%s.apk]" % (sys.argv[0], WETYPE_VERSION), file=sys.stderr)
        sys.exit(2)

    if not apk:
        apk = os.path.join(cache, "wetype_%s.apk" % WETYPE_VERSION)
        if os.path.isfile(apk) and sha256_file(apk) == WETYPE_APK_SHA256:
            print("Using cached WeType %s APK: %s" % (WETYPE_VERSION, apk))
        else:
            os.makedirs(cache, exist_ok=True)
            print("Downloading WeType %s APK (214 MB) from %s" % (WETYPE_VERSION, WETYPE_APK_URL),
                  flush=True)
            download(WETYPE_APK_URL, apk)
    elif not os.path.isfile(apk):
        die("APK not found: %s" % apk)

    if sha256_file(apk) != WETYPE_APK_SHA256:
        die("SHA-256 mismatch for %s\nOnly WeType %s (%s) is supported."
            % (apk, WETYPE_VERSION, WETYPE_APK_SHA256))

    with tempfile.TemporaryDirectory(prefix="wetype-apk.") as tmp:
        safe_extract(apk, tmp)
        for sentinel in ("lib/arm64-v8a/libwxhld_jni.so", "assets/config/beta/index.json"):
            if not os.path.isfile(os.path.join(tmp, sentinel)):
                die("APK is missing %s" % sentinel)
        for sub in ("lib", "assets"):
            target = os.path.join(dest, sub)
            if os.path.islink(target) or os.path.isfile(target):
                os.unlink(target)
            elif os.path.isdir(target):
                shutil.rmtree(target)
            shutil.copytree(os.path.join(tmp, sub), target)
    print("Prepared APK inputs at %s" % dest)


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, zipfile.BadZipFile) as exc:
        die(str(exc))
    except KeyboardInterrupt:
        sys.exit(130)
