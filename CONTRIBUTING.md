# 参与贡献

欢迎各种形式的帮助：报告你的环境能不能用、提体验上的问题、修 bug、适配新版官方 APK。

## 报告问题

[开 issue](https://github.com/zhl-HFUT/vtype-linux/issues/new/choose) 时选对应模板，写清楚：

- 发行版、桌面环境、X11 还是 Wayland、Fcitx5 版本、CPU 架构
- 在哪个应用里、怎么操作、期望什么、实际发生了什么

用 agent 的话，让它按 [AGENTS.md](AGENTS.md) 的“报告问题”一节收集信息。

**不要**上传 `~/.local/state/wetype-ime/account`（设备身份）、个人词库，或未经检查的 `harness.log`（可能含你打过的字）。

## 提交代码

1. Fork 后新建分支，改动尽量小而集中，一个 PR 做一件事。
2. 跑通 [AGENTS.md](AGENTS.md#构建和测试) 里的构建和测试，和 CI 一致。
3. 涉及按键、候选、同步的改动，请在真实桌面上试过，并在 PR 里写明环境和验证方法。
4. 功能或按键变了，同步更新 README 和 `docs/安装与使用.md`。
5. 文档、注释、提交信息用中文。

改动代理放行规则（`cloud/实时云桥接.py`）或任何会向官方服务器发送新数据的功能，请先开 issue 讨论。

## 适配新版官方 APK

这是最需要人手的事。步骤和需要核对的文件见 [AGENTS.md 的“升级官方版本”](AGENTS.md#升级官方版本)。可以先开一个 issue 认领，避免重复劳动。
