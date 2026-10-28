"""Extract applicant fields only from permission notification message lines."""
import re
from datetime import datetime, timezone, timedelta

BEIJING = timezone(timedelta(hours=8))


def applicant_fields(source, content):
    result = {'applicant_name': '-', 'applicant_account': '-', 'application_time': '-'}
    if source != 'permission' or not isinstance(content, str):
        return result
    labels = {'申请人': 'applicant_name', '账号': 'applicant_account', '申请时间': 'application_time'}
    for label, field in labels.items():
        match = re.search(r'^[ \t]*'+label+r'[ \t]*[:：][ \t]*([^\r\n]+)', content, re.MULTILINE)
        if match and match.group(1).strip():
            result[field] = match.group(1).strip()
    if result['application_time'] != '-':
        try:
            if not re.search(r'\d{2}:\d{2}', result['application_time']):
                raise ValueError('缺少时间')
            value = datetime.fromisoformat(result['application_time'].replace('Z', '+00:00'))
            if value.tzinfo is None:
                value = value.replace(tzinfo=BEIJING)
            result['application_time'] = value.astimezone(BEIJING).strftime('%Y-%m-%d %H:%M:%S')
        except (ValueError, OverflowError):
            result['application_time'] = '-'
    return result
