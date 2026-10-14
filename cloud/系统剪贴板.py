"""只访问 CLIPBOARD 纯文本；X11 用 xclip，Wayland 用 wl-clipboard。"""
import os
import selectors
import shutil
import socket
import struct
import subprocess
import time
from 剪贴板协议 import MAX_RECEIVE_TEXT_BYTES


class ClipboardChanged(RuntimeError):
    pass


def wayland_background_clipboard(env):
    """只查询注册表，不绑定剪贴板或创建窗口；探测失败时按不支持处理。"""
    display = env.get('WAYLAND_DISPLAY')
    if not display:
        return False
    if not os.path.isabs(display):
        runtime = env.get('XDG_RUNTIME_DIR')
        if not runtime:
            return False
        display = os.path.join(runtime, display)
    deadline = time.monotonic() + 2
    interfaces = {}

    def receive(connection, length):
        data = bytearray()
        while len(data) < length:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError
            connection.settimeout(remaining)
            chunk = connection.recv(length - len(data))
            if not chunk:
                raise EOFError
            data.extend(chunk)
        return data

    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as connection:
            connection.settimeout(2)
            connection.connect(display)
            connection.settimeout(max(.01, deadline - time.monotonic()))
            # Wayland 使用本机字节序。仅发送 wl_display.get_registry 和 sync。
            # 新对象 2 是注册表，3 是标记初始公告结束的回调。
            connection.sendall(struct.pack('=IIIIII', 1, (12 << 16) | 1, 2, 1, 12 << 16, 3))
            total = 0
            while total < 256 * 1024:
                object_id, header = struct.unpack('=II', receive(connection, 8))
                size, opcode = header >> 16, header & 0xffff
                if size < 8 or size % 4:
                    return False
                body = receive(connection, size - 8)
                total += size
                if object_id == 1 and opcode == 0:  # wl_display.error
                    return False
                if object_id == 3 and opcode == 0 and len(body) == 4:
                    # 当前支持的 wl-clipboard 2.x 使用 wlr 数据控制协议。
                    return 'zwlr_data_control_manager_v1' in interfaces.values()
                if object_id == 2 and opcode == 0 and len(body) >= 12:
                    length = struct.unpack_from('=I', body, 4)[0]
                    if not length or 8 + ((length + 3) & ~3) + 4 != len(body) or body[8 + length - 1] != 0:
                        return False
                    name = struct.unpack_from('=I', body)[0]
                    version = struct.unpack_from('=I', body, len(body) - 4)[0]
                    if version:
                        interfaces[name] = bytes(body[8:8 + length - 1]).decode('ascii')
                elif object_id == 2 and opcode == 1 and len(body) == 4:
                    interfaces.pop(struct.unpack('=I', body)[0], None)
    except (OSError, EOFError, UnicodeError):
        return False
    return False


