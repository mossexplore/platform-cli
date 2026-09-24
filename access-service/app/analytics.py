"""Aggregate authorization checks for the management dashboard."""
from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import case, func, select, text

from .admin_auth import admin_session
from .models import CallLog, now
from .security import BEIJING, display_time, expiry

router = APIRouter()
GRAINS = {'hour': '小时', 'day': '天', 'week': '周'}


def bounds(begin, end, grain):
    if grain not in GRAINS:
        raise HTTPException(400, '时间粒度无效')
    current = now().replace(microsecond=0)
    if not begin and not end:
        start, finish = current - timedelta(days=7), current
        return start, finish + timedelta(seconds=1)
    if not begin or not end:
        raise HTTPException(400, '请同时填写开始时间和结束时间')
    start, finish = expiry(begin), expiry(end)
    if start and finish and (start.microsecond or finish.microsecond):
        raise HTTPException(400, '时间精度最多到秒')
    if start is None or finish is None or start > finish:
        raise HTTPException(400, '开始时间不能晚于结束时间')
    if finish - start > timedelta(days=90):
        raise HTTPException(400, '时间范围最长为 90 天')
    if grain == 'hour' and finish - start > timedelta(days=14):
        raise HTTPException(400, '按小时分析最长为 14 天，请缩短范围或选择天、周')
    return start, finish + timedelta(seconds=1)


def bucket_expression(db, grain):
    column = CallLog.created_at
    fmt = '%Y-%m-%d %H:00:00' if grain == 'hour' else '%Y-%m-%d'
    if db.bind.dialect.name == 'sqlite':
        local_time = func.datetime(column, '+8 hours')
        return func.strftime(fmt, local_time)
    local_time = func.date_add(column, text('INTERVAL 8 HOUR'))
    return func.date_format(local_time, fmt)


def bucket_key(value, grain):
    if grain != 'week':
        return str(value)
    day = datetime.fromisoformat(str(value))
    return (day - timedelta(days=day.weekday())).date().isoformat()


def trend_rows(db, filters, start, stop, grain):
    step = {'hour': timedelta(hours=1), 'day': timedelta(days=1), 'week': timedelta(weeks=1)}[grain]
    bucket = bucket_expression(db, grain)
    denied = func.sum(case((CallLog.allowed.is_(False), 1), else_=0))
    rows = db.execute(select(bucket, func.count(), denied).where(*filters).group_by(bucket).order_by(bucket)).all()
    counts = {}
    for key, count, rejected in rows:
        group = bucket_key(key, grain)
        previous = counts.get(group, (0, 0))
        counts[group] = (previous[0] + count, previous[1] + (rejected or 0))
    local = start.replace(tzinfo=timezone.utc).astimezone(BEIJING)
    local = local.replace(minute=0, second=0, microsecond=0) if grain == 'hour' else local.replace(hour=0, minute=0, second=0, microsecond=0)
    if grain == 'week':
        local -= timedelta(days=local.weekday())
    last = stop.replace(tzinfo=timezone.utc).astimezone(BEIJING)
    points = []
    while local < last:
        next_local = local + step
        key = local.strftime('%Y-%m-%d %H:00:00' if grain == 'hour' else '%Y-%m-%d')
        total, rejected = counts.get(key, (0, 0))
        bucket_start = max(start, local.astimezone(timezone.utc).replace(tzinfo=None))
        bucket_end = min(stop, next_local.astimezone(timezone.utc).replace(tzinfo=None))
        points.append({'key': key, 'label': local.strftime('%m-%d %H:00' if grain == 'hour' else '%m-%d' if grain == 'day' else '%m-%d 周'),
                       'total': total, 'denied': rejected, 'start': bucket_start, 'stop': bucket_end})
        local = next_local
    return points


def command_series(db, filters, grain, names):
    if not names:
        return {}
    bucket = bucket_expression(db, grain)
    rows = db.execute(select(bucket, CallLog.command, func.count()).where(
        *filters, CallLog.command.in_(names)).group_by(bucket, CallLog.command)).all()
    result = {}
    for key, command, count in rows:
        grouped = result.setdefault(bucket_key(key, grain), {})
        grouped[command] = grouped.get(command, 0) + count
    return result


