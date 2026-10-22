"""Per-user instance ownership; no credentials in command lines."""
import ctypes
import os
from pathlib import Path
import socket
import time


class Instance:
    def __init__(self, directory):
        self.directory = Path(directory)
        self.handle = None
        self.file = None

    def acquire(self):
        self.directory.mkdir(parents=True, exist_ok=True)
        if os.name == 'nt':
            import hashlib
            name = 'Local\\PermissionNotifier-' + hashlib.sha256(str(self.directory).encode()).hexdigest()[:24]
            kernel = ctypes.WinDLL('kernel32', use_last_error=True)
            kernel.CreateMutexW.argtypes = [ctypes.c_void_p, ctypes.c_bool, ctypes.c_wchar_p]
            kernel.CreateMutexW.restype = ctypes.c_void_p
            self.handle = kernel.CreateMutexW(None, False, name)
            if not self.handle:
                raise OSError('无法创建单实例互斥量')
            return ctypes.get_last_error() != 183
        import fcntl
        self.file = (self.directory / 'instance.lock').open('a')
        try:
            fcntl.flock(self.file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            return True
        except BlockingIOError:
            return False

    def close(self):
        if self.handle:
            kernel = ctypes.WinDLL('kernel32', use_last_error=True)
            kernel.CloseHandle.argtypes = [ctypes.c_void_p]
            kernel.CloseHandle(self.handle)
            self.handle = None
        if self.file:
            self.file.close()


def wait_ready(server, timeout=10):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        if server.started:
            return True
        time.sleep(.05)
    return False


def private_directory(directory):
    directory.mkdir(parents=True, exist_ok=True)
    if os.name != 'nt':
        os.chmod(directory, 0o700)


def ensure_port_free(port):
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', port))
