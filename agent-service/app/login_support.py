"""Safe login diagnostics and local per-environment Edge profile lifecycle."""

import logging
import re
import shutil
import time
from .errors import AppError

log = logging.getLogger("wiserec.agent.login")
STAGES = {
    "profile": "准备浏览器缓存目录",
    "browser_launch": "启动 Edge",
    "navigation": "打开平台页面",
    "credential_capture": "读取并验证平台登录",
    "business_catalog": "读取平台业务目录",
    "browser_close": "关闭 Edge 窗口",
    "identity_probe": "后端验证平台身份",
    "credential_save": "保存登录结果到数据库",
    "profile_cleanup": "清除浏览器登录缓存",
    "provider": "获取平台登录结果",
}


def login_failure(stage, exc):
    if isinstance(exc, AppError):
        return exc
    kind = type(exc).__name__
    # Never include exception text, HTTP URLs, SQL parameters or traceback locals.
    args = getattr(getattr(exc, "orig", None), "args", ())
    mysql = args[0] if args and type(args[0]) is int else None
    suffix = f"，MySQL={mysql}" if mysql is not None else ""
    message = f"{STAGES.get(stage, '登录')}失败（阶段={stage}，异常={kind}{suffix}）"
    log.warning("login_failure stage=%s class=%s mysql=%s", stage, kind, mysql)
    return AppError("LOGIN_" + stage.upper(), message)


def profile_paths(config, environment_id):
    if not re.fullmatch(r"[a-z][a-z0-9_-]{0,31}", environment_id):
        raise AppError("ENVIRONMENT_INVALID", "环境标识无效")
    root = config.login.profile_root
    return root / ("env-" + environment_id), root / (
        "env-" + environment_id + ".clear-pending"
    )


def remove_profile(directory):
    for attempt in range(5):
        try:
            if directory.is_symlink():
                raise AppError("PROFILE_PATH_INVALID", "浏览器缓存目录不能是符号链接")
            if directory.exists():
                shutil.rmtree(directory)
            return
        except OSError as exc:
            if attempt == 4:
                raise login_failure("profile_cleanup", exc) from None
            time.sleep(0.2 * (attempt + 1))


def clear_profile(config, environment_id):
    directory, pending = profile_paths(config, environment_id)
    remove_profile(directory)
    pending.unlink(missing_ok=True)


def prepare_profile(config, environment_id):
    directory, pending = profile_paths(config, environment_id)
    config.login.profile_root.mkdir(parents=True, exist_ok=True)
    if pending.exists():
        clear_profile(config, environment_id)
    if directory.is_symlink():
        raise AppError("PROFILE_PATH_INVALID", "浏览器缓存目录不能是符号链接")
    directory.mkdir(parents=True, exist_ok=True)
    return directory
