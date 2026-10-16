"""Exercise the exact Docker image against MySQL through its published port."""
import re
import json
from html import unescape
import sys
import uuid
import httpx

def verify(client):
    response = client.get('/healthz')
    assert response.status_code == 200 and response.json() == {'status': 'ok'}
    for asset in ('app.css', 'app.js', 'base.css', 'icon-chevron-down.svg', 'environment-pills.js', 'approval-environments.js'):
        assert client.get('/static/' + asset).status_code == 200, asset
    page = client.get('/login')
    token = re.search(r'name="csrf" value="([^"]+)"', page.text)[1]
    page = client.post('/login', data={'username': 'ci-admin', 'password': 'ci-password-123456', 'csrf': token})
    assert page.status_code == 200 and '退出登录' in page.text
    summary = client.post('/api/v1/access/summary', json={'username': 'ci-user'})
    assert summary.status_code == 200 and summary.json()['has_access'] is True
    assert client.post('/api/v1/access/summary', json={'username': 'unknown-user'}).json()['has_access'] is False
    page = client.get('/admin?tab=environments')
    token = re.search(r'name="csrf" value="([^"]+)"', page.text)[1]
    ci_id = re.search(r'name="item_id" value="(\d+)">(?:(?!name="item_id").)*name="name"[^>]*value="ci"', page.text, re.S)[1]
    saved = client.post('/admin/environments', data={'csrf': token, 'item_id': ci_id,
        'name': 'ci', 'display_name': 'CI alias', 'platform_origin': 'https://platform.example.com',
        'enabled': 'true', 'default_grant': 'true'})
    assert saved.status_code == 200 and '默认开通' in saved.text
    batch = client.post('/api/v1/access/environments', json={'username': 'ci-user',
        'environments': [{'username': 'ci-user', 'environment': 'ci',
            'platform_origin': 'https://platform.example.com', 'business_id': 'ci-business'}]},
        headers={'businessid': 'ci-business'})
    assert batch.status_code == 200 and batch.json()['has_access'] is True
    assert batch.json()['environments'][0]['result']['allowed'] is True
    apply = client.get('/apply')
    apply_csrf = re.search(r'name="csrf" value="([^"]+)"', apply.text)[1]
    username = 'ci-apply-' + uuid.uuid4().hex[:12]
    receipt = client.post('/apply', data={'csrf': apply_csrf, 'username': username, 'display_name': 'CI Applicant'})
    assert receipt.status_code == 200 and '待审批' in receipt.text
    receipt_url = str(receipt.url)
    listing = client.get('/admin/applications?q=' + username)
    application_id = re.search(r'/cli-permission/admin/applications/(\d+)', listing.text)[1]
    preview = client.post('/admin/applications/' + application_id + '/preview',
        data={'csrf': token, 'username': username, 'display_name': 'CI Applicant'})
    assert preview.status_code == 200 and 'data-default-grant="true" checked' in preview.text
    snapshot = re.search(r'name="snapshot" value="([^"]+)"', preview.text)[1]
    approved = client.post('/admin/applications/' + application_id + '/approve', data={
        'csrf': token, 'snapshot': snapshot, 'username': username, 'display_name': 'CI Applicant',
        'environments': [ci_id]})
    assert approved.status_code == 200 and 'CI alias' in approved.text
    assert 'CI alias' in client.get(receipt_url).text
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
    dashboard = client.get('/admin/analytics')
    assert dashboard.status_code == 200, dashboard.text
    chart = json.loads(unescape(re.search(r"data-analysis-chart='([^']+)'", dashboard.text)[1]))
    assert sum(point['total'] for point in chart['points']) >= 2
    for point in chart['points']:
        assert all(type(point[key]) is int for key in ('total', 'allowed', 'denied'))
        assert all(type(value) is int for value in point['commands'])
    for key in ('ranking', 'distribution'):
        assert all(type(item['value']) is int for item in chart[key])


if __name__ == "__main__":
    base = sys.argv[1] + "/cli-permission"
    with httpx.Client(base_url=base, follow_redirects=True, trust_env=False, timeout=15) as client:
        verify(client)
    print("PASS: health, assets, admin login, grant allow/deny persisted call logs and numeric dashboard JSON")
