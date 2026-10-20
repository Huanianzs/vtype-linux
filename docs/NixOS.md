# Nix / NixOS

提供 x86_64-linux 独立包，包含 Fcitx5 插件、ARM64 Android/bionic 宿主、
AOSP 运行库、Android 接口替身、云桥接库、QEMU 和 wxc 0.1.0。
Python、OpenSSL、Snappy 与客户端均使用包内固定路径。

Fcitx5 插件和 ARM64 宿主均从本仓库源码构建，宿主使用 nixpkgs 提供的 Android
NDK 29 工具链（API 28）。wxc 从固定的上游源码提交构建，依赖使用上游源码中的 `Cargo.lock`，
使用 nixpkgs 的 OpenSSL 和 Protobuf，不使用 npm 预编译包。
AOSP 运行库从 nixpkgs 提供的 Android 9 ARM64 系统镜像提取；编译器的 bionic
链接桩不能作为运行库使用。NDK 和系统镜像由 Nix 以固定哈希下载，构建阶段不运行
项目脚本去下载。

## 首次安装

系统需先启用 Fcitx5。安装包后，初始化命令从腾讯服务器下载微信输入法 3.5.4 APK，
校验固定 SHA-256，在用户机器上提取引擎和词库并应用上游引擎补丁：

```sh
nix profile install .#vtype-linux
wetype-setup
wetype-check
```

下载约 214 MB，后续可复用缓存；已有 APK 时执行 `wetype-setup --apk /path/to/wetype_3.5.4.apk`。
APK、腾讯引擎与词库不会进入 Nix 包；AOSP 运行库及本项目桥接库随包提供。
`nix run .#wetype-setup` 和 `nix run .#wetype-check` 也可直接使用。

默认运行目录为 `~/.local/lib/wetype-ime/arm64`，可用 `WETYPE_ENGINE_DIR` 或
`wetype-setup --engine-dir /path/to/runtime` 指定。使用自定义目录时，须将
`WETYPE_ENGINE_DIR` 同时传给 Fcitx5、`wetype-cloud` 和自检命令。

将 Nix profile 的 `share` 加入启动 Fcitx5 的 `XDG_DATA_DIRS`，通常为
`$HOME/.nix-profile/share`。插件以绝对库路径注册。启动或重启 Fcitx5，
在输入法设置中添加“微信拼音”，即可使用：

```sh
fcitx5-remote -s wetype-im
wetype-demo nihao
```

`wetype-check` 使用临时个人词库验证输入、选词、学习和重启；`wetype-demo` 使用
正常的用户词库。初始化不会启用云功能，也不会自动修改 Fcitx5 分组或重启输入法。

## 从旧 AppImage 或手动安装迁移

先退出 Fcitx5 和其他使用该引擎的命令，再执行：

```sh
wetype-setup --migrate-fcitx
wetype-check
```

该命令会重新准备与新版 bionic 宿主配套的引擎库，将旧运行目录保存在同级
`arm64-backup.*` 目录，并保留已有预置词库文件。用户级的 `wetype.conf` 与
`wetype-im.conf` 注册文件会移到 `XDG_DATA_HOME/fcitx5/wetype-backup.*`，
避免遮蔽 Nix 包的插件。备份不会自动删除。

APK 校验或补丁失败时保留原运行目录和注册文件。引擎仍在运行时拒绝替换。
个人学习词库位于 `XDG_DATA_HOME/wetype-ime/dict`，设备身份位于
`XDG_STATE_HOME/wetype-ime/account`；初始化不访问这两个目录。

更新 Nix 包后，再退出 Fcitx5 并运行 `wetype-setup`，刷新运行目录中的包资源链接。

## 云功能

包内已提供 wxc 0.1.0，无需 Node.js/npm。云功能需要用户关联官方客户端：

```sh
wetype-cloud pair
wetype-cloud enable --timer
wetype-cloud status
```

手机/电脑确认关联后，重启 Fcitx5。身份保存在用户私有目录；剪贴板互通需另外执行
`wetype-cloud clipboard enable`，并安装 Wayland 的 `wl-clipboard` 或 X11 的 `xclip`。
关联后的数据传输行为见 [README](../README.md) 和 [剪贴板互通](剪贴板互通.md)。

云代理、桥接库和协议脚本与本包配套。定时刷新服务使用当前 Python、包内协议脚本，
保留 OpenSSL/wxc 的 PATH、`WETYPE_SNAPPY_LIBRARY` 和 wxc 绝对路径。
剪贴板后台服务也保留 Snappy 路径。
可用 `WETYPE_WXC` 显式指定其他客户端。

`nix run .#wxc -- --version` 可单独检查客户端。QEMU 和 bionic 默认使用包内路径；
`QEMU_AARCH64` 和 `WETYPE_SYSROOT` 可用于显式覆盖。

## 开发与验证

```sh
nix develop
cmake -S fcitx5-wetype -B build -G Ninja
cmake --build build
ctest --test-dir build --output-on-failure
python3 -c 'import sys; print(sys.executable)'
python3 -m unittest discover -s tests -p 'test_*.py'
python3 tests/test_snapshot_transport.py
python3 scripts/check-public-source.py
python3 scripts/test_clipboard_desktop.py --backend x11
```

`nix develop` 提供编译、QEMU、Snappy 和界面测试所需的工具；CMake 会从
`PATH` 中查找 `python3`，需要固定解释器时可加
`-DWETYPE_PYTHON_EXECUTABLE="$(command -v python3)"`。

`nix build` 运行 CTest、离线 Python 测试、包内运行库闭包和命令入口检查。
真实引擎需要先执行初始化，可运行 `wetype-check --idle-seconds 85`。
空用户目录安装与私有 Fcitx 检查可在开发环境中运行：

```sh
python3 nix/check-install.py --package ./result --apk /path/to/wetype_3.5.4.apk
```

该检查覆盖重复初始化、数据保留、云桥接库加载、本地与关闭联网的云代理入口，
使用临时 HOME 和私有 D-Bus，不关联设备。
当前只声明 x86_64-linux；Ubuntu 的 AppImage 安装流程保持不变。
