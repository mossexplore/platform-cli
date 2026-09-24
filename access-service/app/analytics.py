"""Aggregate authorization checks for the management dashboard."""
from datetime import timedelta, timezone
from urllib.parse import urlencode

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import case, func, select, text

from .admin_auth import admin_session
from .models import CallLog, now
from .security import BEIJING, display_time, expiry

router = APIRouter()
PERIODS = {'24h': timedelta(hours=24), '7d': timedelta(days=7), '30d': timedelta(days=30)}
REASONS = {
    'ENVIRONMENT_DISABLED': '环境不存在或已停用',
    'ENVIRONMENT_MISMATCH': '环境与平台地址不匹配',
    'USER_DISABLED': '账号不存在或已停用',
    'NOT_GRANTED': '未获得当前环境授权',
    'GRANT_EXPIRED': '当前环境授权已过期',
    'CLI_VERSION_TOO_OLD': 'CLI 版本低于最低要求',
    'CLI_VERSION_BLOCKED': 'CLI 版本已停用',
    'CLI_VERSION_INVALID': 'CLI 版本格式不合法',
    'CLI_PROTOCOL_UNSUPPORTED': 'CLI 上报协议不受支持',
}


def bounds(period, begin, end):
    if period not in (*PERIODS, 'custom'):
        raise HTTPException(400, '时间范围无效')
    current = now().replace(microsecond=0)
    if period != 'custom':
        return current - PERIODS[period], current + timedelta(seconds=1)
    if not begin or not end:
        raise HTTPException(400, '自定义时间范围需要开始和结束时间')
    start, finish = expiry(begin), expiry(end)
    if start and finish and (start.microsecond or finish.microsecond):
        raise HTTPException(400, '时间精度最多到秒')
    if start is None or finish is None or start > finish:
        raise HTTPException(400, '开始时间不能晚于结束时间')
    if finish - start > timedelta(days=90):
        raise HTTPException(400, '自定义时间范围最长为 90 天')
    return start, finish + timedelta(seconds=1)


def bucket_expression(db, hourly):
    column = CallLog.created_at
    if db.bind.dialect.name == 'sqlite':
        local_time = func.datetime(column, '+8 hours')
        return func.strftime('%Y-%m-%d %H:00:00' if hourly else '%Y-%m-%d', local_time)
    local_time = func.date_add(column, text('INTERVAL 8 HOUR'))
    return func.date_format(local_time, '%Y-%m-%d %H:00:00' if hourly else '%Y-%m-%d')


def trend_rows(db, filters, start, stop):
    hourly = stop - start <= timedelta(hours=48)
    step = timedelta(hours=1) if hourly else timedelta(days=1)
    bucket = bucket_expression(db, hourly)
    denied = func.sum(case((CallLog.allowed.is_(False), 1), else_=0))
    rows = db.execute(select(bucket, func.count(), denied).where(*filters).group_by(bucket).order_by(bucket)).all()
    counts = {str(key): (count, rejected or 0) for key, count, rejected in rows}
    local = start.replace(tzinfo=timezone.utc).astimezone(BEIJING)
    local = local.replace(minute=0, second=0, microsecond=0) if hourly else local.replace(hour=0, minute=0, second=0, microsecond=0)
    last = stop.replace(tzinfo=timezone.utc).astimezone(BEIJING)
    points = []
    while local < last:
        next_local = local + step
        key = local.strftime('%Y-%m-%d %H:00:00' if hourly else '%Y-%m-%d')
        total, rejected = counts.get(key, (0, 0))
        bucket_start = max(start, local.astimezone(timezone.utc).replace(tzinfo=None))
        bucket_end = min(stop, next_local.astimezone(timezone.utc).replace(tzinfo=None))
        points.append({'label': local.strftime('%m-%d %H:00' if hourly else '%m-%d'),
                       'total': total, 'denied': rejected, 'start': bucket_start, 'stop': bucket_end})
        local = next_local
    return points


def top_rows(db, filters, field):
    return db.execute(select(field, func.count().label('total')).where(*filters).group_by(field)
                      .order_by(func.count().desc(), field).limit(10)).all()


def log_link(params, start, stop, **extra):
    query = {'begin': display_time(start).replace(' ', 'T'),
             'end_exclusive': display_time(stop).replace(' ', 'T')}
    for key in ('username', 'environment', 'command', 'business_id', 'cli_version'):
        if params.get(key):
            query[key] = params[key]
    query.update(extra)
    return '/cli-permission/admin/calls?' + urlencode(query)


@router.get('/admin/analytics')
def analytics(request: Request, period: str = Query('7d', max_length=16),
              begin: str = Query('', max_length=32), end: str = Query('', max_length=32),
              username: str = Query('', max_length=128), environment: str = Query('', max_length=64),
              command: str = Query('', max_length=128), business_id: str = Query('', max_length=256),
              cli_version: str = Query('', max_length=64)):
    with request.app.state.sessions() as db:
        try:
            admin, session = admin_session(request, db)
        except HTTPException as exc:
            if exc.status_code == 401:
                return RedirectResponse('/cli-permission/login', status_code=303)
            raise
        start, stop = bounds(period, begin, end)
        params = dict(username=username, environment=environment, command=command,
                      business_id=business_id, cli_version=cli_version)
        filters = [CallLog.created_at >= start, CallLog.created_at < stop]
        for key in ('environment', 'business_id', 'cli_version'):
            if params[key]:
                filters.append(getattr(CallLog, key) == params[key])
        for key, field in (('username', CallLog.actor), ('command', CallLog.command)):
            if params[key]:
                filters.append(field.contains(params[key], autoescape=True))
        denied = func.sum(case((CallLog.allowed.is_(False), 1), else_=0))
        total, rejected, users = db.execute(select(func.count(), denied, func.count(func.distinct(CallLog.actor))).where(*filters)).one()
        rejected = rejected or 0
        points = trend_rows(db, filters, start, stop)
        max_point = max((item['total'] for item in points), default=0) or 1
        commands = top_rows(db, filters, CallLog.command)
        actors = top_rows(db, filters, CallLog.actor)
        denied_filters = [*filters, CallLog.allowed.is_(False)]
        reasons = top_rows(db, denied_filters, CallLog.reason)
        denied_environments = top_rows(db, denied_filters, CallLog.environment)
        denied_commands = top_rows(db, denied_filters, CallLog.command)
        return request.app.state.templates.TemplateResponse(request=request, name='analytics.html', context={
            'admin': admin, 'csrf': session.csrf, 'tab': 'analytics', 'period': period,
            'begin': begin, 'end': end, 'start_label': display_time(start),
            'stop_label': display_time(stop - timedelta(seconds=1)), 'params': params,
            'total': total, 'allowed': total - rejected, 'rejected': rejected,
            'rejection_rate': f'{rejected / total * 100:.1f}' if total else '0.0',
            'users': users, 'points': points, 'max_point': max_point,
            'commands': commands, 'actors': actors, 'reasons': reasons,
            'denied_environments': denied_environments, 'denied_commands': denied_commands,
            'reason_labels': REASONS, 'log_link': lambda **extra: log_link(params, start, stop, **extra),
            'point_link': lambda point: log_link(params, point['start'], point['stop'])})
