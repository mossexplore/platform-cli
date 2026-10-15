"""多人授权预览及原子保存，签名绑定会话、输入和数据库快照。"""
import hashlib
import hmac
import json
import time
import uuid
from datetime import timezone

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field, model_validator
from typing import Literal
from sqlalchemy import select

from .admin_auth import authorize_form, admin_session
from .models import User, Environment, Grant, Audit, now
from .security import expiry, display_time

router = APIRouter()


class EnvironmentEdit(BaseModel):
    environment_id: int = Field(gt=0)
    operation: Literal['keep', 'enable', 'revoke'] = 'keep'
    expiry_mode: Literal['keep', 'forever', 'set'] = 'keep'
    expires_at: str = Field(default='', max_length=32)
    note_mode: Literal['keep', 'set', 'clear'] = 'keep'
    note: str = Field(default='', max_length=1000)

    @model_validator(mode='after')
    def validate_edit(self):
        if self.operation == 'revoke' and (self.expiry_mode != 'keep' or self.note_mode != 'keep'):
            raise ValueError('撤销授权时保留有效期和备注')
        return self


class BulkRequest(BaseModel):
    csrf: str = Field(max_length=64)
    user_ids: list[int] = Field(min_length=1, max_length=100)
    edits: list[EnvironmentEdit] = Field(min_length=1, max_length=100)
    token: str = Field(default='', max_length=200)


def snapshot(grant):
    return None if grant is None else {'enabled': grant.enabled,
        'expires_at': grant.expires_at.replace(tzinfo=timezone.utc).isoformat() if grant.expires_at else None, 'note': grant.note}


def describe(value):
    if value is None:
        return '未授权'
    end = display_time(expiry(value['expires_at'])) if value['expires_at'] else '长期有效'
    state = '已撤销' if not value['enabled'] else '已过期' if value['expires_at'] and expiry(value['expires_at']) <= now() else '已开通'
    return f"{state} · {end} · 备注：{value['note'] or '无'}"


