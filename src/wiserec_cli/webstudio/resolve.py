"""平台认证只包围连接发现，不包围任何 Jupyter 执行动作。"""
import json
import ssl
from contextlib import contextmanager, redirect_stdout
from pathlib import Path
import sys
from urllib.parse import urljoin

from ..access import check_access
from ..client import PlatformClient
from ..jupyter.connection import Connection, JupyterClient, JupyterError
from ..services.webstudio import WebStudioService
from .store import SelectionStore
from .urls import parse_access_url, server_url_for_instance, validate_server_urls


@contextmanager
def platform(runtime):
    # 平台认证输出不污染 --output json 的 stdout。
    with redirect_stdout(sys.stderr):
        credentials = runtime.auth.ensure_credentials()
    profile = runtime.config.current_profile()
    selection = runtime.business.require_selection(profile.name, credentials.username)
    raw = json.loads(runtime.business.path.read_text(encoding='utf-8'))
    stored = raw['profiles'][profile.name]['selected'].get('businessId')
    if not stored or stored != selection.business_id:
        raise JupyterError('当前环境 selected.businessId 无效，请重新选择业务')
    check_access(runtime.config.access_control, profile, credentials, selection,
                 command=runtime.invocation_command, full_command=getattr(runtime, 'full_command', ''))
    with PlatformClient(profile, credentials, runtime.config.timeout_ms, 0,
                        runtime.config.verify_ssl, business_selection=selection) as client:
        yield WebStudioService(client), credentials.username, stored


def resolve(runtime, studio_id=None, *, login=False, store=None, report=None):
    settings = runtime.config.jupyter_settings()
    if settings.get('mode', 'direct') != 'webstudio':
        raise JupyterError('此操作需要当前环境 jupyter.mode=webstudio')
    if settings.get('business_file'):
        raise JupyterError('webstudio 模式使用平台业务上下文，请移除 jupyter.business_file')
    # 提前检查所有网关配置，避免配置错误时仍调用登录接口。
    validate_server_urls(settings)
    store = store or SelectionStore()
    notify = report or (lambda message: None)
    with platform(runtime) as (service, username, business_id):
        key = store.key(runtime, username, business_id)
        saved = store.get(key) if not studio_id else None
        target = studio_id or (saved or {}).get('envId')
        if not target:
            raise JupyterError('未选择 Web Studio，请执行 ml webstudio list 和 ml webstudio login ENV_ID')
        notify(f'管理台认证：通过；环境 {runtime.config.current_name}；业务 {business_id}')
        item = service.get(target)
        if 'status' not in item:
            raise JupyterError('Web Studio 响应缺少 status，无法确认实例是否可连接')
        if item.get('status') != 'online':
            raise JupyterError('Web Studio 当前不是 online 状态；请在管理台确认或启动实例')
        notify(f'实例查询：通过；Web Studio {target}')
        server_url = server_url_for_instance(settings, item)
        access_url = service.access(target)
        full_access_url = urljoin(server_url.rstrip('/') + '/', access_url)
        notify(f'Jupyter 完整访问地址（包含 token，请谨慎保管）：{full_access_url}')
        url, token = parse_access_url(server_url, access_url)
        notify('访问地址获取：通过')
    verify = runtime.config.verify_ssl
    if settings.get('ca_file'):
        path = Path(settings['ca_file']).expanduser()
        if not path.is_absolute():
            path = runtime.config.path.parent / path
        verify = ssl.create_default_context(cafile=str(path))
    connection = Connection(url, token, business_id, settings.get('kernel', 'python3'), verify,
                            runtime.config.timeout_ms / 1000, studio_id=target)
    if login:
        with JupyterClient(connection) as client:
            client.request('GET', 'api/kernelspecs')
        store.save(key, item)
    return connection


def show(runtime, store=None):
    if runtime.config.jupyter_settings().get('mode', 'direct') != 'webstudio':
        raise JupyterError('此操作需要当前环境 jupyter.mode=webstudio')
    store = store or SelectionStore()
    with platform(runtime) as (_, username, business_id):
        result = store.get(store.key(runtime, username, business_id))
    if not result:
        raise JupyterError('当前上下文未选择 Web Studio，请先执行 ml webstudio login ENV_ID')
    return result
