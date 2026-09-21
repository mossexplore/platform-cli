"""统一客户端标识；版本来自运行中的包，安装标识不参与认证。"""
from contextvars import ContextVar
import os
from pathlib import Path
from uuid import UUID, uuid4
from . import __version__
from .errors import MlError

_invocation = ContextVar('cli_invocation', default=None)
_warned = ContextVar('cli_version_warned', default=False)


def begin_invocation():
    _invocation.set(str(uuid4()))
    _warned.set(False)


def installation_id():
    from .config import user_config_dir
    directory = Path(os.environ['ML_CLIENT_STATE_DIR']) if os.environ.get('ML_CLIENT_STATE_DIR') else user_config_dir()
    path = directory / 'installation-id'
    try:
        directory.mkdir(parents=True, exist_ok=True)
        try:
            # Exclusive creation preserves the identity across concurrent invocations.
            with path.open('x', encoding='utf-8') as stream:
                value = str(uuid4())
                stream.write(value)
                return value
        except FileExistsError:
            return str(UUID(path.read_text(encoding='utf-8').strip()))
    except (OSError, ValueError):
        # Observability must not break an otherwise authorized operation.
        return None


def client_headers():
    if _invocation.get() is None:
        begin_invocation()
    headers = {'X-CLI-Name': 'wiserec-cli', 'X-CLI-Version': __version__,
               'X-CLI-Protocol-Version': '1', 'X-CLI-Invocation-ID': _invocation.get(),
               'X-Request-ID': str(uuid4())}
    installed = installation_id()
    if installed:
        headers['X-CLI-Installation-ID'] = installed
    return headers


class VersionPolicyError(MlError):
    """版本准入拒绝，不触发登录刷新或业务重试。"""


def handle_version_result(result):
    if not isinstance(result, dict):
        return
    code = result.get('code') or result.get('reason', '')
    labels = {'CLI_VERSION_REQUIRED': '未上报 CLI 版本',
              'CLI_VERSION_INVALID': 'CLI 版本格式不合法',
              'CLI_VERSION_TOO_OLD': 'CLI 版本过低',
              'CLI_VERSION_BLOCKED': '当前 CLI 版本已停用',
              'CLI_PROTOCOL_UNSUPPORTED': 'CLI 上报协议不受支持'}
    if isinstance(code, str) and code in labels:
        detail = (f"{labels[code]}：当前 {result.get('current_version', __version__)}；"
                  f"最低要求 {result.get('minimum_version') or '请联系管理员'}；"
                  f"推荐版本 {result.get('recommended_version') or '请联系管理员'}")
        if result.get('upgrade_url'):
            detail += f"；升级说明：{result['upgrade_url']}"
        raise VersionPolicyError(detail)
    info = result.get('version_policy', result)
    if isinstance(info, dict) and info.get('warning') and not _warned.get():
        import sys
        print(f"升级提醒：当前 CLI {__version__}；推荐版本 {info.get('recommended_version') or info.get('minimum_version') or '请联系管理员'}。"
              f" {info.get('upgrade_url') or ''}", file=sys.stderr)
        _warned.set(True)


def check_version_response(response):
    # Parse only the stable envelope; never treat a policy denial as auth expiry.
    try:
        handle_version_result(response.json())
    except ValueError:
        pass
