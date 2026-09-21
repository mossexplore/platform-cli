import json
import secrets
from fastapi import APIRouter, Header, Request, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy import select
from .models import Environment, User, Grant, CallLog, now
from .security import origin
from .version_policy import metadata, evaluate_version

router = APIRouter()


class Check(BaseModel):
    username: str = Field(strict=True, min_length=1, max_length=128, pattern=r'\S')
    environment: str = Field(min_length=1, max_length=64)
    platform_origin: str = Field(min_length=1, max_length=512)
    full_command: str = Field(default='', strict=True, max_length=8192)
    command: str = Field(default='unknown', min_length=1, max_length=128, pattern=r'^[a-zA-Z0-9 _-]+$')


def denied(reason, message):
    return {'allowed': False, 'reason': reason, 'message': message}


@router.post('/api/v1/access/check')
def check_access(body: Check, request: Request,
                 businessid: str = Header(min_length=1, max_length=256)):
    return recorded_check(body, request, businessid)


@router.post('/api/v1/gateway/check')
def gateway_check(body: Check, request: Request,
                  businessid: str = Header(min_length=1, max_length=256)):
    # Server-to-server only. Gateway must authenticate the platform identity and
    # business membership before constructing the body; never forward client identity fields.
    expected = request.app.state.settings.gateway_token
    if not expected or len(expected) < 32:
        raise HTTPException(503, '网关检查未配置')
    provided = request.headers.get('authorization', '')
    if not secrets.compare_digest(provided.encode(), ('Bearer ' + expected).encode()):
        raise HTTPException(401, '网关认证失败')
    result = recorded_check(body, request, businessid, source='gateway')
    return JSONResponse(result, status_code=200 if result['allowed'] else 403)


def recorded_check(body, request, businessid, source='client'):
    result = evaluate_access(body, request)
    info = metadata(request)
    with request.app.state.sessions() as db:
        decision = evaluate_version(db, body.environment, businessid, body.username, info)
        if result['allowed']:
            if not decision['allowed']:
                result = {**decision, 'code': decision['reason'], 'request_id': info['request_id']}
            elif decision['policy_ids']:
                result['version_policy'] = decision
        # Client-reported identity is not platform-verified. Gateway records are
        # trusted only under the documented gateway authentication contract.
        db.add(CallLog(actor=body.username,
            command=body.command, full_command=body.full_command, environment=body.environment, business_id=businessid,
            source_ip=(request.client.host if request.client else '')[:64],
            allowed=result['allowed'], reason=result.get('reason', 'ALLOWED'),
            cli_version=info['version'], version_source=info['source'], protocol_version=info['protocol'],
            installation_id=info['installation_id'], invocation_id=info['invocation_id'],
            request_id=info['request_id'], check_source=source,
            version_decision=json.dumps(decision, ensure_ascii=False)))
        db.commit()
    return result


def evaluate_access(body, request):
    with request.app.state.sessions() as db:
        environment = db.scalar(select(Environment).where(Environment.name == body.environment))
        if not environment or environment.name != body.environment or not environment.enabled:
            return denied('ENVIRONMENT_DISABLED', '当前环境未启用权限访问')
        expected_origin = environment.platform_origin
        if origin(body.platform_origin) != expected_origin:
            return denied('ENVIRONMENT_MISMATCH', '环境与平台地址不匹配')
        user = db.scalar(select(User).where(User.username == body.username))
        if not user or user.username != body.username or not user.enabled:
            return denied('USER_DISABLED', '当前账号未获授权或已停用，请联系管理员')
        grant = db.scalar(select(Grant).where(Grant.user_id == user.id, Grant.environment_id == environment.id))
        if not grant or not grant.enabled:
            return denied('NOT_GRANTED', '当前账号未获当前环境授权，请联系管理员')
        if grant.expires_at and grant.expires_at <= now():
            return denied('GRANT_EXPIRED', '当前环境的使用授权已过期，请联系管理员')
        return {'allowed': True, 'username': body.username, 'environment': environment.name}
