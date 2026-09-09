from fastapi import APIRouter, Header, Request
from pydantic import BaseModel, Field
from sqlalchemy import select
from .models import Environment, User, Grant, CallLog, now
from .security import origin

router = APIRouter()


class Check(BaseModel):
    username: str = Field(strict=True, min_length=1, max_length=128, pattern=r'\S')
    environment: str = Field(min_length=1, max_length=64)
    platform_origin: str = Field(min_length=1, max_length=512)
    command: str = Field(default='unknown', min_length=1, max_length=128, pattern=r'^[a-zA-Z0-9 _-]+$')


def denied(reason, message):
    return {'allowed': False, 'reason': reason, 'message': message}


@router.post('/api/v1/access/check')
def check_access(body: Check, request: Request,
                 businessid: str = Header(min_length=1, max_length=256)):
    result = evaluate_access(body, request)
    # 账号由 CLI 上报，日志不表示已通过平台身份核验。
    with request.app.state.sessions() as db:
        db.add(CallLog(actor=body.username,
            command=body.command, environment=body.environment, business_id=businessid,
            source_ip=(request.client.host if request.client else '')[:64],
            allowed=result['allowed'], reason=result.get('reason', 'ALLOWED')))
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
