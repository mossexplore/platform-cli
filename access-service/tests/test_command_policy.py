"""环境禁止命令的管理、鉴权、审计和显式迁移。"""
import json
import pytest
from sqlalchemy import select, text
from app.models import Environment, Audit, CallLog, SchemaVersion
from app.migrations import migrate, SCHEMA_VERSION
from test_service import system, login, check

COMMAND = 'ml jupyter files upload'


def save(app, client, csrf, commands, **extra):
    with app.state.sessions() as db:
        env = db.scalar(select(Environment))
        data = dict(csrf=csrf, item_id=env.id, name=env.name, display_name=env.display_name,
                    platform_origin=env.platform_origin, enabled='true', forbidden_commands='\n'.join(commands),
                    policy_revision=env.command_policy_revision)
    return client.post('/cli-permission/admin/environments', data={**data, **extra}, follow_redirects=False)


def test_admin_policy_enforces_without_local_configuration(system):
    app, client, _ = system
    csrf = login(client)
    assert save(app, client, csrf, [COMMAND]).status_code == 303
    result = check(client, command=COMMAND).json()
    assert result['allowed'] is False and result['reason'] == 'COMMAND_DISABLED'
    assert result['command_policy']['deny'] == [COMMAND]
    assert result['command_policy']['revision'] == 1
    assert check(client, command='ml jupyter files download').json()['allowed'] is True
    assert check(client, command='ml dataset files upload').json()['allowed'] is True
    with app.state.sessions() as db:
        log = db.scalars(select(CallLog).where(CallLog.command == COMMAND)).one()
        assert not log.allowed and log.reason == 'COMMAND_DISABLED'
        audit = db.scalars(select(Audit).where(Audit.action == 'environments.save')).one()
        detail = json.loads(audit.detail)
        assert detail['before']['forbidden_commands'] == []
        assert detail['after']['forbidden_commands'] == [COMMAND]
    page = client.get('/cli-permission/admin?tab=environments')
    assert page.status_code == 200 and '禁止命令' in page.text and COMMAND in page.text
    assert 'data-command-input' in page.text
    assert 'data-command-search' not in page.text
    assert save(app, client, csrf, []).status_code == 303
    result = check(client, command=COMMAND).json()
    assert result['allowed'] is True and result['command_policy']['revision'] == 2


@pytest.mark.parametrize('commands', [['ml env use'], ['ml unknown'], ['ml jupyter files upload --force']])
def test_invalid_rule_is_atomic(system, commands):
    app, client, _ = system
    csrf = login(client)
    assert save(app, client, csrf, [COMMAND]).status_code == 303
    assert save(app, client, csrf, commands).status_code == 400
    assert check(client, command=COMMAND).json()['reason'] == 'COMMAND_DISABLED'


def test_stale_edit_rejected(system):
    app, client, _ = system
    csrf = login(client)
    assert save(app, client, csrf, [COMMAND]).status_code == 303
    assert save(app, client, csrf, [], policy_revision=0).status_code == 409
    assert check(client, command=COMMAND).json()['reason'] == 'COMMAND_DISABLED'


def test_gateway_uses_same_rules(system):
    app, client, _ = system
    from dataclasses import replace
    app.state.settings = replace(app.state.settings, gateway_token='a' * 40)
    csrf = login(client)
    save(app, client, csrf, [COMMAND])
    response = client.post('/cli-permission/api/v1/gateway/check',
        headers={'authorization': 'Bearer ' + 'a' * 40, 'businessid': 'selected'},
        json={'username': 'alice', 'environment': 'prod', 'platform_origin': 'https://platform.example.com',
              'command': COMMAND})
    assert response.status_code == 403 and response.json()['reason'] == 'COMMAND_DISABLED'


def test_migration_from_12_is_repeatable_and_preserves_environment(system):
    app, _, _ = system
    with app.state.engine.begin() as connection:
        connection.execute(text('DROP TABLE environment_command_denies'))
        connection.execute(text('ALTER TABLE environments DROP COLUMN command_policy_revision'))
        connection.execute(text('UPDATE schema_versions SET version=12'))
    migrate(app.state.engine, app.state.sessions)
    migrate(app.state.engine, app.state.sessions)
    with app.state.sessions() as db:
        env = db.scalar(select(Environment))
        assert env.name == 'prod' and env.command_policy_revision == 0 and env.forbidden_commands == []
        assert db.get(SchemaVersion, SCHEMA_VERSION)


def test_missing_command_cannot_be_used_when_policy_exists(system):
    app, client, _ = system
    csrf = login(client)
    save(app, client, csrf, [COMMAND])
    assert check(client).json()['reason'] == 'COMMAND_REQUIRED'


def test_delete_environment_cleans_rules(system):
    app, client, _ = system
    from app.models import EnvironmentCommandDeny
    csrf = login(client)
    save(app, client, csrf, [COMMAND])
    with app.state.sessions() as db:
        env_id = db.scalar(select(Environment.id))
    response = client.post(f'/cli-permission/admin/environments/{env_id}/delete',
                           data={'csrf': csrf, 'confirmation': 'yes'}, follow_redirects=False)
    assert response.status_code == 303
    with app.state.sessions() as db:
        assert db.scalars(select(EnvironmentCommandDeny)).all() == []


def test_whitespace_is_normalized_before_matching(system):
    app, client, _ = system
    csrf = login(client)
    save(app, client, csrf, [COMMAND])
    result = check(client, command='  ml   jupyter files upload ').json()
    assert result['reason'] == 'COMMAND_DISABLED'
    assert check(client, command='ml').json()['reason'] == 'COMMAND_REQUIRED'


def test_manual_lines_normalize_and_deduplicate(system):
    app, client, _ = system
    csrf = login(client)
    response = save(app, client, csrf, ['  ml   jupyter files upload  ', '', COMMAND,
                                      'ml custom-system future-operation'])
    assert response.status_code == 303
    result = check(client, command=COMMAND).json()
    assert result['command_policy']['deny'] == ['ml custom-system future-operation', COMMAND]
    page = client.get('/cli-permission/admin?tab=environments')
    assert 'ml custom-system future-operation\nml jupyter files upload' in page.text
    assert 'type="checkbox" name="forbidden_commands"' not in page.text
    assert check(client, command='ml custom-system future-operation').json()['reason'] == 'COMMAND_DISABLED'
