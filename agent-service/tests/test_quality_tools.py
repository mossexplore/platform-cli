"""Quality tools discovery, bounded schema, permission identifiers and service dispatch."""
import json

import httpx
import pytest
from sqlalchemy import select

from conftest import BUSINESS, ready
from app.business_tools import OPERATIONS
from app.errors import AppError
from app.models import Session
from app.platform import COMMANDS
from app.tool_catalog import ToolSelection, discover
from app.tools import REGISTRY, build_tools
from wiserec_cli.services.quality import PREFIX, TYPES

TOOLS = {
    'list_quality_features': ('ml quality feature list', '', 'featureList'),
    'list_quality_wide_featuresets': ('ml quality wide-featureset list', '/wide-feature-sets', 'featureSetList'),
}


def test_discovery_and_model_tool_schemas():
    for query in ('质量监控报告', '特征质量', '空值率', '时效性', 'quality', '特征列表',
                  '查询宽表特征集质量', '宽表特征集的质量监控'):
        result = discover({'query': query})
        assert {tool['name'] for tool in result['tools']} == set(TOOLS)
        assert ToolSelection(query).loaded == set(TOOLS)
    assert {item['name'] for item in discover({'domain': 'quality'})['tools']} == set(TOOLS)
    for name, (command, _, _) in TOOLS.items():
        assert COMMANDS[name] == command
        assert not OPERATIONS[name].write
        assert REGISTRY[name][0] is OPERATIONS[name].schema
        assert discover({'query': name})['tools'][0]['name'] == name
        schema = OPERATIONS[name].schema.model_json_schema()
        assert schema['properties']['page_size']['maximum'] == 100
        assert schema['additionalProperties'] is False
    schema = OPERATIONS['list_quality_features'].schema.model_json_schema()
    assert set(schema['properties']['indicator_type']['anyOf'][0]['enum']) == set(TYPES)


@pytest.mark.asyncio
async def test_sdk_function_tool_receives_normalized_arguments():
    calls = []
    async def invoke(name, args):
        calls.append((name, args))
        return {'ok': True}
    selection = ToolSelection('质量监控')
    tools = {tool.name: tool for tool in build_tools(invoke, selection)}
    result = await tools['list_quality_features'].on_invoke_tool(None,
        json.dumps({'feature_value_type': '离散', 'indicator_type': 'vector'}))
    assert result == {'ok': True}
    assert calls == [('list_quality_features', {'page': 1, 'page_size': 10, 'name': '',
        'table_name': '', 'feature_value_type': 'DISCRETE', 'indicator_type': 'VECTOR'})]


@pytest.mark.parametrize('field', ['feature_value_type', 'indicator_type'])
@pytest.mark.parametrize('key,label', TYPES.items())
def test_enum_normalization(field, key, label):
    for value in (key, key.lower(), label):
        args = OPERATIONS['list_quality_features'].schema.model_validate({field: value})
        assert getattr(args, field) == key


@pytest.mark.parametrize('name', TOOLS)
@pytest.mark.parametrize('args', [{'page': 0}, {'page': True}, {'page_size': 101},
    {'page_size': 0}, {'page_size': True}, {'business_id': 'other'}, {'url': 'https://other.test'}])
def test_invalid_arguments_rejected_before_platform_access(settings, name, args):
    from app.platform import Platform
    with pytest.raises(ValueError):
        Platform(settings, None).execute('session', None, BUSINESS, name, args, 'call')


@pytest.mark.parametrize('value', ['bad', 1, True, [], {}])
def test_bad_enum_is_rejected(value):
    for field in ('feature_value_type', 'indicator_type'):
        with pytest.raises(ValueError):
            OPERATIONS['list_quality_features'].schema.model_validate({field: value})


@pytest.mark.parametrize('name', TOOLS)
@pytest.mark.parametrize('filtered', [False, True])
def test_full_permission_chain_and_service_contract(client, app, name, filtered):
    ready(client)
    # Exercise the API maximum while respecting the existing administrator limit.
    app.state.platform.config.runtime.max_page_size = 100
    with app.state.db() as db:
        session_id = db.scalar(select(Session.id).where(Session.status == 'ready'))
    command, suffix, list_key = TOOLS[name]
    wide = name.endswith('wide_featuresets')
    args = {'name': 'name', 'page': 2, 'page_size': 100} if filtered else {}
    expected = {'setName': ''} if wide else {'featureName': '', 'tableName': ''}
    expected.update(pageIndex=1, pageSize=10)
    if filtered:
        expected.update(pageIndex=2, pageSize=100)
        expected['setName' if wide else 'featureName'] = 'name'
        if not wide:
            args.update(table_name='table', feature_value_type='离散', indicator_type='vector')
            expected.update(tableName='table', featureValueType='DISCRETE', indicatorType='VECTOR')
    item = {'setId' if wide else 'featureId': '33b1a068-0c3d-4d23-b4aa-a6001ee33342',
            'extra': {'retained': True}, 'nullValueRate': 0.125, 'latestCycleTime': '2026102800'}
    original = app.state.platform.transport.handler
    queries = []
    def upstream(request):
        if request.url.path == PREFIX + suffix:
            queries.append(request)
            assert request.headers.get_list('businessid') == ['b1']
            assert request.url.host == httpx.URL(app.state.platform.config.env('dev').api_endpoint).host
            assert json.loads(request.content) == expected
            app.test_upstream.calls.append(request)
            previous = app.test_upstream.calls[-2]
            assert previous.url.path.endswith('/gateway/check')
            assert json.loads(previous.content)['command'] == command
            return httpx.Response(200, json={'result': {'code': 0, 'totalCount': 30,
                'pageIndex': 1, 'pageSize': 1, list_key: [item]}})
        return original(request)
    app.state.platform.transport = httpx.MockTransport(upstream)
    result = app.state.platform.execute(session_id, None, BUSINESS, name, args, 'quality-call')
    assert len(queries) == 1
    assert result['ok'] and not result['truncated']
    assert result['data'] == {'items': [item], 'count': 30, 'pageIndex': 1, 'pageSize': 1}
    app.test_upstream.allow = False
    with pytest.raises(AppError, match='权限'):
        app.state.platform.execute(session_id, None, BUSINESS, name, args, 'denied-call')
    assert len(queries) == 1
