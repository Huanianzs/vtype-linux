# GNOME Wayland 环境适配与输入法协议升级指南

本文档系统梳理了在 Ubuntu (22.04 / 24.04 / 26.04) GNOME 桌面与 Wayland 显示协议环境下，配置 Fcitx5 及微信拼音 (WeType) 的**协议演进、架构对比、避坑指南与核心配置说明**。

---

## 一、 架构对比：与历史方案（强制 XWayland）的本质区别

| 对比维度 | 历史方案（如旧版 `setup-gnome-wayland.sh`） | 当前现代方案（原生 Wayland + Kimpanel） |
| :--- | :--- | :--- |
| **底层核心哲学** | **全面妥协降级**：既然 Wayland 下候选框乱飘，就强行把所有应用都塞回旧时代 X11。 | **拥抱现代规范**：应用 100% 原生跑在 Wayland，由桌面顶层渲染解决输入面板。 |
| **通信协议** | **X11 / XCB 协议**（通过 XWayland 兼容层转发） | **Wayland `text-input-v3` 协议** + **Kimpanel D-Bus 顶层绘制协议** |
| **环境变量特征** | 强制注入：<br>`GDK_BACKEND=x11`<br>`QT_QPA_PLATFORM=xcb`<br>`ELECTRON_OZONE_PLATFORM_HINT=x11`<br>`MOZ_ENABLE_WAYLAND=0` | 原生放行：<br>`QT_QPA_PLATFORM=wayland;xcb`<br>`ELECTRON_OZONE_PLATFORM_HINT=auto`<br>【关键】`GTK_IM_MODULE` 留空注释！ |
| **高分屏缩放 (125%/150%)** | **严重模糊发虚**（X11 先渲染 100% 位图，再由系统双线性插值强制拉伸）。 | **真正矢量高清**（所有应用和字体原生按屏幕物理像素点直接渲染，字迹锐利如刀）。 |
| **桌面手势支持** | 丢失平滑手势（触控板三指/四指无缝滑动切屏退化为机械切换）。 | 完整保留 Wayland 原生丝滑触控手势。 |
| **系统兼容副作用** | 会触发 Desktop Icons NG 扩展的 "X11 while on Wayland" 警告。 | 无任何警告，系统处于 100% 官方推荐的标准运行状态。 |

---

## 二、 协议变迁与核心技术细节

### 1. 为什么以前 GNOME + Wayland 下第三方输入法会死在左上角？
* **协议死结**：Wayland 规范中专门负责浮动输入框定位的协议叫做 `zwp_input_panel_v1`。KDE Plasma、Sway、Hyprland 都完整支持该协议，因此 Fcitx5 浮动窗口在它们上面原生正常。
* **GNOME 的顽疾**：GNOME Mutter **公开坚决拒绝实现** `zwp_input_panel_v1`（官方主张第三方程序不应在桌面上乱画弹窗，必须由桌面环境自己画）。
* **后果**：Firefox 等原生 Wayland 程序就算把光标坐标发给了 Mutter，Mutter 也不转交给 Fcitx5。Fcitx5 自己的 `classicui` 窗口在 Mutter 面前没有锚点，只能默认贴在窗口原点 `(0, 0)`（左上角）。

### 2. 现代方案是如何彻底破解这个死结的？
* **破局关键：Kimpanel 顶层接管**：
  * 通过修复并启用 GNOME Shell 扩展 `kimpanel@kde.org`；
  * Fcitx5 负责算词，然后通过 D-Bus 接口将候选词发给 GNOME Shell；
  * **由 GNOME Shell 本身在输入光标旁绘制候选词小气泡**！
  * 因为 GNOME Shell 是桌面主宰，它天生知道每一个窗口内光标的绝对坐标，完全不需要 Mutter 的输入面板协议，彻底根治左上角漂移！

### 3. GNOME 50+ 扩展崩溃 Bug 修复细节
* **Bug 表现**：老版 Kimpanel 在现代 GJS（GNOME 45+ / 50+）下启动报：`TypeError: this.kimpanel.isLookupTableVertical is not a function`。
* **原因**：`InputPanel` 错误地继承了 `GObject.Object`，导致在 ES6 构造中普通对象参数被 GObject 构造器吞掉，`this.kimpanel` 为 `null`。
* **修复方法**：
  * 移除 `InputPanel` 冗余的 GObject 继承，改为纯 ES6 类：`export class InputPanel { constructor(params) { ... } }`；
  * 并在访问 `isLookupTableVertical()` 和 `getTextStyle()` 时增加方法存在性防御校验。

---

## 三、 当前系统生效的配置规范对照

### 1. 环境变量配置 (`~/.config/environment.d/00-ime.conf`)
```ini
# 核心总线
XMODIFIERS=@im=fcitx
SDL_IM_MODULE=fcitx

# 【核心禁忌】：绝不要硬设 GTK_IM_MODULE！
# 留空（注释），GTK3/GTK4 应用原生走 Wayland 的 text-input-v3 协议与 Mutter 通信
# GTK_IM_MODULE=

# Qt 应用使用 fcitx 插件并首选 Wayland 平台
QT_IM_MODULE=fcitx
QT_QPA_PLATFORM=wayland;xcb

# 浏览器与 Electron 类应用自动开启原生 Wayland
ELECTRON_OZONE_PLATFORM_HINT=auto
```

### 2. 软件生态与打包渠道清理（规避 Snap 隔离）
* **Snap 隔离问题**：Snap 的 AppArmor / cgroup 沙盒会切断应用与系统 Fcitx5 的 D-Bus 通信，造成无法唤醒输入法。
* **APT 原厂替换**：
  * **Firefox**：添加 Mozilla 官方直营 APT 源（`packages.mozilla.org`），配置 APT Pinning 规则（Priority 1000 vs -1），彻底阻断 Ubuntu 官方 Snap 空壳诱饵。
  * **VS Code**：添加 Microsoft 官方原厂 APT 源（`packages.microsoft.com`），安装原生 deb。
  * **Steam**：开启 `i386` 架构支持（`sudo dpkg --add-architecture i386`）后安装 `steam-installer` 原生包。