def plan(db, body):
    ids = sorted(set(body.user_ids))
    env_ids = sorted(edit.environment_id for edit in body.edits)
    if len(ids) != len(body.user_ids) or len(set(env_ids)) != len(env_ids) or any(i <= 0 for i in ids):
        raise HTTPException(400, '人员或环境编号无效或重复')
    if len(ids) * len(env_ids) > 2000:
        raise HTTPException(400, '每批最多 2,000 个人员与环境组合，请拆分操作')
    users = db.scalars(select(User).where(User.id.in_(ids)).order_by(User.id).with_for_update()).all()
    envs = db.scalars(select(Environment).where(Environment.id.in_(env_ids)).order_by(Environment.id).with_for_update()).all()
    if len(users) != len(ids) or len(envs) != len(env_ids):
        raise HTTPException(409, '人员或环境已删除，请刷新列表重新选择')
    if any(not env.enabled for env in envs):
        raise HTTPException(409, '所选环境已停用，请重新配置')
    grants = {(g.user_id, g.environment_id): g for g in db.scalars(select(Grant).where(
        Grant.user_id.in_(ids), Grant.environment_id.in_(env_ids)).order_by(Grant.id).with_for_update()).all()}
    edits = {edit.environment_id: edit for edit in body.edits}
    dates = {}
    for edit in body.edits:
        if edit.expiry_mode == 'set':
            end = expiry(edit.expires_at)
            if end is None or end <= now():
                raise HTTPException(400, '指定到期时间必须晚于当前时间，按北京时间填写')
            dates[edit.environment_id] = end.replace(tzinfo=timezone.utc).isoformat()
    changes, warnings = [], []
    counts = {'created': 0, 'updated': 0, 'revoked': 0, 'unchanged': 0}
    for user in users:
        if not user.enabled:
            warnings.append(f'{user.username} 已停用，配置授权后仍不能访问')
        for env in envs:
            edit = edits[env.id]
            grant = grants.get((user.id, env.id))
            before = snapshot(grant)
            after = dict(before) if before else None
            if edit.operation == 'enable':
                after = after or {'enabled': True, 'expires_at': None, 'note': ''}
                after['enabled'] = True
            elif edit.operation == 'revoke' and after:
                after['enabled'] = False
            if after is not None:
                if edit.expiry_mode != 'keep':
                    after['expires_at'] = dates[env.id] if edit.expiry_mode == 'set' else None
                if edit.note_mode != 'keep':
                    after['note'] = edit.note if edit.note_mode == 'set' else ''
            if edit.operation == 'enable' and after and after['expires_at'] and expiry(after['expires_at']) <= now():
                warnings.append(f'{user.username} / {env.name} 仍已过期，需要调整有效期')
            if before == after:
                counts['unchanged'] += 1
                continue
            kind = 'created' if before is None else 'revoked' if before['enabled'] and not after['enabled'] else 'updated'
            counts[kind] += 1
            if edit.operation != 'enable' and after['enabled'] and after['expires_at'] and expiry(after['expires_at']) <= now():
                warnings.append(f'{user.username} / {env.name} 仍已过期，需要调整有效期')
            changes.append({'user_id': user.id, 'environment_id': env.id, 'username': user.username,
                'environment': env.name, 'before': before, 'after': after,
                'before_text': describe(before), 'after_text': describe(after), 'kind': kind})
    state = {'input': {'user_ids': ids, 'edits': [edits[i].model_dump() for i in env_ids]},
        'users': [[u.id, u.username, u.display_name, u.enabled, str(u.updated_at)] for u in users],
        'environments': [[e.id, e.name, e.enabled, str(e.updated_at)] for e in envs],
        'grants': [[u.id, e.id, snapshot(grants.get((u.id, e.id)))] for u in users for e in envs]}
    fingerprint = hashlib.sha256(json.dumps(state, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
    return users, grants, changes, counts, warnings, fingerprint


def signature(actor, session, fingerprint, issued):
    return hmac.new(actor.password_hash.encode(),
        f'{session.token_hash}:{fingerprint}:{issued}'.encode(), hashlib.sha256).hexdigest()


@router.post('/admin/grants/bulk/preview')
def preview(request: Request, body: BulkRequest):
    with request.app.state.sessions() as db:
        actor = authorize_form(request, db, body.csrf)
        _, session = admin_session(request, db)
        users, _, changes, counts, warnings, fingerprint = plan(db, body)
        issued = int(time.time())
        return {'token': f'{issued}.{signature(actor, session, fingerprint, issued)}',
            'changes': changes, 'counts': counts, 'warnings': warnings,
            'affected_users': len({c['user_id'] for c in changes}), 'selected_users': len(users)}


@router.post('/admin/grants/bulk/save')
def save(request: Request, body: BulkRequest):
    with request.app.state.sessions() as db:
        actor = authorize_form(request, db, body.csrf)
        _, session = admin_session(request, db)
        users, grants, changes, counts, _, fingerprint = plan(db, body)
        try:
            issued, signed = body.token.split('.')
            issued = int(issued)
            valid = 0 <= time.time() - issued <= 900 and hmac.compare_digest(
                signed, signature(actor, session, fingerprint, issued))
        except (ValueError, TypeError):
            valid = False
        if not valid:
            raise HTTPException(409, '预览已过期或人员、环境、授权已变化，请重新预览后保存')
        if not changes:
            raise HTTPException(400, '没有实际变更，无需保存')
        batch_id = uuid.uuid4().hex
        affected = set()
        for change in changes:
            key = (change['user_id'], change['environment_id'])
            grant = grants.get(key)
            if grant is None:
                grant = Grant(user_id=key[0], environment_id=key[1])
                db.add(grant)
            after = change['after']
            grant.enabled, grant.expires_at, grant.note = after['enabled'], expiry(after['expires_at']), after['note']
            affected.add(key[0])
            db.add(Audit(actor=actor.username, action='grants.bulk_save', detail=json.dumps({
                'batch_id': batch_id, 'before': change['before'], 'after': dict(after,
                    username=change['username'], name=change['environment'], user_id=key[0], environment_id=key[1])}, ensure_ascii=False)))
        for user in users:
            if user.id in affected:
                user.updated_at, user.updated_by = now(), actor.username
        db.commit()
        return {'batch_id': batch_id, 'counts': counts, 'changed': len(changes)}
