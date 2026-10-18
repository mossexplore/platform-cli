"""登录与环境命令的用户授权提示，不替代业务请求的逐次鉴权。"""
from __future__ import annotations

from .execution import create_client
import httpx

from . import messages as msg
from .access import access_enabled
from .access_transport import permission_url, tls_verify
from .client_metadata import client_headers
from .errors import BusinessError, MlError
from .output import console


def check_user_access(settings, username, business_id=None):
    """查询账号在权限服务全部环境中是否存在当前有效授权。"""
    headers = client_headers()
    if business_id:
        headers['businessid'] = business_id
    url = permission_url(settings['url']).rsplit('/', 1)[0] + '/summary'
    try:
        with create_client(timeout=settings.get('timeout_seconds', 15),
                          verify=tls_verify(), follow_redirects=False,
                          trust_env=settings.get('use_env_proxy', False)) as client:
            response = client.post(url, headers=headers, json={'username': username})
        if response.status_code == 404:
            raise MlError('权限服务尚不支持用户授权查询，请联系管理员更新权限服务')
        if response.status_code != 200:
            raise MlError(f'用户授权查询失败，HTTP {response.status_code}，请联系管理员')
        result = response.json()
    except httpx.HTTPError:
        raise MlError('无法查询用户授权，请检查权限服务地址、网络及证书后重试') from None
    except ValueError:
        raise MlError('用户授权查询响应不是有效 JSON，请联系管理员') from None
    if (not isinstance(result, dict) or type(result.get('has_access')) is not bool
            or result.get('username') != username):
        raise MlError('用户授权查询响应格式或账号不匹配，请联系管理员')
    return result['has_access']


def show_access_guidance(runtime, credentials=None):
    """返回是否有有效授权；无账号时提示登录，不借用其他环境身份。"""
    settings = runtime.config.access_control
    if not access_enabled(settings):
        return True
    credentials = credentials or runtime.credentials.load(runtime.config.current_name)
    if credentials is None or not credentials.username:
        msg.info('当前环境尚无登录账号，请先执行 ml login 查询 CLI 权限')
        return False
    if not settings.get('url'):
        raise MlError('请先在 config.json 中配置 access_control.url 后查询 CLI 权限')
    business_id = None
    try:
        if runtime.business.has_profile(runtime.config.current_name):
            selection = runtime.business.selection(runtime.config.current_name, credentials.username)
            if selection is not None:
                selected_id = runtime.business.selected_business_id(
                    runtime.config.current_name, credentials.username)
                if selected_id == selection.business_id:
                    business_id = selected_id
    except BusinessError:
        # This account-level query must also work before selecting a business or
        # after switching accounts. Never borrow another account's business ID.
        pass
    if check_user_access(settings, credentials.username, business_id):
        return True
    url = settings['url'].rstrip('/') + '/apply'
    msg.info(f'请打开{url}进行CLI权限申请（若地址无法打开，将*.hwcloudtest.cn加入代理排除），'
        '权限通过后方可执行CLI命令')
    return False
