"""识别终端窗口对应的长期存活进程。"""

from __future__ import annotations

import os
from typing import Dict, Optional


def process_identity(pid: int) -> Optional[str]:
    """PID 加创建时间用于 Windows 进程复用检测。"""
    if pid <= 0:
        return None
    if os.name != "nt":
        try:
            os.kill(pid, 0)
        except (OSError, ValueError):
            return None
        return str(pid)
    import ctypes
    from ctypes import wintypes

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel32.OpenProcess.restype = wintypes.HANDLE
    kernel32.GetProcessTimes.argtypes = [
        wintypes.HANDLE, ctypes.POINTER(wintypes.FILETIME),
        ctypes.POINTER(wintypes.FILETIME), ctypes.POINTER(wintypes.FILETIME),
        ctypes.POINTER(wintypes.FILETIME),
    ]
    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    handle = kernel32.OpenProcess(0x1000, False, pid)
    if not handle:
        return None
    created, exited, kernel, user = (wintypes.FILETIME() for _ in range(4))
    try:
        if not kernel32.GetProcessTimes(
            handle, ctypes.byref(created), ctypes.byref(exited),
            ctypes.byref(kernel), ctypes.byref(user),
        ):
            return None
        return f"{pid}:{created.dwHighDateTime}:{created.dwLowDateTime}"
    finally:
        kernel32.CloseHandle(handle)


def select_shell_pid(processes: Dict[int, tuple[int, str]], current: int) -> Optional[int]:
    """沿父进程链识别 shell，忽略 Python 启动器。"""
    shells = {"cmd.exe", "powershell.exe", "pwsh.exe", "bash.exe", "zsh.exe",
              "fish.exe", "sh.exe", "nu.exe"}
    selected = None
    visited = set()
    while current in processes and current not in visited:
        visited.add(current)
        parent, _ = processes[current]
        if parent not in processes:
            break
        if processes[parent][1].lower() in shells:
            selected = parent
        current = parent
    return selected


def select_console_shell(
    processes: Dict[int, tuple[int, str]], current: int, console_pids: set[int],
) -> Optional[int]:
    """优先使用同一控制台内的持久 shell，避免每次命令产生的 cmd.exe。"""
    parent_shell = select_shell_pid(processes, current)
    preferred = {"powershell.exe", "pwsh.exe", "bash.exe", "zsh.exe",
                 "fish.exe", "sh.exe", "nu.exe"}
    candidates = [
        pid for pid in console_pids
        if pid != current and pid in processes
        and processes[pid][1].lower() in preferred
        and process_identity(pid) is not None
    ]
    if parent_shell in candidates:
        return parent_shell
    if candidates:
        # 两次 CLI 调用选取同一控制台中最早创建的持久 shell。
        return min(candidates, key=lambda pid: tuple(
            int(part) for part in process_identity(pid).split(":")[1:]
        ))
    return parent_shell


def terminal_pid() -> Optional[int]:
    if os.name != "nt":
        return os.getppid()
    import ctypes
    from ctypes import wintypes

    class ProcessEntry(ctypes.Structure):
        _fields_ = [
            ("dwSize", wintypes.DWORD), ("cntUsage", wintypes.DWORD),
            ("th32ProcessID", wintypes.DWORD),
            ("th32DefaultHeapID", ctypes.c_void_p),
            ("th32ModuleID", wintypes.DWORD), ("cntThreads", wintypes.DWORD),
            ("th32ParentProcessID", wintypes.DWORD),
            ("pcPriClassBase", wintypes.LONG), ("dwFlags", wintypes.DWORD),
            ("szExeFile", wintypes.WCHAR * 260),
        ]

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.CreateToolhelp32Snapshot.argtypes = [wintypes.DWORD, wintypes.DWORD]
    kernel32.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
    kernel32.Process32FirstW.argtypes = [wintypes.HANDLE, ctypes.POINTER(ProcessEntry)]
    kernel32.Process32NextW.argtypes = [wintypes.HANDLE, ctypes.POINTER(ProcessEntry)]
    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    snapshot = kernel32.CreateToolhelp32Snapshot(0x2, 0)
    if not snapshot or snapshot == ctypes.c_void_p(-1).value:
        return None
    processes: Dict[int, tuple[int, str]] = {}
    entry = ProcessEntry()
    entry.dwSize = ctypes.sizeof(ProcessEntry)
    try:
        found = kernel32.Process32FirstW(snapshot, ctypes.byref(entry))
        while found:
            processes[entry.th32ProcessID] = (
                entry.th32ParentProcessID, entry.szExeFile,
            )
            found = kernel32.Process32NextW(snapshot, ctypes.byref(entry))
    finally:
        kernel32.CloseHandle(snapshot)

    kernel32.GetConsoleProcessList.argtypes = [
        ctypes.POINTER(wintypes.DWORD), wintypes.DWORD,
    ]
    kernel32.GetConsoleProcessList.restype = wintypes.DWORD
    size = 16
    console_pids: set[int] = set()
    for _ in range(3):
        buffer = (wintypes.DWORD * size)()
        count = kernel32.GetConsoleProcessList(buffer, size)
        if count <= size:
            console_pids = set(buffer[:count])
            break
        size = count
    return select_console_shell(processes, os.getpid(), console_pids)


def terminal_session_id() -> Optional[str]:
    """同一 Windows 控制台中的多次 CLI 调用共享此标识。"""
    if os.name != "nt":
        return None
    import ctypes
    from ctypes import wintypes

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.GetConsoleWindow.restype = wintypes.HWND
    window = kernel32.GetConsoleWindow()
    return str(window) if window else None
