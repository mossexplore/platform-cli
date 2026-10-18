"""Network, directory, auth, concurrency and reset failure boundaries."""
import json
from concurrent.futures import ThreadPoolExecutor
import httpx
import pytest
from wiserec_cli_mock.workspace import checked
from helpers import initialize
from wiserec_cli_mock.transport import Transport, MAX_UPLOAD
from wiserec_cli_mock.storage import Store
from wiserec_cli_mock.seeds import business_ids, uid
from test_demo import invoke


def test_transport_scope_method_and_upload_limits(tmp_path):
    root = initialize(tmp_path/'demo')
    scope = business_ids('demo-dev')[1]
    headers = {'businessid': scope, 'cookie': 'demo-session', 'csrftoken': 'demo-csrf'}
    with httpx.Client(transport=Transport(root), base_url='https://demo-dev.mock.invalid', headers=headers) as client:
        assert client.get('/ai/backend/modelDev/modelTrain/list').status_code == 501
        assert client.post('/unimplemented/startScheduleTask').status_code == 501
        assert client.post('/ai/backend/modelDev/modelTrain/list', headers={'businessid': business_ids('demo-test')[1]}).status_code == 403
        assert client.post('/ai/backend/modelDev/modelTrain/list', headers={'cookie': 'foreign'}).status_code == 401
        assert client.post('/ai/backend/modelDev/modelTrain/list', json={'data': {'businessId': 'foreign'}}).status_code == 403
        response = client.post('/ai/backend/mtp/dataSet/file/upload', content=b'x'*(MAX_UPLOAD+1))
        assert response.status_code == 413
        for url in ('https://example.com', 'http://demo-dev.mock.invalid', 'https://demo-dev.mock.invalid:9999'):
            with pytest.raises(httpx.ConnectError):
                client.get(url)


def test_concurrent_writes_are_persistent(tmp_path):
    root = initialize(tmp_path/'demo')
    scope = business_ids('demo-dev')[1]
    def start(_):
        with httpx.Client(transport=Transport(root), base_url='https://demo-dev.mock.invalid',
                          headers={'businessid': scope, 'cookie': 'demo-session', 'csrftoken': 'demo-csrf'}) as client:
            response = client.post('/ai/backend/modelDev/modelTrain/startScheduleTask', json={'data': {'taskId': uid('train')}})
            assert response.status_code == 200
            return response.json()['result']['data']['jobId']
    with ThreadPoolExecutor(max_workers=4) as pool:
        jobs = list(pool.map(start, range(8)))
    assert len(set(jobs)) == 8
    with Store(root).transaction() as db:
        assert set(jobs) <= {j['jobId'] for j in Store.items(db, scope, 'job')}


def test_symlink_and_overwrite_rejected(tmp_path):
    root = initialize(tmp_path/'demo')
    with pytest.raises(ValueError):
        initialize(root)
    outside = tmp_path/'outside'
    outside.mkdir()
    (outside/'keep.txt').write_text('production')
    (root/'link').symlink_to(outside, target_is_directory=True)
    with pytest.raises(ValueError):
        checked(root)
    assert (outside/'keep.txt').read_text() == 'production'


def test_expired_session_refresh_and_no_json_pollution(tmp_path):
    root = initialize(tmp_path/'demo', 'expired-session')
    invoke(root, 'login')
    assert 'expired' in invoke(root, 'auth', 'status').stdout
    result = invoke(root, 'train', 'list', '-o', 'json')
    assert json.loads(result.stdout)['count'] == 25
    assert 'valid' in invoke(root, 'auth', 'status').stdout


def test_missing_extension_does_not_affect_production(tmp_path):
    import os
    import subprocess
    import sys
    script = '''
import sys
class Block:
    def find_spec(self, fullname, *args):
        if fullname.startswith('wiserec_cli_mock'):
            raise ImportError('extension intentionally broken')
sys.meta_path.insert(0, Block())
from wiserec_cli.cli import run
run()
'''
    result = subprocess.run([sys.executable, '-c', script, '--version'], text=True, capture_output=True,
                            env=dict(os.environ, WISEREC_DEMO_WORKSPACE=str(tmp_path)))
    assert result.returncode == 0 and '1.0.7.2' in result.stdout


def test_worker_transport_and_reset_are_isolated(tmp_path):
    import os
    import subprocess
    import sys
    root = initialize(tmp_path/'demo')
    invoke(root, 'login')
    script = '''
import os
from wiserec_cli_mock.bootstrap import activate
activate(os.environ['WISEREC_DEMO_WORKSPACE'])
from wiserec_cli.runtime import Runtime
from wiserec_cli.ping import _probe
r=Runtime()
c=r.credentials.load(r.config.current_name)
b=r.business.require_selection(c.profile,c.username).business_id
print(_probe(r.config,c.profile,c,b,'demo-probe'))
'''
    result = subprocess.run([sys.executable, '-c', script], capture_output=True, text=True,
                            env=dict(os.environ, WISEREC_DEMO_WORKSPACE=str(root)))
    assert result.returncode == 0, result.stderr
    external = tmp_path/'external.txt'
    external.write_text('keep')
    (root/'exports/keep.txt').write_text('keep export')
    command = [sys.executable, '-m', 'wiserec_cli_mock.manage', '--workspace', str(root), 'reset', '--scenario', 'empty']
    assert subprocess.run(command, capture_output=True).returncode != 0
    assert subprocess.run(command+['--yes'], capture_output=True).returncode == 0
    assert external.read_text() == 'keep'
    assert (root/'exports/keep.txt').read_text() == 'keep export'
    assert json.loads(invoke(root, 'train', 'list', '-o', 'json').stdout)['count'] == 0


def test_identity_change_replaces_credentials_and_catalog(tmp_path):
    import subprocess
    import sys
    root = initialize(tmp_path/'demo')
    invoke(root, 'login')
    command = [sys.executable, '-m', 'wiserec_cli_mock.manage', '--workspace', str(root), 'identity', '--username', 'analyst']
    assert subprocess.run(command, capture_output=True).returncode == 0
    invoke(root, 'auth', 'status', success=False)
    invoke(root, 'login')
    assert 'analyst' in invoke(root, 'auth', 'status').stdout
    entry = json.loads((root/'client/business.json').read_text())['profiles']['demo-dev']
    assert entry['username'] == 'analyst' and len(entry['catalog']) == 2
