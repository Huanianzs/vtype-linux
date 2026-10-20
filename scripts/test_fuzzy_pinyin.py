#!/usr/bin/env python3
"""测试模糊音引擎和配置界面；使用临时词库与私有 D-Bus 会话。"""

import argparse
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time


def test_engine(args):
    sys.path.insert(0, str(args.source / "scripts"))
    from test_bionic_daemon import Engine

    # 1. 默认无模糊音
    if "WETYPE_FUZZY" in os.environ:
        del os.environ["WETYPE_FUZZY"]

    with tempfile.TemporaryDirectory(prefix="vtype-fuzzy.") as directory:
        work = Path(directory) / "dict"
        (work / "userdict/v5").mkdir(parents=True)
        (work / "userdict/user_hot_word").mkdir(parents=True)
        with (Path(directory) / "engine.log").open("wb") as log:
            engine = Engine(args.engine_dir, work, False, None, log, harness=args.harness)
            try:
                engine.command("OPT spans", "OK")
                cands = [w[1] for w in engine.candidates("san")[:10]]
                assert "山" not in cands, f"默认不应有模糊音：san -> {cands}"
                engine.command("C", "OK")
                cands = [w[1] for w in engine.candidates("lan")[:10]]
                assert "男" not in cands, f"默认不应有模糊音：lan -> {cands}"
                print("PASS 默认不开启模糊音", flush=True)
            finally:
                engine.close()

    # 2. 开启 s_sh 与 n_l 模糊音
    os.environ["WETYPE_FUZZY"] = "s_sh,n_l"
    with tempfile.TemporaryDirectory(prefix="vtype-fuzzy.") as directory:
        work = Path(directory) / "dict"
        (work / "userdict/v5").mkdir(parents=True)
        (work / "userdict/user_hot_word").mkdir(parents=True)
        with (Path(directory) / "engine.log").open("wb") as log:
            engine = Engine(args.engine_dir, work, False, None, log, harness=args.harness)
            try:
                engine.command("OPT spans", "OK")
                cands = [w[1] for w in engine.candidates("san")[:10]]
                assert "山" in cands, f"开启 s_sh 模糊音未匹配出山：san -> {cands}"
                engine.command("C", "OK")
                cands = [w[1] for w in engine.candidates("lan")[:10]]
                assert "男" in cands, f"开启 n_l 模糊音未匹配出男：lan -> {cands}"
                print("PASS 字符串指定模糊音(s_sh,n_l)匹配正确", flush=True)
            finally:
                engine.close()

    # 3. 数字位掩码 (0x5 = z_zh | s_sh)
    os.environ["WETYPE_FUZZY"] = "5"
    with tempfile.TemporaryDirectory(prefix="vtype-fuzzy.") as directory:
        work = Path(directory) / "dict"
        (work / "userdict/v5").mkdir(parents=True)
        (work / "userdict/user_hot_word").mkdir(parents=True)
        with (Path(directory) / "engine.log").open("wb") as log:
            engine = Engine(args.engine_dir, work, False, None, log, harness=args.harness)
            try:
                engine.command("OPT spans", "OK")
                cands = [w[1] for w in engine.candidates("san")[:10]]
                assert "山" in cands, f"位掩码开启 s_sh 未匹配：san -> {cands}"
                engine.command("C", "OK")
                cands = [w[1] for w in engine.candidates("zong")[:10]]
                assert "中" in cands, f"位掩码开启 z_zh 未匹配：zong -> {cands}"
                print("PASS 数字位掩码模糊音匹配正确", flush=True)
            finally:
                engine.close()


