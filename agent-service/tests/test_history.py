from conftest import ready, headers


def test_rename_is_persistent_and_does_not_change_recency(client):
    ready(client)
    key = client.post('/api/conversations', headers=headers(client)).json()['id']
    before = client.get('/api/conversations').json()[0]['updated_at']
    result = client.patch('/api/conversations/' + key, json={'title': '  自定义标题  '}, headers=headers(client))
    assert result.status_code == 200
    row = client.get('/api/conversations').json()[0]
    assert row['title'] == '自定义标题'
    assert row['updated_at'] == before
    assert client.get('/api/conversations/' + key).json()['title'] == '自定义标题'


def test_rename_requires_csrf_and_valid_title(client):
    ready(client)
    key = client.post('/api/conversations', headers=headers(client)).json()['id']
    path = '/api/conversations/' + key
    assert client.patch(path, json={'title': 'new'}).status_code == 403
    for title in ['', '   ', 'x' * 101]:
        assert client.patch(path, json={'title': title}, headers=headers(client)).status_code in (400, 422)
    assert client.patch('/api/conversations/missing', json={'title': 'new'}, headers=headers(client)).status_code == 404


def test_cannot_rename_another_users_conversation(client, app):
    from app.models import Conversation, User
    ready(client)
    with app.state.db() as db:
        user = User(environment_id='dev', username='other', display_name='Other')
        db.add(user)
        db.flush()
        row = Conversation(user_id=user.id, environment_id='dev', business={}, title='private')
        db.add(row)
        db.commit()
        key = row.id
    assert client.patch('/api/conversations/' + key, json={'title': 'new'}, headers=headers(client)).status_code == 404
