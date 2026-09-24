"""版本管理列表查询、统计与展示状态；准入规则仍由 version_policy 求值。"""
import json
from datetime import timedelta
from sqlalchemy import case, func, select
from .models import CallLog, Environment, now
from .version_models import VersionPolicy, VersionException
from .pagination import PAGE_SIZE
from .security import display_time

MODES = {'observe': '仅观察', 'warn': '提醒升级', 'enforce': '强制拒绝'}
REASONS = ['CLI_VERSION_TOO_OLD', 'CLI_VERSION_BLOCKED', 'CLI_VERSION_INVALID', 'CLI_PROTOCOL_UNSUPPORTED']


def page_context(db, *, view, days, environment, business_id, q, status, page):
    timestamp = now()
    active = (VersionPolicy.enabled.is_(True), VersionPolicy.deleted_at.is_(None), VersionPolicy.effective_at <= timestamp)
    live_exception = (VersionException.enabled.is_(True), VersionException.expires_at > timestamp)
    recent = select(CallLog).where(CallLog.created_at >= timestamp - timedelta(days=7)).subquery()
    stats = {
        'policies': db.scalar(select(func.count()).select_from(VersionPolicy).where(*active)),
        'calls': db.scalar(select(func.count()).select_from(recent)),
        'denied': db.scalar(select(func.count()).select_from(recent).where(recent.c.reason.in_(REASONS))),
        'exceptions': db.scalar(select(func.count()).select_from(VersionException).where(*live_exception))}
    context = dict(stats=stats, now=timestamp, modes=MODES, view=view, days=days, q=q, status=status,
                   environment=environment, business_id=business_id, policies=[], exceptions=[], rows=[])
    if view == 'usage':
        groups = [CallLog.environment, CallLog.business_id, CallLog.cli_version, CallLog.version_source, CallLog.check_source]
        query = select(*groups, func.count().label('calls'), func.max(CallLog.created_at).label('last_seen'),
            func.sum(case((CallLog.reason.in_(REASONS), 1), else_=0)).label('denied'),
            func.count(func.distinct(CallLog.actor)).label('accounts')).where(CallLog.created_at >= timestamp - timedelta(days=days))
        if environment:
            query = query.where(CallLog.environment == environment)
        if business_id:
            query = query.where(CallLog.business_id.contains(business_id, autoescape=True))
        if q:
            query = query.where(CallLog.cli_version.contains(q, autoescape=True))
        query = query.group_by(*groups)
        if status == 'denied':
            query = query.having(func.sum(case((CallLog.reason.in_(REASONS), 1), else_=0)) > 0)
        ordered = query.order_by(func.max(CallLog.created_at).desc(), *groups)
        key = 'rows'
    else:
        model = VersionPolicy if view == 'policies' else VersionException
        query = select(model)
        if view == 'policies':
            query = query.where(VersionPolicy.deleted_at.is_(None))
        if environment:
            query = query.where(model.environment == environment)
        if business_id:
            query = query.where(model.business_id.contains(business_id, autoescape=True))
        if q:
            field = model.name if view == 'policies' else model.username
            query = query.where(field.contains(q, autoescape=True))
        if view == 'policies':
            filters = {'active': active, 'scheduled': (model.enabled.is_(True), model.effective_at > timestamp),
                       'disabled': (model.enabled.is_(False),)}
        else:
            filters = {'active': live_exception, 'expired': (model.enabled.is_(True), model.expires_at <= timestamp),
                       'disabled': (model.enabled.is_(False),)}
        if status in filters:
            query = query.where(*filters[status])
        ordered = query.order_by(model.id.desc())
        key = view
    count = db.scalar(select(func.count()).select_from(query.subquery()))
    page = min(page, max(1, (count + PAGE_SIZE - 1) // PAGE_SIZE))
    result = db.execute(ordered.offset((page-1)*PAGE_SIZE).limit(PAGE_SIZE))
    items = result.all() if view == 'usage' else result.scalars().all()
    for policy in items if view == 'policies' else []:
        policy.blocked_list = json.loads(policy.blocked_versions)
        policy.copy_fields = {name: getattr(policy, name) for name in ('name','environment','business_id','mode',
            'minimum_version','recommended_version','upgrade_url')}
        policy.copy_fields['blocked_versions'] = ', '.join(policy.blocked_list)
        policy.copy_fields['effective_at'] = ''
        policy.edit_fields = {**policy.copy_fields,
            'effective_at': display_time(policy.effective_at).replace(' ', 'T')}
    context.update({key: items, 'count': count, 'page': page,
        'environments': db.scalars(select(Environment).order_by(Environment.name)).all(),
        'policy_options': db.scalars(select(VersionPolicy).where(
            VersionPolicy.enabled.is_(True), VersionPolicy.deleted_at.is_(None)).order_by(VersionPolicy.id.desc())).all()})
    context['environment_names'] = {item.name: item.display_name for item in context['environments']}
    if view == 'exceptions':
        ids = {item.policy_id for item in items}
        context['policy_names'] = dict(db.execute(select(VersionPolicy.id, VersionPolicy.name).where(VersionPolicy.id.in_(ids))).all())
    return context
