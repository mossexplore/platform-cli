"""Real SDK + scripted HTTP provider: verify tools actually sent each model turn."""
import json
import httpx
import pytest
from openai import AsyncOpenAI
from app.agent_engine import AgentEngine
from app.tool_catalog import discover


def sse(mode, model, step, name=None, args=None):
    if mode == 'chat_completions':
        delta = ({'role': 'assistant', 'tool_calls': [{'index': 0, 'id': f'call_{step}',
                 'type': 'function', 'function': {'name': name, 'arguments': json.dumps(args)}}]}
                 if name else {'role': 'assistant', 'content': '查询完成'})
        event = {'id': f'chat_{step}', 'object': 'chat.completion.chunk', 'created': 1, 'model': model,
                 'choices': [{'index': 0, 'delta': delta, 'finish_reason': 'tool_calls' if name else 'stop'}]}
        return 'data: '+json.dumps(event)+'\n\ndata: [DONE]\n\n'
    item = ({'id': f'fc_{step}', 'type': 'function_call', 'call_id': f'call_{step}',
             'name': name, 'arguments': json.dumps(args), 'status': 'completed'} if name else
            {'id': f'msg_{step}', 'type': 'message', 'role': 'assistant', 'status': 'completed',
             'content': [{'type': 'output_text', 'text': '查询完成', 'annotations': []}]})
    response = {'id': f'resp_{step}', 'object': 'response', 'created_at': 1, 'model': model,
                'status': 'completed', 'output': [item], 'parallel_tool_calls': False,
                'tool_choice': 'auto', 'tools': [], 'usage': {'input_tokens': 1, 'output_tokens': 1, 'total_tokens': 2}}
    events = [{'type': 'response.created', 'response': {**response, 'status': 'in_progress', 'output': []}},
              {'type': 'response.output_item.added', 'output_index': 0, 'item': item}]
    if not name:
        events.append({'type': 'response.output_text.delta', 'item_id': item['id'], 'output_index': 0,
                       'content_index': 0, 'delta': '查询完成'})
    events.extend([{'type': 'response.output_item.done', 'output_index': 0, 'item': item},
                   {'type': 'response.completed', 'response': response}])
    return ''.join('event: '+e['type']+'\ndata: '+json.dumps({**e, 'sequence_number': i})+'\n\n'
                   for i, e in enumerate(events))


@pytest.mark.parametrize('mode', ['chat_completions', 'responses'])
async def test_discover_cross_domain_and_reset_next_run(settings, monkeypatch, mode):
    settings.llm.api_mode = mode
    requests, calls, answers = [], [], []
    def provider(request):
        body = json.loads(request.content)
        step = len(requests)
        requests.append(body)
        names = {t.get('function', t)['name'] for t in body['tools']}
        assert 'discover_tools' in names
        assert 'search_service_logs' not in names
        if step in (0, 3):
            assert 'list_models' in names and 'list_train_tasks' not in names
        else:
            assert {'list_models', 'list_train_tasks'} <= names
        name, args = (('discover_tools', {'domain': 'training'}) if step == 0 else
                      ('list_train_tasks', {'name': '', 'page': 1, 'page_size': 10}) if step == 1 else (None, None))
        return httpx.Response(200, headers={'content-type': 'text/event-stream'},
                              content=sse(mode, body['model'], step, name, args).encode())
    def client(**kwargs):
        kwargs.pop('http_client')
        return AsyncOpenAI(**kwargs, http_client=httpx.AsyncClient(transport=httpx.MockTransport(provider)))
    monkeypatch.setattr('app.agent_engine.AsyncOpenAI', client)
    async def invoke(name, args):
        calls.append(name)
        return discover(args) if name == 'discover_tools' else {'ok': True, 'data': []}
    async def delta(text):
        answers.append(text)
    engine = AgentEngine(settings)
    final, history, usage = await engine.run([], '查询模型', {}, invoke, delta)
    assert final == '查询完成' and calls == ['discover_tools', 'list_train_tasks']
    assert len(requests) == 3 and answers
    await engine.run(history, '继续查询模型', {}, invoke, delta)
    assert len(requests) == 4


async def test_concurrent_runs_do_not_share_loaded_tools(settings, monkeypatch):
    import asyncio
    steps = {'A': 0, 'B': 0}
    async def provider(request):
        body = json.loads(request.content)
        system = body['messages'][0]['content']
        label = 'A' if '"marker": "A"' in system else 'B'
        step = steps[label]
        steps[label] += 1
        names = {t['function']['name'] for t in body['tools']}
        if label == 'A':
            assert 'list_models' in names and 'list_train_tasks' not in names
            assert ('search_service_logs' in names) == (step > 0)
            name, args = ('discover_tools', {'domain': 'logs'}) if step == 0 else (None, None)
        else:
            assert 'list_train_tasks' in names and 'list_models' not in names
            assert 'search_service_logs' not in names
            name, args = ('list_train_tasks', {}) if step == 0 else (None, None)
        await asyncio.sleep(.01)
        return httpx.Response(200, headers={'content-type': 'text/event-stream'},
                              content=sse('chat_completions', body['model'], step, name, args).encode())
    def client(**kwargs):
        kwargs.pop('http_client')
        return AsyncOpenAI(**kwargs, http_client=httpx.AsyncClient(transport=httpx.MockTransport(provider)))
    monkeypatch.setattr('app.agent_engine.AsyncOpenAI', client)
    async def invoke(name, args):
        return discover(args) if name == 'discover_tools' else {'ok': True, 'data': []}
    async def delta(text):
        pass
    engine = AgentEngine(settings)
    answers = await asyncio.gather(
        engine.run([], '模型', {'marker': 'A'}, invoke, delta),
        engine.run([], '训练', {'marker': 'B'}, invoke, delta),
    )
    assert steps == {'A': 2, 'B': 2}
    assert all(answer[0] == '查询完成' for answer in answers)
