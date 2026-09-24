"""版本策略、发布前影响预览和有期限的逐策略例外。"""
import json
from datetime import timedelta
from urllib.parse import urlsplit
from fastapi import APIRouter, Form, HTTPException, Query, Request
from fastapi.responses import RedirectResponse, JSONResponse
from sqlalchemy import func, select
from .admin_auth import admin_session, authorize_form
from .models import Audit, CallLog, Environment, now
from .security import expiry
from .version_models import VersionPolicy, VersionException
from .version_policy import evaluate_version, policies_for, version_tuple
from .version_views import page_context

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
    blocked = set(values['blocked_versions'].replace(',', ' ').split())
    for item in blocked:
        parse_version(item)
    blocked = sorted(blocked, key=version_tuple)
    if values['recommended_version'] and any(
            version_tuple(values['recommended_version']) == version_tuple(item) for item in blocked):
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


def policy_values(name, environment, business_id, mode, minimum_version,
                  recommended_version, blocked_versions, upgrade_url, effective_at):
    return dict(name=name.strip(), environment=environment, business_id=business_id, mode=mode,
                minimum_version=minimum_version, recommended_version=recommended_version,
                blocked_versions=blocked_versions, upgrade_url=upgrade_url, effective_at=effective_at)


def persist_policy(request, csrf, values, intent, policy_id=None):
    if not values['name']:
        raise HTTPException(400, '策略名称不能为空')
    with request.app.state.sessions() as db:
        admin = privileged(request, db, csrf)
        existing = db.get(VersionPolicy, policy_id) if policy_id is not None else None
        if policy_id is not None and (existing is None or existing.deleted_at is not None):
            raise HTTPException(404, '策略不存在')
        validated = validate_policy(db, values)
        item = VersionPolicy(**validated, id=policy_id, created_by=existing.created_by if existing else admin.username,
                             enabled=existing.enabled if existing else True)
        if intent == 'preview':
            # Compare the edited rule with the same rules that will be active after saving.
            groups = [CallLog.environment, CallLog.business_id, CallLog.actor, CallLog.cli_version, CallLog.protocol_version]
            samples = db.execute(select(*groups, func.count()).where(
                CallLog.created_at >= now() - timedelta(days=7)).group_by(*groups)).all()
            affected, checked = 0, 0
            for env, business, actor, version, protocol, total in samples:
                new_scope = (not values['environment'] or env == values['environment']) and (
                    not values['business_id'] or business == values['business_id'])
                old_scope = existing is not None and (
                    not existing.environment or env == existing.environment) and (
                    not existing.business_id or business == existing.business_id)
                if not new_scope and not old_scope:
                    continue
                try:
                    version_tuple(version)
                    valid = True
                except ValueError:
                    valid = False
                info = dict(version=version, valid=valid, protocol_valid=protocol == '1', source='preview')
                timestamp = item.effective_at
                policies = [p for p in policies_for(db, env, business, timestamp) if p.id != policy_id]
                if item.enabled and new_scope:
                    item.id = policy_id if policy_id is not None else -1
                    policies.append(item)
                result = evaluate_version(db, env, business, actor, info, timestamp, policies)
                checked += total
                if not result['allowed']:
                    affected += total
            if 'application/json' in request.headers.get('accept', ''):
                html = request.app.state.templates.get_template('version_preview_summary.html').render(
                    values=values, checked=checked, affected=affected, effective_at=item.effective_at)
                return JSONResponse({'preview_html': html})
            return request.app.state.templates.TemplateResponse(request=request, name='version_preview.html', context={
                'admin': admin, 'csrf': csrf, 'values': values, 'checked': checked, 'affected': affected,
                'effective_at': item.effective_at, 'policy_id': policy_id})
        if intent != 'publish':
            raise HTTPException(400, '策略操作无效')
        if existing:
            before = snapshot(existing)
            for field, value in validated.items():
                setattr(existing, field, value)
            db.add(Audit(actor=admin.username, action='version_policy.update',
                         detail=json.dumps({'before': before, 'after': snapshot(existing)}, ensure_ascii=False)))
        else:
            db.add(item)
            db.flush()
            db.add(Audit(actor=admin.username, action='version_policy.publish',
                         detail=json.dumps(snapshot(item), ensure_ascii=False)))
        db.commit()
    return RedirectResponse('/cli-permission/admin/versions?saved=1', status_code=303)


@router.get('/admin/versions')
def versions(request: Request, days: int = Query(7, ge=1, le=90),
             environment: str = Query('', max_length=64), business_id: str = Query('', max_length=256),
             page: int = Query(1, ge=1), view: str = Query('policies', pattern='^(policies|usage|exceptions)$'),
             q: str = Query('', max_length=128), status: str = Query('', pattern='^(|active|scheduled|disabled|expired|denied)$')):
    with request.app.state.sessions() as db:
        try:
            admin, session = admin_session(request, db)
        except HTTPException as exc:
            if exc.status_code == 401:
                return RedirectResponse('/cli-permission/login', status_code=303)
            raise
        context = page_context(db, view=view, days=days, environment=environment,
                               business_id=business_id, q=q, status=status, page=page)
        return request.app.state.templates.TemplateResponse(request=request, name='versions.html', context={
            'admin': admin, 'csrf': session.csrf, **context})


