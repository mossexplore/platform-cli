import re
from datetime import timedelta
from sqlalchemy import select
from app.models import Grant, Environment, Audit, now
from test_service import system, login


def test_existing_authorizations_are_checked_without_revoked_ones(system):
    app,client,_=system
    with app.state.sessions() as db:
        env=Environment(name='revoked',display_name='撤销环境',platform_origin='https://example.com')
        db.add(env);db.flush()
        db.add(Grant(user_id=1,environment_id=env.id,enabled=False))
        db.get(Grant,1).expires_at=now()-timedelta(days=1)
        db.commit()
    login(client)
    html=client.get('/cli-permission/admin?tab=users').text.split('id="add-grants-1"')[1].split('</dialog>')[0]
    prod=re.search(r'<input[^>]*name="environments"[^>]*value="prod"[^>]*>',html)[0]
    revoked=re.search(r'<input[^>]*name="environments"[^>]*value="revoked"[^>]*>',html)[0]
    assert 'checked' in prod and 'checked' not in revoked
    assert '已过期' in html


def test_save_preserves_details_and_reconciles_selection(system):
    app,client,_=system
    with app.state.sessions() as db:
        grant=db.get(Grant,1);grant.expires_at=now()+timedelta(days=5);grant.note='保留备注'
        expiry=grant.expires_at
        db.add(Environment(name='dev',display_name='开发',platform_origin='https://example.com'))
        db.commit()
    csrf=login(client)
    path='/cli-permission/admin/users/1/environments'
    assert client.post(path,data={'csrf':csrf,'environments':['prod','dev']}).status_code==200
    with app.state.sessions() as db:
        assert db.get(Grant,1).expires_at==expiry and db.get(Grant,1).note=='保留备注'
        dev=db.scalar(select(Environment).where(Environment.name=='dev'))
        assert db.scalar(select(Grant).where(Grant.environment_id==dev.id)).enabled
    assert client.post(path,data={'csrf':csrf,'environments':['dev']}).status_code==200
    with app.state.sessions() as db:
        assert not db.get(Grant,1).enabled and db.get(Grant,1).note=='保留备注'
    assert client.post(path,data={'csrf':csrf}).status_code==200
    with app.state.sessions() as db:
        assert all(not grant.enabled for grant in db.scalars(select(Grant)))
        assert db.scalar(select(Audit).where(Audit.action=='grants.selection_save'))


def test_disabled_environments_preserved_and_invalid_requests_rejected(system):
    app,client,_=system
    path='/cli-permission/admin/users/1/environments'
    assert client.post(path,data={'csrf':'bad'}).status_code==401
    csrf=login(client)
    assert client.post(path,data={'csrf':'bad'}).status_code==403
    assert client.post(path,data={'csrf':csrf,'environments':['unknown']}).status_code==400
    with app.state.sessions() as db:
        db.get(Environment,1).enabled=False;db.commit()
    html=client.get('/cli-permission/admin?tab=users').text.split('id="add-grants-1"')[1].split('</dialog>')[0]
    assert 'name="environments" value="prod"' not in html
    assert client.post(path,data={'csrf':csrf,'environments':['prod']}).status_code==400
    assert client.post(path,data={'csrf':csrf}).status_code==200
    with app.state.sessions() as db:
        assert db.get(Grant,1).enabled
