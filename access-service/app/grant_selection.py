"""按勾选状态配置环境授权，不覆盖已有有效期及备注。"""
import json
from fastapi import APIRouter, Form, HTTPException, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from .admin_auth import authorize_form
from .models import User, Environment, Grant, Audit, now

router = APIRouter()


@router.post('/admin/users/{user_id}/environments')
def configure(request: Request, user_id: int, csrf: str = Form(max_length=64),
              environments: list[str] = Form(default=[])):
    with request.app.state.sessions() as db:
        actor = authorize_form(request, db, csrf)
        user = db.scalar(select(User).where(User.id == user_id).with_for_update())
        if user is None:
            raise HTTPException(404, '人员不存在，请刷新列表')
        selected = set(environments)
        available = db.scalars(select(Environment).where(Environment.enabled.is_(True))).all()
        if not selected.issubset({env.name for env in available}):
            raise HTTPException(400, '所选环境不存在或已停用，请刷新页面后重试')
        grants = {item.environment_id: item for item in db.scalars(
            select(Grant).where(Grant.user_id == user_id).with_for_update()).all()}
        for env in available:
            item = grants.get(env.id)
            enabled = env.name in selected
            if item is None and not enabled:
                continue
            if item is not None and item.enabled == enabled:
                continue
            before = {'enabled': item.enabled, 'environment_id': env.id, 'user_id': user_id} if item else None
            if item is None:
                item = Grant(user_id=user_id, environment_id=env.id, enabled=True)
                db.add(item)
            else:
                item.enabled = enabled
            user.updated_at, user.updated_by = now(), actor.username
            db.add(Audit(actor=actor.username, action='grants.selection_save', detail=json.dumps({
                'before': before, 'after': {'username': user.username, 'name': env.name,
                    'enabled': enabled, 'environment_id': env.id, 'user_id': user_id}}, ensure_ascii=False)))
        db.commit()
    return RedirectResponse('/cli-permission/admin?tab=users&saved=1', status_code=303)
