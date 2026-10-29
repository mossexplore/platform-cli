"""Discovery uses the existing session, audit, progress and bounded run pipeline."""
from sqlalchemy import select
from app.models import ToolCall
from conftest import ready, headers
from test_runs import run_request, wait


class DiscoverEngine:
    def __init__(self, after=None, count=1, business=False):
        self.after, self.count, self.business = after, count, business
        self.results = []

    async def run(self, history, message, context, invoke, delta, progress=None):
        for _ in range(self.count):
            self.results.append(await invoke('discover_tools', {'domain': 'models'}))
        if self.after:
            self.after()
        if self.business:
            await invoke('list_models', {'page': 1, 'page_size': 10, 'name': ''})
        await delta('完成')
        return '完成', [], {'requests': 1}


def test_discovery_audited_without_platform_data_call(client, app):
    engine = DiscoverEngine()
    app.state.runs.engine = engine
    _, _, rid = run_request(client)
    assert wait(client, rid)['status'] == 'completed'
    assert engine.results[0]['tools'][0]['name'] == 'list_models'
    assert not any('/models/' in r.url.path for r in app.test_upstream.calls)
    with app.state.db() as db:
        rows = db.scalars(select(ToolCall).where(ToolCall.run_id == rid)).all()
        assert len(rows) == 1 and rows[0].name == 'discover_tools' and rows[0].status == 'completed'
    events = client.get('/api/runs/'+rid+'/events').text
    assert 'discover_tools' in events and 'tool.completed' in events


def test_discovery_never_grants_platform_permission(client, app):
    def revoke():
        app.test_upstream.allow = False
    app.state.runs.engine = DiscoverEngine(after=revoke, business=True)
    _, _, rid = run_request(client)
    assert wait(client, rid)['status'] == 'failed'
    assert not any('/models/' in r.url.path for r in app.test_upstream.calls)
    with app.state.db() as db:
        rows = {r.name: r.status for r in db.scalars(select(ToolCall).where(ToolCall.run_id == rid))}
        assert rows == {'discover_tools': 'completed', 'list_models': 'failed'}


def test_discovery_limit_returns_actionable_result_and_records_failure(client, app):
    app.state.config.runtime.max_discovery_calls = 1
    engine = DiscoverEngine(count=2)
    app.state.runs.engine = engine
    _, _, rid = run_request(client)
    assert wait(client, rid)['status'] == 'completed'
    assert engine.results[1]['error'] == 'DISCOVERY_LIMIT'
    with app.state.db() as db:
        rows = db.scalars(select(ToolCall).where(ToolCall.run_id == rid)).all()
        assert sorted(r.status for r in rows) == ['completed', 'failed']


def test_discovery_counts_against_overall_tool_budget(client, app):
    app.state.config.runtime.max_tool_calls = 1
    app.state.runs.engine = DiscoverEngine(count=2)
    _, _, rid = run_request(client)
    result = wait(client, rid)
    assert result['status'] == 'failed' and '工具调用次数' in result['error']
