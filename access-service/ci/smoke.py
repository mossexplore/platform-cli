"""Exercise the exact Docker image against MySQL through its published port."""
import re
import sys
import httpx

def verify(client):
    response = client.get('/healthz')
    assert response.status_code == 200 and response.json() == {'status': 'ok'}
    for asset in ('app.css', 'app.js', 'base.css', 'icon-chevron-down.svg'):
        assert client.get('/static/' + asset).status_code == 200, asset
    page = client.get('/login')
    token = re.search(r'name="csrf" value="([^"]+)"', page.text)[1]
    page = client.post('/login', data={'username': 'ci-admin', 'password': 'ci-password-123456', 'csrf': token})
    assert page.status_code == 200 and '退出登录' in page.text
    body = {'username': 'ci-user', 'environment': 'ci', 'platform_origin': 'https://platform.example.com',
            'command': 'ml train list', 'full_command': 'ml train list'}
    response = client.post('/api/v1/access/check', json=body, headers={'businessid': 'ci-business'})
    assert response.status_code == 200 and response.json()['allowed'] is True
    body['username'] = 'unknown-user'
    response = client.post('/api/v1/access/check', json=body, headers={'businessid': 'ci-business'})
    assert response.status_code == 200, response.text
    assert response.json()['allowed'] is False
    logs = client.get('/admin/calls')
    assert logs.status_code == 200 and 'ci-business' in logs.text


if __name__ == "__main__":
    base = sys.argv[1] + "/cli-permission"
    with httpx.Client(base_url=base, follow_redirects=True, trust_env=False, timeout=15) as client:
        verify(client)
    print("PASS: health, assets, admin login, grant allow/deny and persisted call logs")
