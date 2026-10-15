# 候选窗主题（fcitx5 classicui）

这里的主题是可选资源。fcitx5 的候选窗由 `classicui` 插件渲染，主题是**全局**的，按目录名选用，
配置在 `~/.config/fcitx5/conf/classicui.conf` 的 `Theme`（浅色）和 `DarkTheme`（深色）。
安装本目录的主题**不会改动**你现有的主题，也不会替你选默认值——用哪个由你自己决定
（见「选用」）。

## 包含的主题

| 目录 | 说明 | 来源 | 许可 |
|---|---|---|---|
| `wechat-light` / `wechat-dark` | 仿微信亮色 / 深色 | [witt-bit/fcitx5-theme-wechat](https://github.com/witt-bit/fcitx5-theme-wechat) | Apache-2.0 |
| `ayaya-light` / `ayaya-dark` | 粉色系亮色 / 深色 | [witt-bit/fcitx5-theme-ayaya](https://github.com/witt-bit/fcitx5-theme-ayaya) | Apache-2.0 |
| `ayaya-dark-custom` | 在 `ayaya-dark` 基础上调整边距/图片/颜色 | 本项目（基于 ayaya） | Apache-2.0 |

> `wechat-light`、`ayaya-dark`、`ayaya-light`、`ayaya-dark-custom` 是从实际在用的主题原样收录，
> 以保证别的设备装出来和这里一致（包括本地微调过的 png/svg）。

## 安装位置

fcitx5 会在以下位置按主题名查找，安装到任意一个即可：

- 用户级：`~/.local/share/fcitx5/themes/<主题名>/`
- 系统级：`/usr/share/fcitx5/themes/<主题名>/`

用本项目的 `install` 会**用户级**安装（`--system` 时系统级），且**已存在的同名主题会跳过、不覆盖**。

## 选用

图形界面：`fcitx5-configtool` → 附加组件 → 经典界面 → 主题 / 深色主题。

命令行（会先备份 `classicui.conf`，只改这两个键）：

```sh
bash scripts/set-candidate-theme.sh list
bash scripts/set-candidate-theme.sh set --light wechat-light --dark ayaya-dark
```

## 添加自己的主题

1. 在 `themes/<你的主题名>/` 放 `theme.conf` 和它引用的图片（参考现有目录）；
2. `theme.conf` 的 `[Metadata] Name` 建议和目录名一致；
3. 重新 `install` 即可被复制到用户主题目录。

第三方主题请保留其原作者与许可证信息（见本目录 `LICENSE` / `NOTICE`）。
