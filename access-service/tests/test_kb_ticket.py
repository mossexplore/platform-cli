import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from sqlalchemy import select

from app import kb_ticket
from app.models import CallLog
from test_service import system, check, login
from test_command_policy import save


def test_gateway_vector():
    path = Path(__file__).resolve().parents[2] / 'kb-gateway/testdata/ticket.json'
    expected = json.loads(path.read_text())
    settings = SimpleNamespace(kb_ticket_ak=expected['ak'], kb_ticket_sk=expected.pop('key'))
    with patch.object(kb_ticket.time, 'time', return_value=expected['exp'] - 300), \
         patch.object(kb_ticket.uuid, 'uuid4', return_value=expected['ticket_id']):
        assert kb_ticket.issue(settings, expected['username'], expected['environment'], expected['action']) == expected


@pytest.mark.parametrize('ban', ['ml kb', 'ml kb page show'])
def test_ticket_and_audit_follow_command_policy(system, ban):
    app, client, _ = system
    config = app.state.settings
    config.kb_ticket_ak, config.kb_ticket_sk = 'test', 's' * 32
    command = 'ml kb page show'
    allowed = check(client, command=command, full_command=command + ' token=hidden').json()
    ticket = allowed['kb_ticket']
    assert allowed['allowed'] and ticket['action'] == 'kb_page_show'
    with app.state.sessions() as db:
        log = db.scalars(select(CallLog)).one()
        assert json.loads(log.version_decision)['kb_ticket_id'] == ticket['ticket_id']
        assert 'hidden' not in log.full_command
    assert save(app, client, login(client), [ban]).status_code == 303
    denied = check(client, command=command).json()
    assert denied['reason'] == 'COMMAND_DISABLED' and 'kb_ticket' not in denied
