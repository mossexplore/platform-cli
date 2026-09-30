"""与终端会话绑定的后台认证保活。"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import time
from contextlib import contextmanager
from datetime import datetime
from http.cookies import SimpleCookie
from pathlib import Path
from typing import Any, Dict, Optional
from uuid import uuid4

import httpx

from .business import BusinessStore
from .config import ConfigManager
from .credentials import CredentialStore
from .errors import AuthenticationError, BusinessError
from .models import BEIJING_TIMEZONE, Credentials


def _process_identity(pid: int) -> Optional[str]:
    """返回进程创建标识；Windows 同时核对创建时间以防 PID 重用。"""
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
    handle = kernel32.OpenProcess(0x1000, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION
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


def _select_shell_pid(processes: Dict[int, tuple[int, str]], current: int) -> Optional[int]:
    """越过 PowerShell 调用批处理时产生的临时 cmd.exe。"""
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


def _terminal_pid() -> Optional[int]:
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
    snapshot = kernel32.CreateToolhelp32Snapshot(0x2, 0)  # TH32CS_SNAPPROCESS
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
    return _select_shell_pid(processes, os.getpid())


class PingStore:
    def __init__(self, path: Path):
        self.path = path

    @contextmanager
    def locked(self):
        lock_path = self.path.with_name(f".{self.path.name}.lock")
        lock_path.parent.mkdir(parents=True, exist_ok=True)
        with lock_path.open("a+b") as lock:
            if os.name == "nt":
                import msvcrt
                if lock.seek(0, os.SEEK_END) == 0:
                    lock.write(b"0")
                    lock.flush()
                lock.seek(0)
                msvcrt.locking(lock.fileno(), msvcrt.LK_LOCK, 1)
            else:
                import fcntl
                fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
            try:
                yield
            finally:
                if os.name == "nt":
                    lock.seek(0)
                    msvcrt.locking(lock.fileno(), msvcrt.LK_UNLCK, 1)
                else:
                    fcntl.flock(lock.fileno(), fcntl.LOCK_UN)

    def read(self) -> Dict[str, Any]:
        try:
            value = json.loads(self.path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return {"profiles": {}}
        if not isinstance(value, dict) or not isinstance(value.get("profiles"), dict):
            raise ValueError("自动保活状态文件格式错误")
        return value

    def write(self, value: Dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(
                "w", encoding="utf-8", dir=self.path.parent,
                prefix=f".{self.path.name}.", suffix=".tmp", delete=False,
            ) as file:
                temporary = Path(file.name)
                json.dump(value, file, ensure_ascii=False, indent=2)
                file.write("\n")
            try:
                os.chmod(temporary, 0o600)
            except OSError:
                pass
            temporary.replace(self.path)
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)


def _state_path(credentials: CredentialStore) -> Path:
    return credentials.path.with_name("ping.json")


def _valid_owners(entry: Dict[str, Any]) -> list[Dict[str, Any]]:
    return [
        owner for owner in entry.get("owners", [])
        if isinstance(owner, dict)
        and _process_identity(owner.get("pid", 0)) == owner.get("identity")
    ]


def start(runtime: Any, *, automatic: bool = False) -> str:
    """登记当前终端并确保当前环境只有一个后台进程。"""
    if not runtime.config.auto_ping:
        return "自动保活已在配置中关闭"
    if not sys.stdin.isatty():
        return "当前不是交互式终端，未启动自动保活"
    profile = runtime.config.current_name
    credentials = runtime.credentials.load(profile)
    if credentials is None or credentials.is_expired():
        return "当前环境没有有效的本地登录信息，未启动自动保活"
    try:
        runtime.business.require_selection(profile, credentials.username)
    except BusinessError:
        return "尚未选择业务，选择后将启动自动保活"
    owner_pid = _terminal_pid()
    if owner_pid is None:
        return "无法识别当前终端窗口，未启动自动保活"
    owner_identity = _process_identity(owner_pid)
    if owner_identity is None:
        return "无法识别当前终端进程，未启动自动保活"
    store = PingStore(_state_path(runtime.credentials))
    with store.locked():
        data = store.read()
        entry = data["profiles"].setdefault(profile, {})
        if automatic and entry.get("manual_stop"):
            return "当前环境的自动保活已手动停止，运行 ml auth ping start 可恢复"
        entry["manual_stop"] = False
        endpoint = runtime.config.current_profile().api_endpoint
        if entry.get("api_endpoint") not in (None, endpoint):
            entry.clear()
        entry["api_endpoint"] = endpoint
        owners = _valid_owners(entry)
        if not any(owner["identity"] == owner_identity for owner in owners):
            owners.append({"pid": owner_pid, "identity": owner_identity})
        entry["owners"] = owners
        worker_pid = entry.get("worker_pid")
        if (not isinstance(worker_pid, int)
                or _process_identity(worker_pid) != entry.get("worker_identity")):
            creation_flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
            process = subprocess.Popen(
                [sys.executable, "-m", "wiserec_cli.ping_worker",
                 str(runtime.config.path), profile, str(runtime.credentials.path),
                 str(runtime.business.path), str(store.path)],
                stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL, close_fds=True,
                creationflags=creation_flags,
                start_new_session=os.name != "nt",
            )
            entry.update(worker_pid=process.pid,
                         worker_identity=_process_identity(process.pid), status="starting",
                         last_error="", last_success=time.time(),
                         last_confirmed=None, last_attempt=None, last_request_id=None,
                         success_count=0, failure_count=0)
        else:
            entry["status"] = "running"
        store.write(data)
    return f"自动保活已启动（环境 {profile}，间隔 {runtime.config.ping_interval_minutes} 分钟）"


def auto_start(runtime: Any, *, after_login: bool = False) -> str:
    """后台保活失败不应撤销已经成功的登录或业务切换。"""
    try:
        return start(runtime, automatic=not after_login)
    except Exception as exc:
        return f"警告：自动保活启动失败：{exc}"


def stop(runtime: Any, *, all_profiles: bool = False) -> None:
    store = PingStore(_state_path(runtime.credentials))
    with store.locked():
        data = store.read()
        profiles = data["profiles"] if all_profiles else {
            runtime.config.current_name: data["profiles"].get(runtime.config.current_name)
        }
        for entry in profiles.values():
            if isinstance(entry, dict):
                entry["owners"] = []
                entry["status"] = "stopping"
                entry["manual_stop"] = True
        store.write(data)


def detach(runtime: Any, profile: str) -> None:
    """当前终端切换环境时解除旧环境登记。"""
    owner_pid = _terminal_pid()
    identity = _process_identity(owner_pid) if owner_pid is not None else None
    if identity is None:
        return
    store = PingStore(_state_path(runtime.credentials))
    with store.locked():
        data = store.read()
        entry = data["profiles"].get(profile)
        if isinstance(entry, dict):
            entry["owners"] = [owner for owner in _valid_owners(entry)
                               if owner["identity"] != identity]
            store.write(data)


def status(runtime: Any) -> Dict[str, Any]:
    profile = runtime.config.current_name
    store = PingStore(_state_path(runtime.credentials))
    with store.locked():
        entry = store.read()["profiles"].get(profile, {})
    worker_pid = entry.get("worker_pid")
    running = (isinstance(worker_pid, int)
               and _process_identity(worker_pid) == entry.get("worker_identity"))
    owners = _valid_owners(entry)

    def displayed(value: Any) -> str:
        return (datetime.fromtimestamp(value, BEIJING_TIMEZONE)
                .strftime("%Y-%m-%d %H:%M:%S") if isinstance(value, (int, float)) else "-")

    return {
        "环境": profile,
        "自动保活": "启用" if runtime.config.auto_ping else "关闭",
        "状态": entry.get("status", "未启动") if running else "未运行",
        "进程 ID": worker_pid if running else "-",
        "终端窗口数": len(owners),
        "间隔（分钟）": runtime.config.ping_interval_minutes,
        "上次请求": displayed(entry.get("last_attempt")),
        "上次平台确认成功": displayed(entry.get("last_confirmed")),
        "下次预计请求": displayed(
            entry["last_success"] + runtime.config.ping_interval_minutes * 60
            if running and isinstance(entry.get("last_success"), (int, float)) else None
        ),
        "上次请求 ID": entry.get("last_request_id") or "-",
        "成功次数": entry.get("success_count", 0),
        "失败次数": entry.get("failure_count", 0),
        "最近错误": entry.get("last_error") or "-",
    }


def mark_platform_activity(credentials: CredentialStore, profile: str) -> None:
    store = PingStore(_state_path(credentials))
    with store.locked():
        data = store.read()
        entry = data["profiles"].get(profile)
        if isinstance(entry, dict) and entry.get("status") != "stopping":
            entry["last_success"] = time.time()
            store.write(data)


def _updated_cookie(old: str, response: httpx.Response) -> str:
    old_cookies = SimpleCookie()
    old_cookies.load(old)
    for header in response.headers.get_list("set-cookie"):
        changes = SimpleCookie()
        changes.load(header)
        for name, morsel in changes.items():
            if morsel["max-age"] == "0" or morsel.value == "":
                old_cookies.pop(name, None)
            else:
                old_cookies[name] = morsel.value
    return "; ".join(f"{name}={item.value}" for name, item in old_cookies.items())


def _probe(config: ConfigManager, profile_name: str, credentials: Credentials,
           business_id: str, request_id: str) -> tuple[str, str]:
    profile = next(item for item in config.profiles() if item.name == profile_name)
    with httpx.Client(base_url=profile.base_url,
                      timeout=config.timeout_ms / 1000,
                      verify=config.verify_ssl_for(profile),
                      follow_redirects=False) as client:
        response = client.get("/ai/user/info", headers={
            "cookie": credentials.cookie, "csrftoken": credentials.csrftoken,
            "businessid": business_id, "ai-businessId": business_id,
            "referer": profile.api_endpoint, "X-Request-ID": request_id,
        })
    if response.status_code in {401, 403, 419, 440} or 300 <= response.status_code < 400:
        raise AuthenticationError("平台会话已失效")
    response.raise_for_status()
    payload = response.json()
    result = payload.get("result") if isinstance(payload, dict) else None
    if isinstance(result, dict) and result.get("code") in {
        401, 403, 419, 440, "UNAUTHORIZED", "SESSION_EXPIRED",
    }:
        raise AuthenticationError("平台会话已失效")
    if (not isinstance(result, dict) or type(result.get("code")) is not int
            or result["code"] != 0
            or result.get("username") != credentials.username):
        raise ValueError("平台未确认当前账号的会话有效")
    updated_cookie = _updated_cookie(credentials.cookie, response)
    cookie_values = SimpleCookie()
    cookie_values.load(updated_cookie)
    csrf = (response.headers.get("csrftoken") or response.headers.get("x-csrftoken")
            or (cookie_values["csrftoken"].value if "csrftoken" in cookie_values else None)
            or credentials.csrftoken)
    return updated_cookie, csrf


def run_worker(config_path: Path, profile: str, credentials_path: Path,
               business_path: Path, state_path: Path) -> None:
    store = PingStore(state_path)
    credentials_store = CredentialStore(credentials_path)
    business_store = BusinessStore(business_path)
    failure_delay = 0
    while True:
        with store.locked():
            data = store.read()
            entry = data["profiles"].get(profile)
            if not isinstance(entry, dict) or entry.get("worker_pid") != os.getpid():
                return
            owners = _valid_owners(entry)
            entry["owners"] = owners
            if not owners or entry.get("status") == "stopping":
                entry.update(status="stopped", worker_pid=None, worker_identity=None)
                store.write(data)
                return
            store.write(data)
        try:
            config = ConfigManager(config_path)
            if not config.auto_ping:
                stop_data = "配置已关闭自动保活"
                break
            credentials = credentials_store.load(profile)
            if credentials is None:
                stop_data = "登录信息已清除"
                break
            selection = business_store.require_selection(profile, credentials.username)
            now = time.time()
            if now < entry.get("last_success", 0) + config.ping_interval_minutes * 60:
                time.sleep(5)
                continue
            if failure_delay and now < entry.get("last_attempt", 0) + failure_delay:
                time.sleep(5)
                continue
            request_id = str(uuid4())
            with store.locked():
                current_data = store.read()
                current = current_data["profiles"].get(profile, {})
                current.update(last_attempt=now, last_request_id=request_id,
                               status="requesting")
                store.write(current_data)
            new_cookie, new_csrf = _probe(
                config, profile, credentials, selection.business_id, request_id,
            )
            credentials_store.extend_if_current(
                credentials, config.auth_ttl_seconds, new_cookie=new_cookie,
                new_csrftoken=new_csrf,
            )
            with store.locked():
                current_data = store.read()
                current = current_data["profiles"].get(profile, {})
                confirmed_at = time.time()
                current.update(last_success=confirmed_at, last_confirmed=confirmed_at,
                               status="running",
                               last_error="", last_request_id=request_id,
                               success_count=current.get("success_count", 0) + 1)
                store.write(current_data)
            failure_delay = 0
        except AuthenticationError:
            stop_data = "平台会话已失效"
            break
        except (OSError, httpx.HTTPError, ValueError, BusinessError) as exc:
            failure_delay = min(max(failure_delay * 2, 30), 300)
            with store.locked():
                current_data = store.read()
                current = current_data["profiles"].get(profile, {})
                current.update(status="retrying", last_error=str(exc),
                               failure_count=current.get("failure_count", 0) + 1)
                store.write(current_data)
            time.sleep(5)
    with store.locked():
        data = store.read()
        entry = data["profiles"].get(profile, {})
        if entry.get("worker_pid") == os.getpid():
            entry.update(worker_pid=None, worker_identity=None,
                         status="stopped", last_error=stop_data)
            store.write(data)
