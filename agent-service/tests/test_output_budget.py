import httpx
import pytest
from sqlalchemy import select
from app.models import Session
from conftest import ready, BUSINESS


@pytest.mark.parametrize("length,expected_truncated", [(60000, False), (210000, True)])
def test_large_tool_response_respects_expanded_budget(
    client, app, length, expected_truncated
):
    ready(client)
    app.state.config.runtime.max_tool_output_chars = 200000

    def upstream(request):
        if request.url.path.endswith("/models/queryList"):
            return httpx.Response(
                200,
                json={
                    "result": {
                        "code": 0,
                        "count": 1,
                        "models": [
                            {"id": "full-model-id", "description": "x" * length}
                        ],
                    }
                },
            )
        return app.test_upstream(request)

    app.state.platform.transport = httpx.MockTransport(upstream)
    with app.state.db() as db:
        sid = db.scalar(select(Session).where(Session.user_id.is_not(None))).id
    result = app.state.platform.execute(
        sid, None, BUSINESS, "list_models", {"page": 1, "page_size": 1}, "budget-test"
    )
    assert result["truncated"] is expected_truncated
    if expected_truncated:
        assert result["data"] is None
    else:
        record = result["data"]["result"]["models"][0]
        assert record["id"] == "full-model-id"
        assert record["description"] == "x" * length
