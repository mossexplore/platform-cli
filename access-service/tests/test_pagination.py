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
    assert '每页 10 条' in html
    assert html.split('<tbody>')[1].split('</tbody>')[0].count('<tr>') == 10
    assert '下一页' in html
