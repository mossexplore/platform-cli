"""Independent CLI inventory gate: new business leaves must have agent coverage."""
import click
import pytest
from typer.main import get_command
from wiserec_cli.cli import app as cli
from app.platform import COMMANDS
from app.business_tools import OPERATIONS
from app.tools import REGISTRY
from app.tool_catalog import DOMAINS, discover

UI_GROUPS = {'auth', 'access', 'business', 'env', 'history'}
UI_LEAVES = {'ml context', 'ml login', 'ml logout', 'ml tree'}


def leaves(node, path='ml'):
    if isinstance(node, click.Group):
        return {leaf for name, child in node.commands.items() for leaf in leaves(child, path + ' ' + name)}
    return {path}


def test_every_business_cli_command_is_mapped_and_no_fictional_permission_commands():
    commands = leaves(get_command(cli))
    business = {c for c in commands if c not in UI_LEAVES and c.split()[1] not in UI_GROUPS}
    mapped = {COMMANDS[name] for name in REGISTRY}
    assert business <= mapped, 'Uncovered CLI commands: ' + str(business - mapped)
    assert mapped <= commands, 'Invented permission commands: ' + str(mapped - commands)


def test_discovery_pagination_reaches_every_tool_with_four_schema_limit():
    seen = set()
    for key, domain in DOMAINS.items():
        offset, names = 0, []
        while True:
            result = discover({'domain': key, 'offset': offset})
            assert len(result['tools']) <= 4
            names += [x['name'] for x in result['tools']]
            offset = result['next_offset']
            if offset is None: break
        assert names == list(domain.names)
        seen.update(names)
    assert seen == set(REGISTRY)


@pytest.mark.parametrize('name', list(OPERATIONS))
def test_schemas_reject_identity_and_arbitrary_transport_injection(name):
    op = OPERATIONS[name]
    schema = op.schema.model_json_schema()
    assert schema['additionalProperties'] is False
    assert not {'cookie', 'token', 'username', 'business_id', 'tenant_id', 'url', 'method', 'file_path'} & schema['properties'].keys()
    with pytest.raises(ValueError):
        op.schema.model_validate({'cookie': 'spoof', 'business_id': 'other'})


def test_feature_kind_and_optional_service_arguments():
    assert OPERATIONS['list_resource_templates'].schema.model_validate({}).env is None
    assert OPERATIONS['list_model_featuresets'].schema.model_validate({}).model_dump() == {'page_index': 1, 'page_size': 10, 'name': None}
    assert OPERATIONS['list_sample_tasks'].schema.model_validate({'status': 'started'}).status == 'started'
