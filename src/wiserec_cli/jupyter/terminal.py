"""Terminal WebSocket 桥接；Ctrl+] 仅断开，远程关闭由显式命令完成。"""
from __future__ import annotations

import codecs
import json
import os
import shutil
import sys
import threading
from contextlib import contextmanager
from urllib.parse import quote

import websocket

from .connection import JupyterError


def require_tty():
    if not sys.stdin.isatty() or not sys.stdout.isatty():
        raise JupyterError("Terminal 交互需要真实终端，请在本机终端中运行")


@contextmanager
def raw_input():
    if os.name == "nt":
        import ctypes
        from ctypes import wintypes
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.GetStdHandle.restype = wintypes.HANDLE
        kernel32.GetStdHandle.argtypes = [wintypes.DWORD]
        kernel32.GetConsoleMode.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
        kernel32.SetConsoleMode.argtypes = [wintypes.HANDLE, wintypes.DWORD]
        handles = [kernel32.GetStdHandle(-10), kernel32.GetStdHandle(-11)]
        modes = [wintypes.DWORD(), wintypes.DWORD()]
        if not all(kernel32.GetConsoleMode(h, ctypes.byref(m)) for h, m in zip(handles, modes)):
            raise JupyterError("无法读取 Windows 控制台模式")
        try:
            # 关闭本地 Ctrl+C 处理、行缓冲和回显；开启 ANSI 输出。
            if not kernel32.SetConsoleMode(handles[0], modes[0].value & ~7):
                raise JupyterError("无法设置 Windows 终端输入模式")
            kernel32.SetConsoleMode(handles[1], modes[1].value | 4)
            yield
        finally:
            for handle, mode in zip(handles, modes):
                kernel32.SetConsoleMode(handle, mode.value)
        return
    import termios
    import tty
    fd = sys.stdin.fileno()
    previous = termios.tcgetattr(fd)
    try:
        tty.setraw(fd)
        yield
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, previous)


def read_input():
    if os.name == "nt":
        import msvcrt
        if not msvcrt.kbhit():
            return None
        value = msvcrt.getwch()
        if value in {"\x00", "\xe0"}:
            return {"H": "\x1b[A", "P": "\x1b[B", "M": "\x1b[C", "K": "\x1b[D",
                    "G": "\x1b[H", "O": "\x1b[F", "S": "\x1b[3~"}.get(msvcrt.getwch(), "")
        return value
    import select
    if select.select([sys.stdin], [], [], 0.05)[0]:
        return os.read(sys.stdin.fileno(), 4096)
    return None


def attach(client, name):
    require_tty()
    # quote 防止名称变成另一条 API 路径。
    socket = client.socket("terminals/websocket/" + quote(name, safe=""))
    socket.settimeout(0.2)
    stopped = threading.Event()
    errors = []

    def receive():
        try:
            while not stopped.is_set():
                try:
                    raw = socket.recv()
                except websocket.WebSocketTimeoutException:
                    continue
                if not raw:
                    break
                message = json.loads(raw)
                if message[0] == "stdout":
                    sys.stdout.write(message[1])
                    sys.stdout.flush()
                elif message[0] == "disconnect":
                    break
        except Exception:
            if not stopped.is_set():
                errors.append("终端连接中断；可用 terminal list 检查后重新 attach")
        finally:
            stopped.set()

    receiver = threading.Thread(target=receive, daemon=True)
    decoder = codecs.getincrementaldecoder("utf-8")("replace")
    previous_size = None
    try:
        with raw_input():
            receiver.start()
            while not stopped.is_set():
                size = shutil.get_terminal_size((80, 24))
                if size != previous_size:
                    socket.send(json.dumps(["set_size", size.lines, size.columns, 0, 0]))
                    previous_size = size
                chunk = read_input()
                if chunk is None:
                    stopped.wait(0.02)
                    continue
                if chunk == b"":
                    break
                value = decoder.decode(chunk) if isinstance(chunk, bytes) else chunk
                if "\x1d" in value:
                    before = value.split("\x1d", 1)[0]
                    if before:
                        socket.send(json.dumps(["stdin", before]))
                    break
                if value:
                    socket.send(json.dumps(["stdin", value]))
    finally:
        stopped.set()
        # 唤醒接收线程后再释放 socket；不能让 close() 与 recv() 并发读取关闭帧。
        try:
            socket.abort()
        except OSError:
            pass
        if receiver.ident is not None:
            receiver.join(timeout=1)
        socket.shutdown()
        sys.stdout.write("\r\n已结束本地连接；远程终端是否存续请用 terminal list 查看。\n")
    if errors:
        raise JupyterError(errors[0])
