import json
import pytest
from sqlalchemy import select, text
from app.models import User, Environment, Grant, Audit, Admin, CallLog
from test_service import system, login, check


@pytest.mark.parametrize('resource,model,other', [('users',User,Environment),('environments',Environment,User)])
def test_physical_delete_and_preserve_history(system,resource,model,other):
    app,client,_=system
    check(client)
    csrf=login(client)
    with app.state.sessions() as db:
        db.get(Admin,1).role='admin'
        db.commit()
    response=client.post(f'/cli-permission/admin/{resource}/1/delete',data={'csrf':csrf,'confirmation':'yes'})
    assert response.status_code==200 and '删除成功' in response.text
    with app.state.sessions() as db:
        assert db.get(model,1) is None
        assert db.get(other,1) is not None
        assert db.scalar(select(Grant)) is None
        assert db.scalar(select(CallLog)) is not None
        audit=db.scalar(select(Audit).where(Audit.action==resource+'.delete'))
        assert json.loads(audit.detail)['removed_grants']==1
    assert client.post(f'/cli-permission/admin/{resource}/1/delete',data={'csrf':csrf,'confirmation':'yes'}).status_code==404


@pytest.mark.parametrize('resource', ['users','environments'])
def test_delete_requires_session_csrf_and_exact_yes(system,resource):
    app,client,_=system
    path=f'/cli-permission/admin/{resource}/1/delete'
    assert client.post(path,data={'csrf':'fake','confirmation':'yes'}).status_code==401
    csrf=login(client)
    assert client.post(path,data={'csrf':'bad','confirmation':'yes'}).status_code==403
    for value in ['', 'YES', 'yes ', 'no']:
        assert client.post(path,data={'csrf':csrf,'confirmation':value}).status_code==400
    assert client.get(path).status_code==405
    with app.state.sessions() as db:
        assert db.get(User,1) and db.get(Environment,1) and db.get(Grant,1)
    page=client.get('/cli-permission/admin?tab='+resource).text
    assert f'data-open="delete-{resource}-1"' in page
    assert 'pattern="yes"' in page and 'class="danger-button" disabled' in page


def test_delete_rolls_back_if_audit_fails(system):
    app,client,_=system
    csrf=login(client)
    with app.state.engine.begin() as connection:
        connection.execute(text("CREATE TRIGGER fail_delete_audit BEFORE INSERT ON audit_logs WHEN NEW.action = 'users.delete' BEGIN SELECT RAISE(ABORT, 'audit failure'); END"))
    result=client.post('/cli-permission/admin/users/1/delete',data={'csrf':csrf,'confirmation':'yes'})
    assert result.status_code>=400
    with app.state.sessions() as db:
        assert db.get(User,1) and db.get(Grant,1)
