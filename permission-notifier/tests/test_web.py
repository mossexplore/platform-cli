import re
from fastapi.testclient import TestClient
from permission_notifier.store import Store
from permission_notifier.worker import Worker
from permission_notifier.web import create_app
from test_store_sender import configured


def test_local_boundary_csrf_and_config(tmp_path):
    store=Store(tmp_path/'assistant.json');configured(store)
    app=create_app(store,Worker(store))
    with TestClient(app,base_url='http://127.0.0.1:18765') as client:
        page=client.get('/')
        assert page.status_code==200
        csrf=re.search('name="csrf-token" content="([^"]+)"',page.text)[1]
        headers={'Origin':'http://127.0.0.1:18765','X-CSRF-Token':csrf}
        assert client.post('/api/pause',json={}).status_code==403
        assert client.post('/api/pause',json={},headers={**headers,'Origin':'https://evil.example'}).status_code==403
        assert client.get('/api/config',headers={'Host':'evil.example'}).status_code==403
        public=client.get('/api/config').json()
        assert 'token-value' not in str(public) and 'auth-value' not in str(public)
        public['config']['poll_interval_seconds']=17
        response=client.put('/api/config',json={'config':public['config'],'config_revision':public['config_revision']},headers=headers)
        assert response.status_code==200,response.text
        assert store.snapshot()['config']['poll_interval_seconds']==17
        assert client.put('/api/config',json={'config':public['config'],'config_revision':public['config_revision']},headers=headers).status_code==409
        assert client.post('/api/resume',json={},headers=headers).status_code==200
        assert not store.snapshot()['state']['paused']
        assert client.post('/api/pause',json={},headers=headers).status_code==200
        assert store.snapshot()['state']['paused']


def test_connection_tracks_current_identity_and_heartbeat(tmp_path):
    import time
    store = Store(tmp_path/'assistant.json')
    values = configured(store)
    worker = Worker(store)
    with TestClient(create_app(store, worker), base_url='http://127.0.0.1:18765') as client:
        assert client.get('/api/status').json()['connection_state'] == 'pending'
        worker.bound_signature = (values['permission_service_url'], values['assistant_token'])
        worker.last_heartbeat = time.time()
        assert client.get('/api/status').json()['connection_state'] == 'connected'
        worker.last_heartbeat -= 121
        assert client.get('/api/status').json()['connection_state'] == 'disconnected'
        worker.last_heartbeat = time.time()
        worker.bound_signature = ('https://other.example', 'other')
        assert client.get('/api/status').json()['connection_state'] != 'connected'
        worker.bound_signature = (values['permission_service_url'], values['assistant_token'])
        worker.error = 'AUTH_REJECTED'
        assert client.get('/api/status').json()['connection_state'] == 'disconnected'


def test_navigation_resources_are_available_offline(tmp_path):
    store = Store(tmp_path/'assistant.json')
    with TestClient(create_app(store, Worker(store)), base_url='http://127.0.0.1:18765') as client:
        page = client.get('/')
        from html.parser import HTMLParser
        class Resources(HTMLParser):
            def __init__(self):
                super().__init__()
                self.paths = []
            def handle_starttag(self, tag, attrs):
                for key, value in attrs:
                    if key in ('src', 'href') and value.startswith('/static/'):
                        self.paths.append(value)
        resources = Resources()
        resources.feed(page.text)
        assert len(resources.paths) >= 7
        for path in resources.paths:
            response = client.get(path)
            assert response.status_code == 200, path
            if path.endswith('.svg'):
                assert '<svg' in response.text


def test_reveal_requires_local_post_and_never_changes_config(tmp_path):
    store=Store(tmp_path/'assistant.json');configured(store)
    before=store.path.read_bytes()
    with TestClient(create_app(store,Worker(store)),base_url='http://127.0.0.1:18765') as client:
        page=client.get('/')
        csrf=re.search('name="csrf-token" content="([^"]+)"',page.text)[1]
        headers={'Origin':'http://127.0.0.1:18765','X-CSRF-Token':csrf}
        assert client.get('/api/secrets/reveal').status_code==405
        assert client.post('/api/secrets/reveal',json={'field':'auth'}).status_code==403
        assert client.post('/api/secrets/reveal',json={'field':'auth'},headers={**headers,'Origin':'https://evil.example'}).status_code==403
        for field,value in [('auth','auth-value'),('assistant_token','token-value')]:
            response=client.post('/api/secrets/reveal',json={'field':field},headers=headers)
            assert response.json()=={'value':value}
            assert response.headers['cache-control']=='no-store'
        assert client.post('/api/secrets/reveal',json={'field':'unknown'},headers=headers).status_code==400
        assert 'auth-value' not in client.get('/api/config').text
        assert 'token-value' not in client.get('/api/status').text
    assert store.path.read_bytes()==before


def test_record_api_filters_and_invalid_times(tmp_path):
    from permission_notifier.records import begin,finish
    store=Store(tmp_path/'assistant.json')
    rid=begin(store,'test-id','test','001','test content');finish(store,rid,{'state':'accepted'})
    with TestClient(create_app(store,Worker(store)),base_url='http://127.0.0.1:18765') as client:
        assert client.get('/api/records?source=test').json()['total']==1
        assert client.get('/api/records?source=permission').json()['total']==0
        assert client.get('/api/records?start=invalid').status_code==400
        assert client.get('/api/records?page=0').status_code==400
