import re
from test_service import system, login


def test_entry_redirects_and_scoped_login_cookie(system):
    _, client, _ = system
    response = client.get('/cli-permission', follow_redirects=False)
    assert response.status_code == 308
    assert response.headers['location'] == '/cli-permission/'
    response = client.get('/cli-permission/')
    assert response.url.path == '/cli-permission/login'
    assert 'Path=/cli-permission' in response.headers['set-cookie']
    assert client.get('/healthz').status_code == 404
    assert client.post('/api/v1/access/check', json={}).status_code == 404
    assert client.get('/cli-permission/healthz').json() == {'status':'ok'}
    response = client.post('/cli-permission/api/v1/access/check', json={})
    assert response.status_code == 422
    assert response.headers['content-type'] == 'application/json'


def test_links_forms_assets_and_logout_stay_under_prefix(system):
    _, client, _ = system
    csrf = login(client)
    cookie = next(c for c in client.cookies.jar if c.name == 'access_session')
    assert cookie.path == '/cli-permission'
    for page in ['users','environments','grants','audit']:
        html = client.get('/cli-permission/admin?tab='+page).text
        for url in re.findall(r'(?:href|src|action)="([^"]+)"', html):
            assert url.startswith(('/cli-permission/', '#')), url
    css = client.get('/cli-permission/static/app.css')
    assert css.status_code == 200
    for asset in re.findall(r'url\("([^"]+)"\)', css.text):
        assert client.get('/cli-permission/static/'+asset).status_code == 200
    assert client.get('/cli-permission/static/app.js').status_code == 200
    response = client.post('/cli-permission/logout', data={'csrf':csrf}, follow_redirects=False)
    assert response.headers['location'] == '/cli-permission/login'
    assert 'Path=/cli-permission' in response.headers['set-cookie']
    assert 'Max-Age=0' in response.headers['set-cookie']
