"""只访问 CLIPBOARD 纯文本；X11 用 xclip，Wayland 用 wl-clipboard。"""
import os
import selectors
import shutil
import subprocess
import time
from 剪贴板协议 import MAX_RECEIVE_TEXT_BYTES


class ClipboardChanged(RuntimeError):
    pass


class DesktopClipboard:
    def __init__(self, backend='auto', env=None):
        self.env = dict(os.environ if env is None else env)
        if backend == 'auto':
            backend = 'wayland' if self.env.get('WAYLAND_DISPLAY') else 'x11'
        if backend not in ('x11', 'wayland'):
            raise ValueError('剪贴板后端必须为 auto、x11 或 wayland')
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
