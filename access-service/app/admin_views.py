"""管理台查询、状态与审计展示。"""
import json
from datetime import timedelta
from sqlalchemy import select, func, or_, and_
from .models import User, Environment, Grant, now


def grant_active(at):
    return and_(Grant.enabled.is_(True), User.enabled.is_(True), Environment.enabled.is_(True),
                or_(Grant.expires_at.is_(None), Grant.expires_at > at))


def overview(db):
    at = now()
    count = lambda model: db.scalar(select(func.count()).select_from(model))
    active = select(func.count()).select_from(Grant).join(User).join(Environment).where(grant_active(at))
    return {'users': count(User), 'environments': count(Environment),
            'active': db.scalar(active),
            'expiring': db.scalar(active.where(Grant.expires_at <= at + timedelta(days=7)))}


def filter_status(query, tab, status):
    if not status or tab == 'audit':
        return query
    if tab != 'grants':
        model = User if tab == 'users' else Environment
        return query.where(model.enabled.is_(status == 'enabled'))
    at = now()
    if status == 'active':
        return query.where(grant_active(at))
    if status == 'expired':
        return query.where(Grant.expires_at <= at)
    if status == 'expiring':
        return query.where(grant_active(at), Grant.expires_at <= at + timedelta(days=7))
    return query.where(or_(Grant.enabled.is_(False), User.enabled.is_(False), Environment.enabled.is_(False)))


def grant_state(item, user, environment):
    if not user.enabled:
        return ('neutral', '人员已停用')
    if not environment.enabled:
        return ('neutral', '环境已停用')
    if not item.enabled:
        return ('neutral', '已撤销')
    if item.expires_at and item.expires_at <= now():
        return ('danger', '已过期')
    if item.expires_at and item.expires_at <= now() + timedelta(days=7):
        return ('warning', '即将到期')
    return ('positive', '生效中')


ACTIONS = {'administrators.reset_password': '重置管理员密码', 'administrators.create': '创建管理员', 'administrators.enable': '启用管理员', 'administrators.disable': '停用管理员', 'login': '登录管理台', 'logout': '退出登录', 'login_failed': '登录失败',
           'users.save': '更新人员', 'environments.save': '更新环境',
           'grants.save': '更新授权', 'grants.batch_save': '批量配置授权'}
FIELDS = {'role': '管理角色', 'username': '账号', 'display_name': '名称', 'enabled': '启用状态',
          'name': '环境标识', 'platform_origin': '平台地址', 'expires_at': '到期时间',
          'note': '备注', 'user_id': '人员编号', 'environment_id': '环境编号'}


def audit_detail(item):
    try:
        data = json.loads(item.detail)
    except (ValueError, TypeError):
        return {'label': ACTIONS.get(item.action, item.action), 'summary': item.detail, 'changes': []}
    if not isinstance(data, dict) or not isinstance(data.get('after'), dict):
        return {'label': ACTIONS.get(item.action, item.action), 'summary': item.detail, 'changes': []}
    after, before = data['after'], data.get('before') or {}
    def display(key, value):
        if value in (None, 'None', ''):
            return '—'
        if key == 'role':
            return {'admin': '管理员', 'super_admin': '超级管理员'}.get(value, value)
        if key == 'enabled':
            return '启用' if value in ('True', True) else '停用'
        if key == 'expires_at':
            from datetime import datetime
            from .security import display_time
            try:
                return display_time(datetime.fromisoformat(value))
            except (ValueError, TypeError):
                pass
        return value
    changes = [{'field': label, 'before': display(key, before.get(key)), 'after': display(key, after.get(key))}
               for key, label in FIELDS.items() if key in after and before.get(key) != after[key]]
    return {'label': ACTIONS.get(item.action, item.action),
            'summary': ('新增' if not before else '修改') + ' · ' + str(after.get('username') or after.get('name') or '环境授权'),
            'changes': changes}
