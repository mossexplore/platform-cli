"""Run-scoped visibility, bounded discovery and server-owned schemas."""
import json
import pytest
from agents import Agent, RunContextWrapper
from app.tools import build_tools, REGISTRY
from app.tool_catalog import DOMAINS, ToolSelection, discover


async def visible(selection):
    async def invoke(name, args):
        return discover(args)
    agent = Agent(name="test", tools=build_tools(invoke, selection))
    return {t.name for t in await agent.get_all_tools(RunContextWrapper(context=None))}


@pytest.mark.parametrize('message,domain', [('模型详情', 'models'), ('训练任务', 'training'),
                                          ('服务主机', 'services'), ('日志', 'logs')])
async def test_initial_domain_sends_only_relevant_definitions(message, domain):
    assert await visible(ToolSelection(message)) == set(DOMAINS[domain].names) | {'discover_tools'}


async def test_unknown_intent_only_exposes_discovery_and_directory():
    assert await visible(ToolSelection('你好，帮我分析一下')) == {'discover_tools'}
    result = discover({'query': 'not-a-real-capability'})
    assert not result['tools'] and len(result['domains']) == len(DOMAINS)


def test_catalog_is_complete_and_bounded():
    assert {name for d in DOMAINS.values() for name in d.names} == REGISTRY.keys()
    for domain in DOMAINS:
        result = discover({'domain': domain})
        assert 1 <= len(result['tools']) <= 4
        assert all(set(t) == {'name', 'description'} for t in result['tools'])
    assert [t['name'] for t in discover({'query': 'get_model_training'})['tools']] == ['get_model_training']
    with pytest.raises(ValueError):
        discover({'domain': 'shell', 'cookie': 'secret'})


async def test_discovery_enables_next_request_not_other_runs():
    first, other = ToolSelection('模型'), ToolSelection('模型')
    async def invoke(name, args):
        assert name == 'discover_tools'
        return discover(args)
    tool = next(t for t in build_tools(invoke, first) if t.name == 'discover_tools')
    await tool.on_invoke_tool(None, json.dumps({'domain': 'training'}))
    assert set(DOMAINS['training'].names) <= await visible(first)
    assert not set(DOMAINS['training'].names) & await visible(other)
    assert await visible(ToolSelection('你好')) == {'discover_tools'}


def test_load_limit_is_atomic_and_exact_name_can_fit():
    selection = ToolSelection('模型', limit=5)
    result = selection.apply(discover({'domain': 'training'}))
    assert result['error'] == 'TOOL_LOAD_LIMIT'
    assert selection.loaded == set(DOMAINS['models'].names)
    assert selection.apply(discover({'query': 'list_train_history'}))['ok']
    assert len(selection.loaded) == 5
    with pytest.raises(ValueError):
        selection.apply({'ok': True, 'tools': [{'name': 'arbitrary_http'}]})


async def test_hidden_tool_cannot_be_invoked_directly():
    calls = []
    async def invoke(name, args):
        calls.append(name)
    tool = next(t for t in build_tools(invoke, ToolSelection('模型')) if t.name == 'list_services')
    with pytest.raises(ValueError, match='尚未加载'):
        await tool.on_invoke_tool(None, '{}')
    assert not calls
