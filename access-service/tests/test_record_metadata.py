from datetime import datetime
from sqlalchemy import text, select
from app.models import User, Environment, SchemaVersion
from app.migrations import migrate
from test_service import system, login


def test_creation_edit_and_grants_track_actor_and_keep_creation(system):
    app,client,_=system
    csrf=login(client)
    response=client.post('/cli-permission/admin/users',data={'csrf':csrf,'username':'new','enabled':'true','updated_by':'forged'})
    assert response.status_code==200
    with app.state.sessions() as db:
        user=db.scalar(select(User).where(User.username=='new'))
        user_id=user.id;created=user.created_at
        assert created and user.updated_at and user.updated_by=='admin'
        user.updated_at=datetime(2000,1,1);db.commit()
    assert client.post(f'/cli-permission/admin/users/{user_id}/environments',data={'csrf':csrf,'environments':['prod']}).status_code==200
    with app.state.sessions() as db:
        user=db.get(User,user_id)
        assert user.created_at==created and user.updated_at>datetime(2000,1,1) and user.updated_by=='admin'
    assert client.post('/cli-permission/admin/environments',data={'csrf':csrf,'item_id':1,'name':'prod','display_name':'生产','platform_origin':'https://platform.example.com','enabled':'true'}).status_code==200
    with app.state.sessions() as db:
        assert db.get(Environment,1).updated_by=='admin'
        user=db.get(User,user_id);user.created_at=datetime(2026,9,8,6,54,36);db.commit()
    html=client.get('/cli-permission/admin?tab=users').text
    assert '2026-09-08 14:54:36' in html
    for path in ['users','environments']:
        html=client.get('/cli-permission/admin?tab='+path).text
        assert '创建时间' in html and '修改时间' in html and '最新操作人' in html


def test_v4_metadata_migration_preserves_unknown_history(system):
    app,client,_=system
    with app.state.engine.begin() as connection:
        for table in ['users','environments']:
            for column in ['created_at','updated_at','updated_by']:
                connection.execute(text(f'ALTER TABLE {table} DROP COLUMN {column}'))
        connection.execute(text('UPDATE schema_versions SET version=4'))
    migrate(app.state.engine,app.state.sessions)
    migrate(app.state.engine,app.state.sessions)
    with app.state.sessions() as db:
        assert db.get(SchemaVersion,7)
        for model in [User,Environment]:
            row=db.get(model,1)
            assert row.created_at is None and row.updated_at is None and row.updated_by is None
    login(client)
    assert '未知' in client.get('/cli-permission/admin?tab=users').text
