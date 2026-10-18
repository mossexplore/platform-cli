"""收集本地环境状态，并用一次请求查询全部待检查环境及当前账号授权。"""
from .execution import create_client
import httpx

from .access import access_enabled
from .access_transport import permission_url, tls_verify
from .client_metadata import client_headers, handle_version_result
from .errors import MlError


def local_status(runtime, profile):
    try:
        credentials = runtime.credentials.load(profile.name)
    except MlError:
        return '登录信息异常', None, None
    if credentials is None:
        return '未登录', None, None
    username = credentials.username or None
    if credentials.is_expired():
        return '登录已过期', None, username
    if not username:
        return '登录信息异常', None, None
    try:
        if not runtime.business.has_profile(profile.name):
            return '未选择业务', None, username
        selection = runtime.business.selection(profile.name, username)
        if selection is None:
            return '未选择业务', None, username
        business_id = runtime.business.selected_business_id(profile.name, username)
        if business_id != selection.business_id:
            return '业务信息异常', None, username
    except MlError:
        return '业务信息异常', None, username
    return '查询失败', {'environment': profile.name, 'username': username,
                       'platform_origin': profile.base_url, 'business_id': business_id}, username


def query_environment_access(settings, username, checks, business_id=None):
    headers = client_headers()
    if business_id:
        headers['businessid'] = business_id
    url = permission_url(settings['url']).rsplit('/', 1)[0] + '/environments'
    try:
        with create_client(timeout=settings.get('timeout_seconds', 15), verify=tls_verify(),
                          follow_redirects=False, trust_env=settings.get('use_env_proxy', False)) as client:
            response = client.post(url, headers=headers, json={'username': username, 'environments': checks})
        if response.status_code == 404:
            raise MlError('权限服务尚不支持批量环境查询，请联系管理员更新权限服务')
        if response.status_code != 200:
            raise MlError(f'批量环境权限查询失败，HTTP {response.status_code}')
        result = response.json()
    except httpx.HTTPError:
        raise MlError('无法查询环境权限，请检查权限服务地址、网络及证书后重试') from None
    except ValueError:
        raise MlError('批量环境权限查询响应不是有效 JSON') from None
    if (not isinstance(result, dict) or not {'username', 'has_access', 'environments'} <= result.keys()
            or result.get('username') != username
            or (type(result.get('has_access')) is not bool if username else result.get('has_access') is not None)
            or not isinstance(result.get('environments'), list)):
        raise MlError('批量环境权限查询响应格式或账号不匹配')
    expected = {item['environment']: item for item in checks}
    seen = set()
    for item in result['environments']:
        if not isinstance(item, dict) or not isinstance(item.get('environment'), str):
            raise MlError('批量环境权限查询响应格式错误')
        name = item['environment']
        check = expected.get(name)
        decision = item.get('result')
        if (check is None or name in seen or item.get('username') != check['username']
                or item.get('business_id') != check['business_id'] or not isinstance(decision, dict)
                or type(decision.get('allowed')) is not bool):
            raise MlError('批量环境权限查询返回的环境、账号或业务不匹配')
        if decision['allowed'] and (decision.get('username') != check['username']
                                    or decision.get('environment') != name):
            raise MlError('批量环境权限查询授权结果与请求不匹配')
        seen.add(name)
    if seen != set(expected):
        raise MlError('批量环境权限查询结果不完整')
    return result


def environment_statuses(runtime):
    settings = runtime.config.access_control
    profiles = runtime.config.profiles()
    if not access_enabled(settings):
        raise MlError('权限校验已关闭，无法查询环境授权状态')
    if not settings.get('url'):
        raise MlError('请先配置权限服务地址 access_control.url')
    local = {p.name: local_status(runtime, p) for p in profiles}
    _, current_check, username = local[runtime.config.current_name]
    if not username:
        raise MlError('当前环境尚无登录账号，请先执行 ml login 查询 CLI 权限')
    checks = [check for _, check, owner in local.values() if check and owner == username]
    response = query_environment_access(settings, username, checks,
                                        current_check['business_id'] if current_check else None)
    if response['has_access'] is False:
        raise MlError(f"请打开{settings['url'].rstrip('/')}/apply进行CLI权限申请"
                      '（若地址无法打开，将*.hwcloudtest.cn加入代理排除），权限通过后方可执行CLI命令')
    authorizations = response.get('authorizations')
    if not isinstance(authorizations, list):
        raise MlError('权限服务尚不支持完整环境授权状态，请联系管理员更新权限服务')
    grants = {}
    for item in authorizations:
        if (not isinstance(item, dict) or not isinstance(item.get('environment'), str)
                or not isinstance(item.get('platform_origin'), str)
                or item['environment'] in grants):
            raise MlError('环境授权状态响应格式错误')
        grants[item['environment']] = item['platform_origin'].rstrip('/')
    decisions = {}
    for item in response['environments']:
        handle_version_result(item['result'])
        decisions[item['environment']] = item['result']['allowed']
    statuses = {}
    for profile in profiles:
        status, check, owner = local[profile.name]
        allowed = grants.get(profile.name) == profile.base_url.rstrip('/')
        if profile.name in decisions:
            allowed = allowed and decisions[profile.name]
        if not allowed:
            statuses[profile.name] = '未授权'
        elif owner == username and status == '登录已过期':
            statuses[profile.name] = '登录已过期'
        elif owner == username and check:
            statuses[profile.name] = '登录使用中'
        else:
            statuses[profile.name] = '已授权'
    return statuses
