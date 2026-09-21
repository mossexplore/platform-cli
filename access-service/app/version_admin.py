"""版本策略、发布前影响预览和有期限的逐策略例外。"""
import json
from datetime import timedelta
from urllib.parse import urlsplit
from fastapi import APIRouter, Form, HTTPException, Query, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import case, func, select
from .admin_auth import admin_session, authorize_form
from .models import Audit, CallLog, Environment, now
from .security import expiry
from .version_models import VersionPolicy, VersionException
from .version_policy import evaluate_version, policies_for, version_tuple
from .pagination import PAGE_SIZE

router = APIRouter()


def privileged(request, db, csrf):
    admin = authorize_form(request, db, csrf)
    if admin.role != 'super_admin':
        raise HTTPException(403, '版本策略变更需要超级管理员权限')
    return admin


def parse_version(value):
    try:
        version_tuple(value)
        return value
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from None


def validate_policy(db, values):
    if values['mode'] not in ('observe', 'warn', 'enforce'):
        raise HTTPException(400, '版本策略模式无效')
    if values['business_id'] and not values['environment']:
        raise HTTPException(400, '业务策略必须指定环境')
    if values['environment'] and not db.scalar(select(Environment).where(Environment.name == values['environment'])):
        raise HTTPException(400, '指定环境不存在')
    parse_version(values['minimum_version'])
    if values['recommended_version']:
        parse_version(values['recommended_version'])
        if version_tuple(values['recommended_version']) < version_tuple(values['minimum_version']):
            raise HTTPException(400, '推荐版本不能低于最低版本')
    blocked = sorted(set(values['blocked_versions'].replace(',', ' ').split()), key=parse_version)
    if values['recommended_version'] in blocked:
        raise HTTPException(400, '推荐版本不能同时被禁用')
    url = values['upgrade_url']
    if url:
        try:
            parts = urlsplit(url)
            valid = parts.scheme in ('http', 'https') and parts.hostname and not parts.username and not parts.password
            _ = parts.port
        except ValueError:
            valid = False
        if not valid:
            raise HTTPException(400, '升级地址必须是无凭据的 HTTP(S) 地址')
    return {**values, 'blocked_versions': json.dumps(blocked), 'effective_at': expiry(values['effective_at']) or now()}


def snapshot(item):
    return {key: (value.isoformat() if hasattr(value, 'isoformat') else value)
            for key, value in vars(item).items() if not key.startswith('_')}


@router.get('/admin/versions')
def versions(request: Request, days: int = Query(7, ge=1, le=90),
             environment: str = Query('', max_length=64), business_id: str = Query('', max_length=256),
             page: int = Query(1, ge=1)):
    with request.app.state.sessions() as db:
        try:
            admin, session = admin_session(request, db)
        except HTTPException as exc:
            if exc.status_code == 401:
                return RedirectResponse('/cli-permission/login', status_code=303)
            raise
        groups = [CallLog.environment, CallLog.business_id, CallLog.cli_version, CallLog.version_source, CallLog.check_source]
        query = select(*groups, func.count().label('calls'),
                       func.max(CallLog.created_at).label('last_seen'),
                       func.sum(case((CallLog.reason.in_(['CLI_VERSION_TOO_OLD', 'CLI_VERSION_BLOCKED',
                           'CLI_VERSION_INVALID', 'CLI_PROTOCOL_UNSUPPORTED']), 1), else_=0)).label('denied'),
                       func.count(func.distinct(CallLog.actor)).label('accounts')).where(CallLog.created_at >= now() - timedelta(days=days))
        if environment:
            query = query.where(CallLog.environment == environment)
        if business_id:
            query = query.where(CallLog.business_id == business_id)
        query = query.group_by(*groups)
        count = db.scalar(select(func.count()).select_from(query.subquery()))
        rows = db.execute(query.order_by(func.max(CallLog.created_at).desc(), *groups)
                          .offset((page-1)*PAGE_SIZE).limit(PAGE_SIZE)).all()
        return request.app.state.templates.TemplateResponse(request=request, name='versions.html', context={
            'admin': admin, 'csrf': session.csrf, 'rows': rows, 'days': days, 'environment': environment,
            'business_id': business_id, 'count': count, 'page': page,
            'previous': str(request.url.include_query_params(page=page-1)),
            'next': str(request.url.include_query_params(page=page+1)),
            'policies': db.scalars(select(VersionPolicy).order_by(VersionPolicy.id.desc())).all(),
            'exceptions': db.scalars(select(VersionException).order_by(VersionException.id.desc())).all(),
            'environments': db.scalars(select(Environment).order_by(Environment.name)).all()})