def top_rows(db, filters, field):
    return db.execute(select(field, func.count().label('total')).where(*filters).group_by(field)
                      .order_by(func.count().desc(), field).limit(10)).all()


def log_link(params, start, stop, **extra):
    query = {'begin': display_time(start).replace(' ', 'T'),
             'end_exclusive': display_time(stop).replace(' ', 'T')}
    for key in ('username', 'environment', 'business_id', 'cli_version'):
        if params.get(key):
            query[key] = params[key]
    query.update(extra)
    return '/cli-permission/admin/calls?' + urlencode(query)


@router.get('/admin/analytics')
def analytics(request: Request, grain: str = Query('day', max_length=8),
              begin: str = Query('', max_length=32), end: str = Query('', max_length=32),
              username: str = Query('', max_length=128), environment: str = Query('', max_length=64),
              business_id: str = Query('', max_length=256),
              cli_version: str = Query('', max_length=64)):
    with request.app.state.sessions() as db:
        try:
            admin, session = admin_session(request, db)
        except HTTPException as exc:
            if exc.status_code == 401:
                return RedirectResponse('/cli-permission/login', status_code=303)
            raise
        start, stop = bounds(begin, end, grain)
        params = dict(username=username, environment=environment,
                      business_id=business_id, cli_version=cli_version)
        filters = [CallLog.created_at >= start, CallLog.created_at < stop]
        for key in ('environment', 'business_id', 'cli_version'):
            if params[key]:
                filters.append(getattr(CallLog, key) == params[key])
        if username:
            filters.append(CallLog.actor.contains(username, autoescape=True))
        denied = func.sum(case((CallLog.allowed.is_(False), 1), else_=0))
        total, rejected, users = db.execute(select(func.count(), denied, func.count(func.distinct(CallLog.actor))).where(*filters)).one()
        rejected = rejected or 0
        points = trend_rows(db, filters, start, stop, grain)
        commands = top_rows(db, filters, CallLog.command)
        chart_commands = [name for name, _ in commands[:5]]
        series = command_series(db, filters, grain, chart_commands)
        chart_points = []
        for point in points:
            values = series.get(point['key'], {})
            chart_points.append({'label': point['label'], 'total': point['total'],
                'allowed': point['total'] - point['denied'], 'denied': point['denied'],
                'commands': [values.get(name, 0) for name in chart_commands],
                'other': point['total'] - sum(values.values()),
                'href': log_link(params, point['start'], point['stop'])})
        chart_distribution = [{'label': name or 'unknown', 'value': count,
            'href': log_link(params, start, stop, command_exact=name)} for name, count in commands[:5]]
        other = total - sum(item['value'] for item in chart_distribution)
        if other:
            chart_distribution.append({'label': '其他命令', 'value': other, 'href': ''})
        chart_ranking = [{'label': name or 'unknown', 'value': count,
            'href': log_link(params, start, stop, command_exact=name)} for name, count in commands]
        actors = top_rows(db, filters, CallLog.actor)
        return request.app.state.templates.TemplateResponse(request=request, name='analytics.html', context={
            'admin': admin, 'csrf': session.csrf, 'tab': 'analytics', 'grain': grain,
            'advanced_active': any(params.values()),
            'begin': display_time(start).replace(' ', 'T'),
            'end': display_time(stop - timedelta(seconds=1)).replace(' ', 'T'),
            'start_label': display_time(start),
            'stop_label': display_time(stop - timedelta(seconds=1)), 'params': params,
            'total': total, 'allowed': total - rejected, 'rejected': rejected,
            'rejection_rate': f'{rejected / total * 100:.1f}' if total else '0.0',
            'users': users, 'points': points,
            'chart': {'points': chart_points, 'commands': [name or 'unknown' for name in chart_commands],
                      'distribution': chart_distribution, 'ranking': chart_ranking, 'grain': GRAINS[grain]},
            'commands': commands, 'actors': actors,
            'log_link': lambda **extra: log_link(params, start, stop, **extra),
            'point_link': lambda point: log_link(params, point['start'], point['stop'])})
