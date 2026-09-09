"""调用日志查询；全部筛选在数据库完成，管理会话验证后才能访问。"""
from fastapi import APIRouter, Query, Request, HTTPException
from fastapi.responses import RedirectResponse
from sqlalchemy import select, func
from .admin_auth import admin_session
from .models import CallLog
from .security import expiry

router = APIRouter()


@router.get('/admin/calls')
def calls(request: Request, username: str = Query('', max_length=128),
          environment: str = Query('', max_length=64), command: str = Query('', max_length=128),
          result: str = '', begin: str = Query('', max_length=32), end: str = Query('', max_length=32),
          page: int = Query(1, ge=1)):
    if result not in ('', 'allowed', 'denied'):
        raise HTTPException(400, '授权结果筛选无效')
    start, stop = expiry(begin), expiry(end)
    if start and stop and start > stop:
        raise HTTPException(400, '开始时间不能晚于结束时间')
    with request.app.state.sessions() as db:
        try:
            admin, session = admin_session(request, db)
        except HTTPException as exc:
            if exc.status_code == 401:
                return RedirectResponse('/cli-permission/login', status_code=303)
            raise
        query = select(CallLog)
        if username:
            query = query.where(CallLog.actor.contains(username, autoescape=True))
        if environment:
            query = query.where(CallLog.environment == environment)
        if command:
            query = query.where(CallLog.command.contains(command, autoescape=True))
        if result:
            query = query.where(CallLog.allowed.is_(result == 'allowed'))
        if start:
            query = query.where(CallLog.created_at >= start)
        if stop:
            query = query.where(CallLog.created_at <= stop)
        count = db.scalar(select(func.count()).select_from(query.subquery()))
        items = db.scalars(query.order_by(CallLog.created_at.desc(), CallLog.id.desc()).offset((page-1)*20).limit(20)).all()
        return request.app.state.templates.TemplateResponse(request=request, name='calls.html', context={
            'admin': admin, 'csrf': session.csrf, 'items': items, 'count': count, 'page': page,
            'username': username, 'environment': environment, 'command': command, 'result': result,
            'begin': begin, 'end': end,
            'previous': str(request.url.include_query_params(page=page-1)),
            'next': str(request.url.include_query_params(page=page+1))})
