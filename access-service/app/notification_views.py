"""Presentation data for the owner console; protocol values stay unchanged."""
from datetime import timedelta
from sqlalchemy import select, func, or_
from .models import AccessApplication, now
from .notification_models import NotificationTask
from .notification_state import counts
from .pagination import PAGE_SIZE

STATUSES = {
    'pending': ('待处理', 'neutral'), 'processing': ('处理中', 'warning'),
    'retry_wait': ('等待重试', 'warning'), 'sent': ('接口已接受', 'positive'),
    'skipped': ('已跳过', 'neutral'), 'partial': ('部分已接受', 'warning'),
    'failed': ('发送失败', 'danger'), 'uncertain': ('结果不确定', 'warning'),
}
DELIVERIES = {'pending': '待处理', 'sending': '发送中', 'retry_wait': '等待重试',
              'accepted': '接口已接受', 'skipped': '已跳过', 'failed': '失败', 'uncertain': '结果不确定'}
HEALTH = {
    'running': ('运行中', 'positive', '助手正在处理可领取的通知任务。'),
    'paused': ('已暂停', 'warning', '如需继续发送，请在本地助手中恢复通知。'),
    'network_error': ('网络异常', 'danger', '请在本地助手检查服务地址、网络和代理设置。'),
    'auth_error': ('认证异常', 'danger', '请在本地助手核对服务凭据和消息接口凭据。'),
    'worker_error': ('工作线程异常', 'danger', '请检查本地助手的诊断信息。'),
    'storage_error': ('存储异常', 'danger', '请检查本地助手的数据目录和磁盘空间。'),
    'needs_attention': ('需要处理', 'warning', '请在本地助手核对失败或结果不确定的接收对象。'),
    'unconfigured': ('未完成配置', 'neutral', '请先在本地助手完成连接和消息设置。'),
}


def client_summary(client, at=None):
    at = at or now()
    if not client.token_hash:
        credential = ('已撤销' if client.credential_generation else '未生成', 'neutral', '请生成助手 Token 并在本地绑定。')
    elif client.installation_id:
        credential = (('有效', 'positive', '凭据已绑定当前助手。') if client.expires_at and client.expires_at > at else
                      ('已过期', 'danger', '请重新生成 Token 并在本地助手重新绑定。'))
    else:
        credential = (('待绑定', 'warning', '请在生成后30分钟内将 Token 绑定到本地助手。') if client.bind_deadline and client.bind_deadline > at else
                      ('绑定已超时', 'danger', '请重新生成 Token 并及时绑定。'))
    live = bool(client.last_seen_at and client.last_seen_at > at - timedelta(seconds=180))
    valid = credential[0] == '有效'
    connection = ('连接正常', 'positive', '最近3分钟收到过助手心跳，不代表消息已送达。') if live and valid else (
        ('尚未连接', 'neutral', '完成凭据绑定后，助手会定期上报状态。') if not client.last_seen_at else
        ('连接超时', 'warning', '最近3分钟未收到有效连接，请检查本地助手。'))
    if not valid and client.last_seen_at:
        connection = ('连接待恢复', 'warning', '请先处理凭据状态，旧心跳不代表连接可用。')
    health = HEALTH.get(client.health_code, ('状态未知', 'neutral', '等待助手上报运行状态。'))
    if not live or not valid:
        health = ('等待连接', 'neutral', '连接恢复后可确认助手当前运行状态。')
    enabled = ('已开启', 'positive', '允许生成和领取新通知任务。') if client.enabled else (
        '已关闭', 'neutral', '停止生成和领取新任务，已领取任务仍可完成。')
    return [dict(title=title, label=value[0], tone=value[1], hint=value[2]) for title, value in
            [('助手连接', connection), ('助手运行', health), ('通知开关', enabled), ('助手凭据', credential)]]


def task_list(db, page=1, q='', status=''):
    query = select(NotificationTask, AccessApplication).outerjoin(
        AccessApplication, AccessApplication.id == NotificationTask.application_id)
    if status:
        query = query.where(NotificationTask.status == status)
    if q:
        # User search text is literal, not a SQL wildcard expression.
        query = query.where(or_(AccessApplication.username.contains(q, autoescape=True),
                                AccessApplication.display_name.contains(q, autoescape=True),
                                NotificationTask.application_id == int(q) if q.isdecimal() and len(q) < 16 else False))
    total = int(db.scalar(select(func.count()).select_from(query.subquery())) or 0)
    page = min(page, max(1, (total + PAGE_SIZE - 1) // PAGE_SIZE))
    rows = []
    for task, application in db.execute(query.order_by(NotificationTask.created_at.desc(), NotificationTask.id.desc())
                                        .offset((page - 1) * PAGE_SIZE).limit(PAGE_SIZE)):
        totals = counts(task)
        failed = int(totals.get('failed', 0))
        pending = bool(application and application.status == 'pending')
        label, tone = STATUSES.get(task.status, ('未知状态', 'neutral'))
        rows.append(dict(task=task, application=application, label=label, tone=tone,
                         summary=' · '.join(f'{text} {int(totals[key])}' for key, text in DELIVERIES.items() if totals.get(key)) or '等待助手准备接收对象',
                         failed=failed, can_retry=bool(failed and pending), uncertain=int(totals.get('uncertain', 0)),
                         application_pending=pending))
    return dict(rows=rows, count=total, page=page, q=q, status=status, statuses=STATUSES)