@router.post('/admin/versions/policies')
def save_policy(request: Request, csrf: str = Form(max_length=64),
                name: str = Form(min_length=1, max_length=128), environment: str = Form('', max_length=64),
                business_id: str = Form('', max_length=256), mode: str = Form('observe'),
                minimum_version: str = Form('1.0.0', max_length=64), recommended_version: str = Form('', max_length=64),
                blocked_versions: str = Form('', max_length=4096), upgrade_url: str = Form('', max_length=1024),
                effective_at: str = Form('', max_length=32), intent: str = Form('preview')):
    values = policy_values(name, environment, business_id, mode, minimum_version,
                           recommended_version, blocked_versions, upgrade_url, effective_at)
    return persist_policy(request, csrf, values, intent)


@router.post('/admin/versions/policies/{policy_id}')
def edit_policy(policy_id: int, request: Request, csrf: str = Form(max_length=64),
                name: str = Form(min_length=1, max_length=128), environment: str = Form('', max_length=64),
                business_id: str = Form('', max_length=256), mode: str = Form('observe'),
                minimum_version: str = Form('1.0.0', max_length=64), recommended_version: str = Form('', max_length=64),
                blocked_versions: str = Form('', max_length=4096), upgrade_url: str = Form('', max_length=1024),
                effective_at: str = Form('', max_length=32), intent: str = Form('preview')):
    values = policy_values(name, environment, business_id, mode, minimum_version,
                           recommended_version, blocked_versions, upgrade_url, effective_at)
    return persist_policy(request, csrf, values, intent, policy_id)


@router.post('/admin/versions/policies/{policy_id}/toggle')
def toggle_policy(policy_id: int, request: Request, csrf: str = Form(max_length=64), enabled: bool = Form()):
    with request.app.state.sessions() as db:
        admin = privileged(request, db, csrf)
        item = db.get(VersionPolicy, policy_id)
        if not item or item.deleted_at is not None:
            raise HTTPException(404, '策略不存在')
        before = snapshot(item)
        item.enabled = enabled
        db.add(Audit(actor=admin.username, action='version_policy.toggle',
                     detail=json.dumps({'before': before, 'after': snapshot(item)}, ensure_ascii=False)))
        db.commit()
    return RedirectResponse('/cli-permission/admin/versions?saved=1', status_code=303)


@router.post('/admin/versions/policies/{policy_id}/delete')
def delete_policy(policy_id: int, request: Request, csrf: str = Form(max_length=64),
                  confirmation: str = Form('', max_length=16)):
    with request.app.state.sessions() as db:
        admin = privileged(request, db, csrf)
        item = db.get(VersionPolicy, policy_id)
        if not item or item.deleted_at is not None:
            raise HTTPException(404, '策略不存在')
        if item.enabled:
            raise HTTPException(400, '请先停用策略，再删除')
        if confirmation != 'yes':
            raise HTTPException(400, '请输入 yes 确认删除')
        before = snapshot(item)
        timestamp = now()
        item.deleted_at = timestamp
        related = db.scalars(select(VersionException).where(
            VersionException.policy_id == policy_id, VersionException.enabled.is_(True),
            VersionException.expires_at > timestamp)).all()
        for exception in related:
            exception.enabled = False
        db.add(Audit(actor=admin.username, action='version_policy.delete', detail=json.dumps({
            'before': before, 'after': snapshot(item),
            'revoked_exception_ids': [exception.id for exception in related]}, ensure_ascii=False)))
        db.commit()
    return RedirectResponse('/cli-permission/admin/versions?view=policies&deleted=1', status_code=303)


@router.post('/admin/versions/exceptions')
def add_exception(request: Request, csrf: str = Form(max_length=64), policy_id: int = Form(),
                  environment: str = Form(min_length=1, max_length=64), business_id: str = Form(min_length=1, max_length=256),
                  username: str = Form(min_length=1, max_length=128), minimum_version: str = Form(max_length=64),
                  maximum_version: str = Form(max_length=64), expires_at: str = Form(max_length=32),
                  reason: str = Form(min_length=1, max_length=1000)):
    with request.app.state.sessions() as db:
        admin = privileged(request, db, csrf)
        policy = db.get(VersionPolicy, policy_id)
        if not policy or not policy.enabled or policy.deleted_at is not None:
            raise HTTPException(400, '只能为已启用的策略创建例外')
        if (policy.environment and policy.environment != environment) or (policy.business_id and policy.business_id != business_id):
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
    return RedirectResponse('/cli-permission/admin/versions?view=exceptions&saved=1', status_code=303)


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
    return RedirectResponse('/cli-permission/admin/versions?view=exceptions&saved=1', status_code=303)
