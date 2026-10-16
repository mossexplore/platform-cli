"""环境列表的一次性权限查询，不替代业务调用前的实时鉴权。"""
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field
from .access import Check, recorded_check
from sqlalchemy import select, or_
from .models import Environment, Grant, User, now

router = APIRouter()


class EnvironmentCheck(Check):
    business_id: str = Field(strict=True, min_length=1, max_length=256, pattern=r'^[^\r\n]+$')


class EnvironmentBatch(BaseModel):
    username: str | None = Field(default=None, strict=True, min_length=1, max_length=128, pattern=r'\S')
    environments: list[EnvironmentCheck] = Field(default_factory=list, max_length=100)


@router.post('/api/v1/access/environments')
def environment_access(body: EnvironmentBatch, request: Request):
    names = [item.environment for item in body.environments]
    if len(names) != len(set(names)):
        raise HTTPException(422, '环境标识不能重复')
    authorizations = []
    if body.username:
        with request.app.state.sessions() as db:
            rows = db.execute(select(Environment.name, Environment.platform_origin)
                .join(Grant, Grant.environment_id == Environment.id)
                .join(User, Grant.user_id == User.id)
                .where(User.username == body.username, User.enabled.is_(True),
                       Environment.enabled.is_(True), Grant.enabled.is_(True),
                       or_(Grant.expires_at.is_(None), Grant.expires_at > now()))).all()
            authorizations = [{'environment': name, 'platform_origin': origin}
                              for name, origin in rows]
    results = []
    for item in body.environments:
        check = Check(username=item.username, environment=item.environment,
                      platform_origin=item.platform_origin,
                      command='ml env list', full_command='ml env list')
        result = recorded_check(check, request, item.business_id)
        results.append({'environment': item.environment, 'username': item.username,
                        'business_id': item.business_id, 'result': result})
    return {'username': body.username, 'has_access': bool(authorizations) if body.username else None,
            'environments': results, 'authorizations': authorizations}
