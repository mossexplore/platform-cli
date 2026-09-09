"""Application decisions and authorization changes in one transaction."""
import json
from fastapi import HTTPException
from sqlalchemy import select, update
from .models import AccessApplication, Audit, Environment, Grant, User, now
from .security import digest, expiry


def identity(username, display_name):
    username, display_name = username.strip(), display_name.strip()
    if not username or not display_name or any(c.isspace() for c in username):
        raise HTTPException(400, '请填写正确的 W3 账号和姓名；账号不能包含空格')
    return username, display_name


def review_state(db, username, application_id, lock=False):
    env_query = select(Environment).where(Environment.enabled.is_(True)).order_by(Environment.id)
    user_query = select(User).where(User.username == username)
    if lock:
        env_query, user_query = env_query.with_for_update(), user_query.with_for_update()
    environments = db.scalars(env_query).all()
    user = db.scalar(user_query)
    grants = []
    if user:
        query = select(Grant).where(Grant.user_id == user.id).order_by(Grant.id)
        grants = db.scalars(query.with_for_update() if lock else query).all()
    duplicate_query = select(AccessApplication.id).where(
        AccessApplication.pending_username == username, AccessApplication.id != application_id)
    duplicate = db.scalar(duplicate_query.with_for_update() if lock else duplicate_query)
    state = {
        'environments': [{'id': e.id, 'name': e.name, 'display_name': e.display_name,
                          'origin': e.platform_origin} for e in environments],
        'user': {'id': user.id, 'username': user.username, 'name': user.display_name,
                 'enabled': user.enabled} if user else None,
        'grants': [{'id': g.id, 'environment_id': g.environment_id, 'enabled': g.enabled,
                    'expires_at': g.expires_at.isoformat() if g.expires_at else None,
                    'note': g.note} for g in grants],
        'duplicate': duplicate,
    }
    return state, user, grants


def fingerprint(state):
    return digest(json.dumps(state, ensure_ascii=False, sort_keys=True))


def claim(db, application_id):
    result = db.execute(update(AccessApplication).where(
        AccessApplication.id == application_id, AccessApplication.status == 'pending'
    ).values(status='processing'))
    if result.rowcount != 1:
        raise HTTPException(409, '申请不存在或已审批，请刷新列表')
    return db.get(AccessApplication, application_id)


def approve(db, actor, application_id, username, display_name, selected, expires_at,
            snapshot, confirm_existing, update_name, restore_grants):
    username, display_name = identity(username, display_name)
    item = claim(db, application_id)
    state, user, grants = review_state(db, username, application_id, lock=True)
    if fingerprint(state) != snapshot:
        raise HTTPException(409, '环境或人员授权已变化，请返回申请详情重新核对')
    if state['duplicate']:
        raise HTTPException(409, '修正后的账号存在其他待审批申请，请先处理重复申请')
    if user and not user.enabled:
        raise HTTPException(400, '该人员已停用，请先在人员与授权中处理停用状态')
    if user and not confirm_existing:
        raise HTTPException(400, '请确认关联已有人员')
    selected = set(selected)
    available = {str(e['id']): e for e in state['environments']}
    if not selected or not selected.issubset(available):
        raise HTTPException(400, '请至少选择一个启用环境')
    expires = expiry(expires_at)
    if expires and expires <= now():
        raise HTTPException(400, '授权到期时间必须晚于当前时间')
    before = state
    if user is None:
        user = User(username=username, display_name=display_name, enabled=True,
                    updated_by=actor.username)
        db.add(user)
        db.flush()
    elif update_name:
        user.display_name = display_name
    existing = {g.environment_id: g for g in grants}
    result = []
    for key in sorted(selected, key=int):
        env = available[key]
        grant = existing.get(env['id'])
        active = grant and grant.enabled and (grant.expires_at is None or grant.expires_at > now())
        if grant and not active and not restore_grants:
            raise HTTPException(400, '所选环境有已撤销或过期授权，请明确确认重新开通')
        if grant is None:
            grant = Grant(user_id=user.id, environment_id=env['id'], enabled=True,
                          expires_at=expires, note=f'权限申请 #{item.id}')
            db.add(grant)
        elif not active:
            grant.enabled, grant.expires_at = True, expires
        result.append({'environment': env['name'], 'environment_id': env['id'],
                       'expires_at': grant.expires_at.isoformat() if grant.expires_at else None,
                       'action': 'preserved' if active else 'granted'})
    user.updated_at, user.updated_by = now(), actor.username
    item.status, item.pending_username = 'approved', None
    item.reviewed_at, item.reviewed_by = now(), actor.username
    item.approved_username, item.approved_name = username, display_name
    item.user_id = user.id
    item.result = json.dumps({'environments': result, 'person_name': user.display_name}, ensure_ascii=False)
    db.add(Audit(actor=actor.username, action='applications.approve', detail=json.dumps({
        'application_id': item.id, 'original': {'username': item.username, 'name': item.display_name},
        'corrected': {'username': username, 'name': display_name}, 'before': before,
        'after': json.loads(item.result), 'user_id': user.id}, ensure_ascii=False)))
    db.commit()


def reject(db, actor, application_id, reason):
    if not reason.strip():
        raise HTTPException(400, '拒绝申请时必须填写原因')
    item = claim(db, application_id)
    item.status, item.pending_username = 'rejected', None
    item.reason = reason.strip()
    item.reviewed_at, item.reviewed_by = now(), actor.username
    db.add(Audit(actor=actor.username, action='applications.reject', detail=json.dumps({
        'application_id': item.id, 'username': item.username, 'name': item.display_name,
        'reason': item.reason}, ensure_ascii=False)))
    db.commit()
