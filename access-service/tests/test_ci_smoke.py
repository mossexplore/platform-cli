"""Keep the Docker smoke client's requests aligned with the real API contract."""
from app.models import Admin, Environment, Grant, User
from app.security import password_hash
from ci.smoke import verify
from test_service import system


def test_smoke_client_exercises_valid_allow_and_deny_requests(system):
    app, client, _ = system
    with app.state.sessions() as db:
        db.add(Admin(username='ci-admin', password_hash=password_hash('ci-password-123456'), role='super_admin'))
        user = User(username='ci-user')
        environment = Environment(name='ci', display_name='CI', platform_origin='https://platform.example.com')
        db.add_all([user, environment])
        db.flush()
        db.add(Grant(user_id=user.id, environment_id=environment.id))
        db.commit()
    client.base_url = 'http://testserver/cli-permission/'
    verify(client)