def test_fcitx(args):
    import dbus
    from dbus.mainloop.glib import DBusGMainLoop

    DBusGMainLoop(set_as_default=True)

    with tempfile.TemporaryDirectory(prefix="vtype-fcitx-fuzzy.") as directory:
        root = Path(directory)
        config = root / "config/fcitx5"
        config.mkdir(parents=True)
        (config / "profile").write_text(
            "[Groups/0]\nName=Default\nDefault Layout=us\nDefaultIM=wetype-im\n"
            "[Groups/0/Items/0]\nName=keyboard-us\nLayout=\n"
            "[Groups/0/Items/1]\nName=wetype-im\nLayout=\n"
            "[GroupOrder]\n0=Default\n")
        os.environ.update(
            XDG_CONFIG_HOME=str(root / "config"), XDG_DATA_HOME=str(root / "data"),
            XDG_DATA_DIRS=str(args.addon_prefix / "share"),
            WETYPE_ENGINE_DIR=str(args.engine_dir), WETYPE_WORK_DIR=str(root / "dict"),
            WETYPE_HARNESS_LOG=str(root / "harness.log"),
            WETYPE_PAGETEST_LOG=str(root / "fcitx.log"))
        for key in ["DISPLAY", "WAYLAND_DISPLAY", "WETYPE_CLOUD_CONFIG", "WETYPE_FUZZY"]:
            os.environ.pop(key, None)
        (root / "dict/userdict/v5").mkdir(parents=True)
        (root / "dict/userdict/user_hot_word").mkdir(parents=True)
        registry = dbus.SessionBus()
        with (root / "fcitx.log").open("wb") as log:
            process = subprocess.Popen(
                ["fcitx5", "--disable=classicui,xim,waylandim,wayland,xcb"],
                stdout=log, stderr=subprocess.STDOUT)
            try:
                os.environ["WETYPE_E2E_FCITX_PID"] = str(process.pid)
                for _ in range(100):
                    if registry.name_has_owner("org.fcitx.Fcitx5"):
                        break
                    assert process.poll() is None, "私有 Fcitx 启动失败"
                    time.sleep(0.05)
                else:
                    raise AssertionError("私有 Fcitx D-Bus 未就绪")

                sys.path.insert(0, str(args.source / "fcitx5-wetype/e2e"))
                from dbus_test_client import Client, controller, pump

                client = Client("vtype-fuzzy-pinyin-test")
                client.focus()
                time.sleep(2)
                pump()
                url = "fcitx://config/addon/wetype"
                raw, description = controller.GetConfig(url)
                # 检查 19 项模糊音选项均已导出
                for opt in ["Fuzzy_Z_ZH", "Fuzzy_C_CH", "Fuzzy_S_SH", "Fuzzy_N_L",
                            "Fuzzy_H_F", "Fuzzy_R_L", "Fuzzy_G_K", "Fuzzy_AN_ANG",
                            "Fuzzy_EN_ENG", "Fuzzy_IN_ING", "Fuzzy_IAN_IANG",
                            "Fuzzy_UAN_UANG", "Fuzzy_ON_ONG", "Fuzzy_ENG_ONG",
                            "Fuzzy_UN_ONG", "Fuzzy_UN_IONG", "Fuzzy_AN_AI",
                            "Fuzzy_HUI_FEI", "Fuzzy_HUANG_WANG"]:
                    assert opt in raw, f"缺少模糊音配置项 {opt}"
                print("PASS 图形配置正确导出全部 19 项模糊音", flush=True)

                # 开启 Fuzzy_S_SH
                raw["Fuzzy_S_SH"] = dbus.String("True", variant_level=1)
                controller.SetConfig(url, raw)
                pump(2)
                current, _ = controller.GetConfig(url)
                assert str(current["Fuzzy_S_SH"]) == "True"

                client.type("san")
                cands = [text for _, text in client.candidates]
                assert any("山" in t for t in cands), f"开启模糊音后候选未包含'山': {cands}"
                print("PASS 动态开启模糊音 s=sh 后候选召回成功", flush=True)

            except BaseException:
                print("\n".join((root / "fcitx.log").read_text(errors="replace").splitlines()[-35:]))
                raise
            finally:
                process.terminate()
                try:
                    process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--harness", type=Path, help="已编译的 Android 宿主程序")
    parser.add_argument("--addon-prefix", type=Path, help="包含 share/fcitx5 的插件安装前缀")
    parser.add_argument("--engine-dir", type=Path,
                        default=Path.home() / ".local/lib/wetype-ime/arm64")
    parser.add_argument("--mode", choices=["engine", "fcitx", "private-fcitx"], default="engine")
    args = parser.parse_args()
    args.source = args.source.resolve()
    args.engine_dir = args.engine_dir.resolve()
    args.harness = (args.harness or args.source / "harness/jinterop").resolve()
    if args.addon_prefix:
        args.addon_prefix = args.addon_prefix.resolve()
    elif args.mode != "engine":
        parser.error("Fcitx 检查需要 --addon-prefix")
    if args.mode == "engine":
        test_engine(args)
    elif args.mode == "private-fcitx":
        assert os.environ.get("VTYPE_PRIVATE_DBUS") == "1", "请使用 --mode fcitx"
        test_fcitx(args)
    else:
        env = os.environ.copy()
        env["VTYPE_PRIVATE_DBUS"] = "1"
        subprocess.run(["dbus-run-session", "--", sys.executable, __file__,
                        "--source", str(args.source), "--harness", str(args.harness),
                        "--addon-prefix", str(args.addon_prefix),
                        "--engine-dir", str(args.engine_dir), "--mode", "private-fcitx"],
                       env=env, check=True)


if __name__ == "__main__":
    main()
