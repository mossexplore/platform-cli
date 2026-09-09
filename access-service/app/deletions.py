"""人员及环境物理删除：精确确认、关联授权清理与审计原子提交。"""
import json
from fastapi import APIRouter, Form, HTTPException, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import delete, select, update
from .admin_auth import authorize_form
from .models import User, Environment, Grant, Audit, now

router = APIRouter()


@router.post('/admin/{resource}/{item_id}/delete')
def remove(request: Request, resource: str, item_id: int,
           csrf: str = Form(max_length=64), confirmation: str = Form('', max_length=16)):
    if resource not in ('users', 'environments'):
        raise HTTPException(404, '不支持删除此类记录')
    with request.app.state.sessions() as db:
        admin = authorize_form(request, db, csrf)
        if confirmation != 'yes':
            raise HTTPException(400, '请输入小写 yes 确认删除')
        model = User if resource == 'users' else Environment
        item = db.scalar(select(model).where(model.id == item_id).with_for_update())
        if item is None:
            raise HTTPException(404, '记录不存在或已被删除，请刷新列表')
        before = {column.name: getattr(item, column.name) for column in model.__table__.columns}
        condition = Grant.user_id == item_id if resource == 'users' else Grant.environment_id == item_id
        if resource == 'environments':
            affected = select(Grant.user_id).where(condition)
            db.execute(update(User).where(User.id.in_(affected)).values(updated_at=now(), updated_by=admin.username))
        removed = db.execute(delete(Grant).where(condition)).rowcount
        db.delete(item)
        db.add(Audit(actor=admin.username, action=resource+'.delete', detail=json.dumps(
            {'before': before, 'after': {}, 'removed_grants': removed}, ensure_ascii=False, default=str)))
        db.commit()
    return RedirectResponse('/cli-permission/admin?tab='+resource+'&deleted=1', status_code=303)
