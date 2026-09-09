import pytest
from app.models import Admin, Audit, CallLog, Environment, User
from test_service import system, login


@pytest.mark.parametrize('path,model,fields', [
    ('/admin?tab=users', User, lambda i: {'username': f'user-{i}'}),
    ('/admin?tab=environments', Environment, lambda i: {'name': f'env-{i}', 'display_name': '环境', 'platform_origin': 'https://example.com'}),
    ('/admin?tab=audit', Audit, lambda i: {'actor': 'admin', 'action': 'login', 'detail': '登录'}),
    ('/admin/administrators', Admin, lambda i: {'username': f'admin-{i}', 'password_hash': 'unused'}),
    ('/admin/calls', CallLog, lambda i: {'actor': 'alice', 'command': 'ml train list', 'environment': 'prod', 'business_id': 'biz', 'source_ip': '', 'allowed': True, 'reason': 'ALLOWED'}),
])
def test_lists_show_ten_records(system, path, model, fields):
    app, client, _ = system
    with app.state.sessions() as db:
        db.add_all(model(**fields(i)) for i in range(11))
        db.commit()
    login(client)
    html = client.get('/cli-permission' + path).text
    assert ('每页 10 人' if model is User else '每页 10 条') in html
    assert html.split('<tbody>')[1].split('</tbody>')[0].count('<tr') == 10
    assert '下一页' in html
    assert 'name="page" min="1" max="2"' in html
    separator = '&' if '?' in path else '?'
    second = client.get('/cli-permission' + path + separator + 'page=2')
    assert second.status_code == 200
    assert '第 2 / 2 页' in second.text
    assert 1 <= second.text.split('<tbody>')[1].split('</tbody>')[0].count('<tr') < 10


def test_all_lists_offer_page_jump_and_preserve_filters(system):
    import re
    from html import unescape
    from urllib.parse import urlencode
    app, client, _ = system
    login(client)
    cases = [
        ('/cli-permission/admin', {'tab':'users','q':'alice','status':'enabled','grant_status':'active'}),
        ('/cli-permission/admin', {'tab':'environments','q':'prod','status':'enabled'}),
        ('/cli-permission/admin', {'tab':'audit','q':'admin'}),
        ('/cli-permission/admin/applications', {'status':'pending','q':'张三'}),
        ('/cli-permission/admin/administrators', {'q':'admin','status':'enabled'}),
        ('/cli-permission/admin/calls', {'username':'alice','environment':'prod','command':'ml train list',
            'result':'allowed','begin':'2026-01-01T00:00:00','end':'2027-01-01T00:00:00'}),
    ]
    for path, filters in cases:
        response = client.get(path+'?'+urlencode(filters))
        assert response.status_code == 200, response.text
        form = re.search(r'<form class="page-jump".*?</form>', response.text, re.S)[0]
        assert f'action="{path}"' in form and 'method="get"' in form
        hidden = dict((unescape(k),unescape(v)) for k,v in re.findall(r'type="hidden" name="([^"]+)" value="([^"]*)"',form))
        assert hidden == filters
        assert 'name="page" min="1" max="1" step="1"' in form
        assert 'aria-label="跳转页码"' in form and '>跳转</button>' in form
