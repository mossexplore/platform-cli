"""环境列表的一次性权限查询，不替代业务调用前的实时鉴权。"""
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field
from .access import Check, UserAccessQuery, recorded_check, user_access_summary

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
    summary = user_access_summary(UserAccessQuery(username=body.username), request) if body.username else None
    results = []
    for item in body.environments:
        check = Check(username=item.username, environment=item.environment,
                      platform_origin=item.platform_origin,
                      command='ml env list', full_command='ml env list')
        result = recorded_check(check, request, item.business_id)
        results.append({'environment': item.environment, 'username': item.username,
                        'business_id': item.business_id, 'result': result})
    return {'username': body.username, 'has_access': summary['has_access'] if summary else None,
            'environments': results}
