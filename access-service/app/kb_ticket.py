"""Action-scoped shared Wiki admission tickets."""
import hashlib
import hmac
import re
import time
import uuid
from urllib.parse import quote

ACTIONS = {'ml kb list': 'kb_list', 'ml kb page list': 'kb_page_list',
           'ml kb search': 'kb_search', 'ml kb page show': 'kb_page_show'}


def audit_command(value):
    # Free-form text cannot reliably be scrubbed once a credential label occurs.
    match = re.search(r'(?i)cookie|csrf|authorization|token|password|secret|api[-_ ]?key|密钥|密码', value)
    if match:
        value = value[:match.start()] + '[已脱敏]'
    return ' '.join(value.split())[:256]


def issue(settings, username, environment, action):
    if not settings.kb_ticket_ak or not settings.kb_ticket_sk:
        return None
    ticket_id = str(uuid.uuid4())
    exp = int(time.time()) + 300
    fields = ['v1', settings.kb_ticket_ak, ticket_id, username, environment, action, str(exp)]
    payload = '\n'.join(quote(field, safe='') for field in fields).encode()
    sig = hmac.new(settings.kb_ticket_sk.encode(), payload, hashlib.sha256).hexdigest()
    return dict(ak=settings.kb_ticket_ak, ticket_id=ticket_id, username=username,
                environment=environment, action=action, exp=exp, sig=sig)