class DesktopClipboard:
    def __init__(self, backend='auto', env=None):
        self.env = dict(os.environ if env is None else env)
        if backend not in ('auto', 'x11', 'wayland'):
            raise ValueError('剪贴板后端必须为 auto、x11 或 wayland')
        automatic = backend == 'auto'
        background = (wayland_background_clipboard(self.env)
                      if backend != 'x11' and self.env.get('WAYLAND_DISPLAY') else False)
        if automatic:
            backend = 'wayland' if background else 'x11'
        if self.env.get('WAYLAND_DISPLAY') and not background and backend == 'wayland':
            raise RuntimeError('当前 Wayland 桌面不支持后台剪贴板；请安装 xclip 并使用 --backend x11 或 auto（需要 XWayland）')
        if automatic and self.env.get('WAYLAND_DISPLAY') and backend == 'x11' and not self.env.get('DISPLAY'):
            raise RuntimeError('当前 Wayland 桌面不支持后台剪贴板，且未启用 XWayland；无法启用剪贴板同步')
        self.backend = backend
        display = 'WAYLAND_DISPLAY' if backend == 'wayland' else 'DISPLAY'
        if not self.env.get(display):
            raise RuntimeError('请在图形桌面的终端中启用剪贴板同步')
        required = ('wl-copy', 'wl-paste') if backend == 'wayland' else ('xclip',)
        self.tools = {}
        for name in required:
            tool = shutil.which(name, path=self.env.get('PATH'))
            if not tool:
                raise RuntimeError('缺少剪贴板工具：' + name)
            self.tools[name] = tool

    def capture(self, command, limit, allow_empty=False):
        proc = subprocess.Popen(command, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE, env=self.env)
        output = bytearray()
        errors = bytearray()
        deadline = time.monotonic() + 2
        selector = selectors.DefaultSelector()
        selector.register(proc.stdout, selectors.EVENT_READ, 'output')
        selector.register(proc.stderr, selectors.EVENT_READ, 'errors')
        try:
            while selector.get_map():
                remaining = deadline - time.monotonic()
                events = selector.select(max(0, remaining))
                if remaining <= 0 or not events:
                    raise TimeoutError('系统剪贴板读取超时')
                for key, _ in events:
                    target = output if key.data == 'output' else errors
                    cap = limit if key.data == 'output' else 4096
                    data = os.read(key.fileobj.fileno(), min(16384, cap + 1 - len(target)))
                    if not data:
                        selector.unregister(key.fileobj)
                        continue
                    target.extend(data)
                    if len(target) > cap:
                        if key.data == 'output':
                            return None
                        raise RuntimeError('系统剪贴板工具异常')
            if proc.wait(timeout=max(.01, deadline - time.monotonic())) != 0:
                if allow_empty and (b'target TARGETS not available' in errors
                                    or errors.strip() in (b'No selection', b'Nothing is copied')):
                    return None
                raise RuntimeError('系统剪贴板读取失败')
            return bytes(output)
        finally:
            selector.close()
            if proc.poll() is None:
                proc.kill()
                proc.wait()
            proc.stdout.close()
            proc.stderr.close()

    def read(self):
        if self.backend == 'wayland':
            paste = self.tools['wl-paste']
            offered = self.capture([paste, '--list-types'], 16384, allow_empty=True)
            if offered is None:
                return None
            types = offered.decode('ascii', errors='ignore').splitlines()
            candidates = ['text/plain;charset=utf-8', 'text/plain;charset=UTF-8', 'text/plain']
            target = next((kind for kind in candidates if kind in types), None)
            command = [paste, '--no-newline', '--type', target] if target else None
        else:
            paste = [self.tools['xclip'], '-selection', 'clipboard', '-out']
            offered = self.capture(paste + ['-target', 'TARGETS'], 16384, allow_empty=True)
            if offered is None:
                return None
            types = offered.decode('ascii', errors='ignore').splitlines()
            target = next((kind for kind in ('UTF8_STRING', 'text/plain;charset=utf-8', 'text/plain', 'STRING') if kind in types), None)
            command = paste + ['-target', target] if target else None
        if not command or 'text/uri-list' in types or any(kind.startswith('image/') for kind in types):
            return None
        data = self.capture(command, MAX_RECEIVE_TEXT_BYTES)
        if data is None:
            return None
        try:
            text = data.decode('utf-8')
        except UnicodeError:
            return None
        return text if '\0' not in text else None

    def write(self, text, expected):
        if self.read() != expected:
            raise ClipboardChanged('本地剪贴板已变化，本轮不覆盖')
        if self.backend == 'wayland':
            command = [self.tools['wl-copy'], '--type', 'text/plain;charset=utf-8']
        else:
            command = [self.tools['xclip'], '-selection', 'clipboard', '-in', '-target', 'UTF8_STRING']
        # 工具后台持有复制内容；正文只经 stdin，不出现在进程参数和日志中。
        subprocess.run(command, input=text.encode(), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                       env=self.env, timeout=2, check=True)
        # xclip 先 fork 再接管选区，命令返回时新内容可能尚未生效。
        deadline = time.monotonic() + 1
        while self.read() != text:
            if time.monotonic() > deadline:
                raise RuntimeError('系统剪贴板未确认写入')
            time.sleep(.05)