@router.post('/admin/versions/policies')
def save_policy(request: Request, csrf: str = Form(max_length=64),
                name: str = Form(min_length=1, max_length=128), environment: str = Form('', max_length=64),
                business_id: str = Form('', max_length=256), mode: str = Form('observe'),
                minimum_version: str = Form('1.0.0', max_length=64), recommended_version: str = Form('', max_length=64),
                blocked_versions: str = Form('', max_length=4096), upgrade_url: str = Form('', max_length=1024),
                effective_at: str = Form('', max_length=32), intent: str = Form('preview')):
    values = dict(name=name.strip(), environment=environment, business_id=business_id, mode=mode,
                  minimum_version=minimum_version, recommended_version=recommended_version,
                  blocked_versions=blocked_versions, upgrade_url=upgrade_url, effective_at=effective_at)
    if not values['name']:
        raise HTTPException(400, '策略名称不能为空')
    with request.app.state.sessions() as db:
        admin = privileged(request, db, csrf)
        validated = validate_policy(db, values)
        item = VersionPolicy(**validated, created_by=admin.username, enabled=True)
        if intent == 'preview':
            # Aggregate historical checks, not business executions or physical devices.
            groups = [CallLog.environment, CallLog.business_id, CallLog.actor, CallLog.cli_version, CallLog.protocol_version]
            samples = db.execute(select(*groups, func.count()).where(
                CallLog.created_at >= now() - timedelta(days=7)).group_by(*groups)).all()
            affected, checked = 0, 0
            for env, business, actor, version, protocol, total in samples:
                if (environment and env != environment) or (business_id and business != business_id):
                    continue
                try:
                    version_tuple(version)
                    valid = True
                except ValueError:
                    valid = False
                info = dict(version=version, valid=valid, protocol_valid=protocol == '1', source='preview')
                item.id = -1
                existing = policies_for(db, env, business, item.effective_at)
                result = evaluate_version(db, env, business, actor, info, item.effective_at, [*existing, item])
                checked += total
                if not result['allowed']:
                    affected += total
            return request.app.state.templates.TemplateResponse(request=request, name='version_preview.html', context={
                'admin': admin, 'csrf': csrf, 'values': values, 'checked': checked, 'affected': affected,
                'effective_at': item.effective_at})
        if intent != 'publish':
            raise HTTPException(400, '策略操作无效')
        db.add(item)
        db.flush()
        db.add(Audit(actor=admin.username, action='version_policy.publish', detail=json.dumps(snapshot(item), ensure_ascii=False)))
        db.commit()
    return RedirectResponse('/cli-permission/admin/versions', status_code=303)


@router.post('/admin/versions/policies/{policy_id}/toggle')
def toggle_policy(policy_id: int, request: Request, csrf: str = Form(max_length=64), enabled: bool = Form()):
    with request.app.state.sessions() as db:
        admin = privileged(request, db, csrf)
        item = db.get(VersionPolicy, policy_id)
        if not item:
            raise HTTPException(404, '策略不存在')
        before = snapshot(item)
        item.enabled = enabled
        db.add(Audit(actor=admin.username, action='version_policy.toggle',
                     detail=json.dumps({'before': before, 'after': snapshot(item)}, ensure_ascii=False)))
        db.commit()
    return RedirectResponse('/cli-permission/admin/versions', status_code=303)


@router.post('/admin/versions/exceptions')
def add_exception(request: Request, csrf: str = Form(max_length=64), policy_id: int = Form(),
                  environment: str = Form(min_length=1, max_length=64), business_id: str = Form(min_length=1, max_length=256),
                  username: str = Form(min_length=1, max_length=128), minimum_version: str = Form(max_length=64),
                  maximum_version: str = Form(max_length=64), expires_at: str = Form(max_length=32),
                  reason: str = Form(min_length=1, max_length=1000)):
    with request.app.state.sessions() as db:
        admin = privileged(request, db, csrf)
        policy = db.get(VersionPolicy, policy_id)
        if not policy or (policy.environment and policy.environment != environment) or (policy.business_id and policy.business_id != business_id):
            raise HTTPException(400, '例外与指定策略的环境或业务不匹配')
        parse_version(minimum_version)
        parse_version(maximum_version)
        deadline = expiry(expires_at)
        if not deadline or deadline <= now() or version_tuple(minimum_version) > version_tuple(maximum_version) or not reason.strip():
            raise HTTPException(400, '例外必须有未来失效时间、有效版本范围和原因')
        item = VersionException(policy_id=policy_id, environment=environment, business_id=business_id,
            username=username, minimum_version=minimum_version, maximum_version=maximum_version,
            expires_at=deadline, reason=reason, created_by=admin.username)
        db.add(item)
        db.flush()
        db.add(Audit(actor=admin.username, action='version_exception.create', detail=json.dumps(snapshot(item), ensure_ascii=False)))
        db.commit()
    return RedirectResponse('/cli-permission/admin/versions', status_code=303)


@router.post('/admin/versions/exceptions/{item_id}/revoke')
def revoke_exception(item_id: int, request: Request, csrf: str = Form(max_length=64)):
    with request.app.state.sessions() as db:
        admin = privileged(request, db, csrf)
        item = db.get(VersionException, item_id)
        if not item:
            raise HTTPException(404, '例外不存在')
        item.enabled = False
        db.add(Audit(actor=admin.username, action='version_exception.revoke', detail=json.dumps(snapshot(item), ensure_ascii=False)))
        db.commit()
    return RedirectResponse('/cli-permission/admin/versions', status_code=303)
