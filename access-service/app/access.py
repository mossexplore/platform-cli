import httpx
from fastapi import APIRouter, Header, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import select
from .models import Environment, User, Grant, CallLog, now
from .security import origin

router = APIRouter()


class Check(BaseModel):
    environment: str = Field(min_length=1, max_length=64)
    platform_origin: str = Field(min_length=1, max_length=512)
    command: str = Field(default='unknown', min_length=1, max_length=128, pattern=r'^[a-zA-Z0-9 _-]+$')


def denied(reason, message):
    return {'allowed': False, 'reason': reason, 'message': message}


@router.post('/api/v1/access/check')
def check_access(body: Check, request: Request,
                 x_platform_cookie: str = Header(default='', max_length=16384),
                 x_platform_csrf: str = Header(default='', max_length=4096),
                 businessid: str = Header(min_length=1, max_length=256)):
    result = None
    failure = None
    try:
        result = evaluate_access(body, request, x_platform_cookie, x_platform_csrf, businessid)
    except HTTPException as exc:
        failure = exc
    # 只记录经过验证的账号；身份验证之前的失败不能冒用客户端自报账号。
    with request.app.state.sessions() as db:
        db.add(CallLog(actor=getattr(request.state, 'verified_username', '未验证'),
            command=body.command, environment=body.environment, business_id=businessid,
            source_ip=(request.client.host if request.client else '')[:64],
            allowed=bool(result and result.get('allowed')),
            reason=('HTTP_' + str(failure.status_code)) if failure else result.get('reason', 'ALLOWED')))
        db.commit()
    if failure:
        raise failure
    return result


def evaluate_access(body, request, x_platform_cookie, x_platform_csrf, businessid):
    with request.app.state.sessions() as db:
        environment = db.scalar(select(Environment).where(Environment.name == body.environment))
        if not environment or environment.name != body.environment or not environment.enabled:
            return denied('ENVIRONMENT_DISABLED', '当前环境未启用权限访问')
        expected_origin = environment.platform_origin
        if origin(body.platform_origin) != expected_origin:
            return denied('ENVIRONMENT_MISMATCH', '环境与平台地址不匹配')
    if not x_platform_cookie:
        raise HTTPException(401, '缺少平台登录凭据，请重新登录')
    headers = {'cookie': x_platform_cookie, 'csrftoken': x_platform_csrf,
               'referer': expected_origin + '/dashboard'}
    if businessid:
        headers.update({'businessid': businessid, 'ai-businessId': businessid})
    try:
        # 只访问管理员保存的固定平台地址，不重定向，不缓存认证或授权结果。
        with httpx.Client(timeout=10, verify=True, follow_redirects=False,
                          transport=request.app.state.identity_transport) as client:
            response = client.get(expected_origin + '/ai/user/info', headers=headers)
        if response.status_code in (401, 403, 419, 440) or response.is_redirect:
            raise HTTPException(401, '平台登录已失效，请重新登录')
        if response.status_code != 200:
            raise HTTPException(503, '平台身份验证服务暂不可用')
        result = response.json().get('result')
        if not isinstance(result, dict) or type(result.get('code')) is not int or result['code'] != 0:
            raise HTTPException(401, '平台身份验证失败，请重新登录')
        username = result.get('username')
        if not isinstance(username, str) or not username.strip():
            raise HTTPException(503, '平台身份响应缺少有效账号')
    except (httpx.HTTPError, ValueError, AttributeError):
        raise HTTPException(503, '平台身份验证服务暂不可用') from None
    request.state.verified_username = username
    with request.app.state.sessions() as db:
        environment = db.scalar(select(Environment).where(Environment.name == body.environment))
        if not environment or not environment.enabled or environment.platform_origin != expected_origin:
            return denied('ENVIRONMENT_DISABLED', '环境授权配置已变更，请重试')
        user = db.scalar(select(User).where(User.username == username))
        if not user or user.username != username or not user.enabled:
            return denied('USER_DISABLED', '当前账号未获授权或已停用，请联系管理员')
        grant = db.scalar(select(Grant).where(Grant.user_id == user.id, Grant.environment_id == environment.id))
        if not grant or not grant.enabled:
            return denied('NOT_GRANTED', '当前账号未获当前环境授权，请联系管理员')
        if grant.expires_at and grant.expires_at <= now():
            return denied('GRANT_EXPIRED', '当前环境的使用授权已过期，请联系管理员')
        return {'allowed': True, 'username': username, 'environment': environment.name}
