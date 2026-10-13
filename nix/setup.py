#!/usr/bin/env python3
"""准备用户引擎资源；APK 校验及二进制补丁复用上游脚本。"""
import argparse
import fcntl
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import uuid

ENGINE_LIBS = ('libandromeda.so', 'libcryptopp.so', 'libc++_shared.so',
               'libime_net.so', 'libowl.so', 'libprotobuf-lite.so',
               'libtensorflowlite_c.so', 'libwcwss.so', 'libwxhld.so',
               'libwxhld_jni.so', 'libwechatxlog.so')
REPLACED = {'lib', 'sysroot', 'wetype-harness', 'qemu-aarch64-static',
            'libwetype-cloud.so', 'cloud_proxy.py', 'cloud', 'wetype-cloud.py'}


def active_engine(engine):
    """只检查 daemon 的库/词库参数，不阻止其他用户或私有测试实例。"""
    for process in Path('/proc').glob('[0-9]*'):
        try:
            argv = (process / 'cmdline').read_bytes().split(b'\0')
            if b'--daemon' not in argv:
                continue
            for arg in argv:
                if arg.startswith(b'/') and Path(os.fsdecode(arg)).is_relative_to(engine):
                    return True
            env = (process / 'environ').read_bytes().split(b'\0')
            if any(item.startswith(b'LD_LIBRARY_PATH=' + os.fsencode(engine) + b'/') for item in env):
                return True
        except (OSError, ValueError):
            continue
    return False


def registrations(data_home):
    return [data_home / 'fcitx5/addon/wetype.conf',
            data_home / 'fcitx5/inputmethod/wetype-im.conf']


def prepare(package, engine, apk=None, migrate=False, data_home=None):
    package = package.resolve()
    if engine.is_symlink():
        raise RuntimeError('引擎目录不能是符号链接，请指定独立目录')
    engine = engine.parent.resolve() / engine.name
    data_home = data_home or Path(os.environ.get('XDG_DATA_HOME', Path.home() / '.local/share'))
    shadowing = [path for path in registrations(data_home) if path.exists() or path.is_symlink()]
    if shadowing and not migrate:
        raise RuntimeError('存在用户级旧插件注册；退出 Fcitx5 后加 --migrate-fcitx 备份并移开旧注册')
    for relative in ('libexec/wetype-harness', 'libexec/libandroid.so',
                     'libexec/libwetype-cloud.so', 'libexec/cloud_proxy.py',
                     'libexec/qemu-aarch64-static', 'libexec/sysroot/system/bin/linker64'):
        if not (package / relative).is_file():
            raise RuntimeError('Nix 包缺少 ' + relative)
    engine.parent.mkdir(parents=True, exist_ok=True)
    with (engine.parent / '.wetype-setup.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        if active_engine(engine):
            raise RuntimeError('该引擎仍在运行，请先退出 Fcitx5 和 wetype-demo，再执行初始化')
        with tempfile.TemporaryDirectory(prefix='.wetype-setup-', dir=engine.parent) as temp:
            root = Path(temp)
            inputs = root / 'apk'
            stage = root / 'runtime'
            scripts = package / 'share/vtype-linux/scripts'
            env = dict(os.environ, WETYPE_APK_ROOT=str(inputs))
            command = [sys.executable, str(scripts / 'fetch_apk.py')]
            if apk:
                command.append(str(apk.resolve()))
            subprocess.run(command, env=env, check=True)
            # 保留未知文件和更新过的预置词库；个人学习词库位于 XDG_DATA_HOME，不访问它。
            if engine.exists():
                shutil.copytree(engine, stage, symlinks=True,
                                ignore=lambda directory, names: REPLACED if Path(directory) == engine else [])
            else:
                stage.mkdir()
            libs = stage / 'lib'
            libs.mkdir()
            for name in ENGINE_LIBS:
                shutil.copy2(inputs / 'lib/arm64-v8a' / name, libs / name)
            for script in ('17_disable_scan_sig.py', '21_fake_appender.py'):
                subprocess.run([sys.executable, str(scripts / script), str(libs / 'libwxhld.so')], check=True)
            dicts = stage / 'dicts'
            if dicts.is_symlink():
                raise RuntimeError('预置词库目录不能是符号链接，请使用独立运行目录')
            dicts.mkdir(exist_ok=True)
            for source in (inputs / 'assets/config/beta').iterdir():
                target = dicts / source.name
                if not target.exists() and not target.is_symlink():
                    if source.is_dir():
                        shutil.copytree(source, target)
                    else:
                        shutil.copy2(source, target)
            (libs / 'libandroid.so').symlink_to(package / 'libexec/libandroid.so')
            for name in ('wetype-harness', 'qemu-aarch64-static', 'sysroot',
                         'libwetype-cloud.so', 'cloud_proxy.py'):
                (stage / name).symlink_to(package / 'libexec' / name)
            (stage / 'cloud').symlink_to(package / 'share/vtype-linux/cloud')
            (stage / 'wetype-cloud.py').symlink_to(package / 'share/vtype-linux/wetype-cloud.py')
            if active_engine(engine):
                raise RuntimeError('准备期间引擎已启动，请退出后重试')
            backup = engine.with_name(engine.name + '-backup.' + uuid.uuid4().hex[:8])
            if engine.exists():
                engine.rename(backup)
            registration_backup = None
            moved = []
            try:
                stage.rename(engine)
                if shadowing:
                    registration_backup = Path(tempfile.mkdtemp(prefix='wetype-backup.', dir=data_home / 'fcitx5'))
                    for path in shadowing:
                        target = registration_backup / (path.parent.name + '-' + path.name)
                        path.rename(target)
                        moved.append((path, target))
            except OSError:
                for path, target in reversed(moved):
                    target.rename(path)
                if engine.exists():
                    engine.rename(stage)
                if backup.exists():
                    backup.rename(engine)
                if registration_backup:
                    registration_backup.rmdir()
                raise
            if backup.exists():
                print('旧运行目录已备份：' + str(backup))
            if registration_backup:
                print('旧插件注册已备份：' + str(registration_backup))
    print('运行目录已准备：' + str(engine))
    print('将 Nix profile 的 share 加入 XDG_DATA_DIRS，启动 Fcitx5 后添加“微信拼音”。')
    print('wetype-check 可隔离验证引擎；云功能和剪贴板同步需单独启用。')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--package', type=Path, required=True)
    parser.add_argument('--engine-dir', type=Path,
                        default=Path(os.environ.get('WETYPE_ENGINE_DIR', Path.home() / '.local/lib/wetype-ime/arm64')))
    parser.add_argument('--apk', type=Path, help='使用本机 APK，仍校验固定 SHA-256')
    parser.add_argument('--migrate-fcitx', action='store_true', help='备份并移开遮蔽 Nix 包的用户级插件注册')
    args = parser.parse_args()
    prepare(args.package, args.engine_dir.expanduser(), args.apk, args.migrate_fcitx)


if __name__ == '__main__':
    try:
        main()
    except (OSError, RuntimeError, subprocess.CalledProcessError) as error:
        print('初始化未完成：' + str(error), file=sys.stderr)
        sys.exit(1)
