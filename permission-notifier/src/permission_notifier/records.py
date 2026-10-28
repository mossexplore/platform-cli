"""Persistent per-attempt records and Beijing-time history filters."""
import time
import re
from datetime import datetime, timedelta, timezone
from uuid import uuid4
from .record_fields import applicant_fields

BEIJING = timezone(timedelta(hours=8))
TEST_CONTENT = '【测试】权限通知助手连接验证'


def begin(store, task_id, source, uid, content, delivery_id=None):
    record_id = str(uuid4())
    sent_at = time.time()
    def append(data):
        data['state']['send_records'][record_id] = {
            'id': record_id, 'task_id': task_id, 'sent_at': sent_at,
            'source': source, 'uid': uid, 'content': content, 'state': 'sending',
            'delivery_id': delivery_id}
        if delivery_id:
            item = data['state']['tasks'][task_id]['deliveries'][delivery_id]
            item.update(record_id=record_id, sent_at=sent_at)
    store.change(append)
    return record_id


def finish(store, record_id, result):
    def update(data):
        record = data['state']['send_records'][record_id]
        # Never persist arbitrary diagnostic bodies or request credentials.
        record.update({key: result[key] for key in ('state', 'http_status', 'error_code') if key in result})
    store.change(update)


def recover_interrupted(store):
    if store.fault:
        return
    if any(row['state'] == 'sending' for row in store.snapshot()['state']['send_records'].values()):
        def update(data):
            for row in data['state']['send_records'].values():
                if row['state'] == 'sending':
                    row.update(state='uncertain', error_code='INTERRUPTED')
        store.change(update)


def rows(data):
    result = list(data['state']['send_records'].values())
    recorded = {(r['task_id'], r.get('delivery_id')) for r in result if r['source'] == 'permission'}
    # Legacy files had no actual send timestamp. Expose it as unknown rather
    # than substituting application creation, lease renewal or report time.
    for task_id, task in data['state']['tasks'].items():
        for key, item in task.get('deliveries', {}).items():
            if (task_id, key) not in recorded and (item.get('attempts', 0) or item['state'] in ('accepted', 'failed', 'uncertain')):
                result.append({'id': 'legacy:'+task_id+':'+key, 'task_id': task_id,
                    'sent_at': item.get('sent_at'), 'source': 'permission', 'uid': item['uid'],
                    'content': task.get('content', ''), 'state': item['state'], 'delivery_id': key})
    return result


def boundary(value):
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=BEIJING)
        return parsed.timestamp()
    except (ValueError, OverflowError):
        raise ValueError('发送时间无效，请填写有效的北京时间') from None


def query(data, start='', end='', source='', page=1, page_size=10):
    lower, upper = boundary(start), boundary(end)
    if lower is not None and upper is not None and lower > upper:
        raise ValueError('开始时间不能晚于结束时间')
    if source not in ('', 'permission', 'test'):
        raise ValueError('无效来源')
    if page < 1 or not 1 <= page_size <= 100:
        raise ValueError('无效分页参数')
    # Include the whole displayed end second/minute, not only its .000 instant.
    exclusive = None
    if upper is not None:
        precision = re.search(r'[T ]\d{2}:\d{2}(?::\d{2}(\.\d+)?)?', end)
        if precision and precision.group(1):
            exclusive = upper + 10**(-(len(precision.group(1))-1))
        else:
            exclusive = upper + (1 if precision and precision.group(0).count(':') == 2 else 60 if precision else 86400)
    items = [r for r in rows(data) if (not source or r['source'] == source) and
             (lower is None or r['sent_at'] is not None and r['sent_at'] >= lower) and
             (exclusive is None or r['sent_at'] is not None and r['sent_at'] < exclusive)]
    items.sort(key=lambda r: (r['sent_at'] or 0, r['id']), reverse=True)
    total = len(items)
    pages = max(1, (total+page_size-1)//page_size)
    page = min(page, pages)
    selected = []
    for row in items[(page-1)*page_size:page*page_size]:
        entry = dict(row)
        entry.update(applicant_fields(row['source'], row.get('content', '')))
        task = data['state']['tasks'].get(row['task_id'])
        item = task.get('deliveries', {}).get(row.get('delivery_id')) if task else None
        entry['actionable'] = bool(item and (item.get('record_id') == row['id'] or
            row['id'].startswith('legacy:')) and item['state'] in ('failed', 'uncertain', 'retry_wait', 'pending'))
        entry['current_state'] = item['state'] if item else row['state']
        entry['can_migrate'] = bool(task and not task['closed'] and item and
            (item.get('record_id') == row['id'] or row['id'].startswith('legacy:')) and
            task.get('route') != {k: data['config']['message'][k] for k in ('url','sender')})
        selected.append(entry)
    return {'items': selected, 'total': total, 'page': page, 'pages': pages, 'page_size': page_size}
