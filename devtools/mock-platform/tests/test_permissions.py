"""Execute CLI against the actual permission system, then inspect persisted audit."""
import json
import socket
import httpx
import pytest
from sqlalchemy import select, update, delete
from app.models import CallLog, Grant, User, Environment, now
from app.version_models import VersionPolicy
from helpers import initialize
from test_demo import invoke
from wiserec_cli_mock.seeds import uid, business_ids
from wiserec_cli_mock.storage import Store


def logs(service):
    with service.app.state.sessions() as db:
        return db.scalars(select(CallLog).order_by(CallLog.id)).all()


def test_real_permission_audit_and_revocation(tmp_path, permission_service):
    root = initialize(tmp_path/'demo')
    invoke(root, 'train', 'list', '-o', 'json')
    record = logs(permission_service)[-1]
    assert (record.actor, record.environment, record.business_id, record.command, record.allowed) == (
        'demo', 'demo-dev', business_ids('demo-dev')[1], 'ml train list', True)
    assert record.cli_version == '1.0.7.7' and record.invocation_id and record.request_id
    with Store(root).transaction() as db:
        before = Store.items(db, business_ids('demo-dev')[1], 'job')
    with permission_service.app.state.sessions() as db:
        db.execute(update(Grant).values(enabled=False))
        db.commit()
    try:
        invoke(root, 'train', 'start', uid('train'), success=False)
        record = logs(permission_service)[-1]
        assert not record.allowed and record.reason == 'NOT_GRANTED'
        with Store(root).transaction() as db:
            assert Store.items(db, business_ids('demo-dev')[1], 'job') == before
    finally:
        with permission_service.app.state.sessions() as db:
            db.execute(update(Grant).values(enabled=True))
            db.commit()


def test_version_policy_is_server_decision(tmp_path, permission_service):
    root = initialize(tmp_path/'demo')
    with permission_service.app.state.sessions() as db:
        rule = VersionPolicy(name='test-denial', environment='demo-dev', mode='enforce',
                             blocked_versions='["1.0.7.7"]', created_by='test')
        db.add(rule)
        db.commit()
        rule_id = rule.id
    try:
        invoke(root, 'train', 'start', uid('train'), success=False)
        record = logs(permission_service)[-1]
        assert not record.allowed and 'VERSION' in record.reason
    finally:
        with permission_service.app.state.sessions() as db:
            db.execute(delete(VersionPolicy).where(VersionPolicy.id == rule_id))
            db.commit()


def test_unavailable_permissions_prevent_writes_context_stays_offline(tmp_path):
    with socket.socket() as unavailable:
        unavailable.bind(('127.0.0.1', 0))
        root = initialize(tmp_path/'demo', permission_url=f'http://127.0.0.1:{unavailable.getsockname()[1]}')
        invoke(root, 'context', '--json')
        with Store(root).transaction() as db:
            before = Store.items(db, business_ids('demo-dev')[1], 'job')
        invoke(root, 'train', 'start', uid('train'), success=False)
        with Store(root).transaction() as db:
            assert Store.items(db, business_ids('demo-dev')[1], 'job') == before


def test_permission_disabled_and_unregistered_identity_rejected(tmp_path):
    root = initialize(tmp_path/'demo', username='not-granted')
    invoke(root, 'train', 'list', success=False)
    path = root/'config.json'
    data = json.loads(path.read_text())
    data['access_control']['enable'] = False
    path.write_text(json.dumps(data))
    invoke(root, 'train', 'list', success=False)


def test_permission_transport_only_allows_exact_api(tmp_path, permission_service):
    from wiserec_cli_mock.transport import Transport
    root = initialize(tmp_path/'demo')
    with httpx.Client(transport=Transport(root), follow_redirects=True) as client:
        for suffix in ('/cli-permission/admin', '/cli-permission/api/v1/access/check?other=1', '/other'):
            with pytest.raises(httpx.ConnectError):
                client.post(permission_service.url+suffix)
        with pytest.raises(httpx.ConnectError):
            client.get(permission_service.url+'/cli-permission/api/v1/access/check')


def test_initialization_requires_real_service_and_explicit_account(tmp_path):
    from wiserec_cli_mock.workspace import initialize as create
    for url, username in [('https://access.mock.invalid', 'demo'), ('https://access.example.com', ''), ('', 'demo')]:
        with pytest.raises(Exception):
            create(tmp_path/'demo', permission_url=url, username=username)
        assert not (tmp_path/'demo').exists()


@pytest.mark.parametrize('action,arguments', [('advance', []), ('reset', ['--yes']),
                                             ('fault', ['--path', '/ai/example'])])
def test_management_denial_preserves_business_state(tmp_path, action, arguments):
    import subprocess
    import sys
    root = initialize(tmp_path/'demo', username='not-granted')
    before = (root/'state.sqlite3').read_bytes()
    result = subprocess.run([sys.executable, '-m', 'wiserec_cli_mock.manage', '--workspace', str(root),
                             action, *arguments], capture_output=True, text=True, timeout=90)
    assert result.returncode != 0
    assert (root/'state.sqlite3').read_bytes() == before


def test_keepalive_denial_is_recorded(tmp_path, permission_service):
    import os
    import subprocess
    import sys
    root = initialize(tmp_path/'demo', username='not-granted')
    script = '''
import os
from wiserec_cli_mock.bootstrap import activate
activate(os.environ['WISEREC_DEMO_WORKSPACE'])
from wiserec_cli.runtime import Runtime
from wiserec_cli.ping import _probe
from wiserec_cli.access import AccessDeniedError
r=Runtime()
c=r.auth.ensure_credentials()
b=r.business.require_selection(c.profile,c.username).business_id
try:
    _probe(r.config,c.profile,c,b,'permission-test')
except AccessDeniedError:
    raise SystemExit(0)
raise SystemExit('keepalive bypassed permissions')
'''
    result = subprocess.run([sys.executable, '-c', script], env=dict(os.environ, WISEREC_DEMO_WORKSPACE=str(root)),
                            capture_output=True, text=True, timeout=90)
    assert result.returncode == 0, result.stdout+result.stderr
    record = logs(permission_service)[-1]
    assert record.command == 'ml auth ping' and not record.allowed
