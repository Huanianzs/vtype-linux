# Nix / NixOS

提供 x86_64-linux 独立包，构建 Fcitx5 插件、Android/bionic 宿主并固定静态 QEMU、
Python、OpenSSL、Node.js 与 Snappy 的运行路径。

## 安装

```sh
nix build
nix profile install .#vtype-linux
```

腾讯引擎库、词库和 AOSP 系统运行库仍需按[安装与使用](安装与使用.md)准备在
`~/.local/lib/wetype-ime/arm64`；本包不会下载或打包腾讯 APK，不保存设备身份。
已准备好的运行时可以直接复用。首次准备运行时的 Nix 自动化仍待补齐。

将本包的 `share` 目录加入启动 Fcitx5 的 `XDG_DATA_DIRS`，例如独立 profile 安装后
加入 `$HOME/.nix-profile/share`。插件注册使用绝对库路径。Fcitx5 设置里添加“微信拼音”
并重启后可切换使用。若以前通过 AppImage 安装过插件，请先备份并停用它的用户级
注册文件，避免 `XDG_DATA_HOME/fcitx5` 中的旧注册覆盖本包。

```sh
fcitx5-remote -s wetype-im
wetype-demo nihao
```

宿主程序由 Nix 包提供，无需覆盖用户运行时中的旧宿主。引擎库、词库位置通过
`WETYPE_ENGINE_DIR` 指定，默认使用上述用户目录；个人词库位置保持上游默认值。

## 云功能

先准备 wxc（包内提供 Node.js 22；在 `nix develop` 中也可使用 npm）：

```sh
nix develop
npm install --prefix "$HOME/.local/share/wetype-ime/tools" @mkdir700/wxc@0.1.0
wetype-cloud pair
wetype-cloud enable --timer
wetype-cloud status
```

手机/电脑确认关联后，重启 Fcitx5。身份保存在用户私有目录，剪贴板仍需单独启用。
定时任务使用当前 Python 解释器与协议脚本，保留 OpenSSL/Node.js 的 PATH 和
`WETYPE_SNAPPY_LIBRARY`，不依赖 `/usr/bin/python3`。

## 开发与验证

```sh
nix develop
cmake -S fcitx5-wetype -B build
cmake --build build
ctest --test-dir build --output-on-failure
python3 -m unittest discover -s tests -p 'test_*.py'
python3 tests/test_snapshot_transport.py
```

`nix build` 同样运行 CTest 和不联网的 Python 检查。真实引擎自检可指定本包宿主：

```sh
python3 scripts/test_bionic_daemon.py --engine-dir ~/.local/lib/wetype-ime/arm64 \
  --harness ~/.nix-profile/libexec/wetype-harness
```

当前包只声明 x86_64-linux。Ubuntu 安装方式保持原有流程；共享 Snappy 加载代码
在未指定环境变量时继续查找系统库，缺失时返回明确错误。
