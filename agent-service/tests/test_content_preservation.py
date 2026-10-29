from app.sanitize import clean


def test_service_id_and_fields_are_never_replaced_or_removed():
    data = {
        "serviceId": "ee06db5f-9715-4dca-91b2-28879fd92d80",
        "token": "1",
        "cookie": "sid=1",
        "authorization": "Bearer value",
        "description": "password=123 token=abc csrftoken=xyz",
        "url": "https://platform.test/log?id=1&token=abc",
        "items": [{"signature": "value", "id": "1"}],
    }
    assert clean(data) == data
    assert "[已隐藏]" not in str(clean(data))


def test_tool_result_passed_to_model_preserves_large_and_sensitive_named_fields(
    client, app
):
    import httpx
    from sqlalchemy import select
    from app.models import Session
    from conftest import ready, BUSINESS

    ready(client)
    model = {
        "id": "ee06db5f-9715-4dca-91b2-28879fd92d80",
        "token": "test-data",
        "url": "https://example.test?id=1&token=abc",
    }

    def upstream(request):
        if request.url.path.endswith("/models/queryList"):
            return httpx.Response(
                200, json={"result": {"code": 0, "count": 1, "models": [model]}}
            )
        return app.test_upstream(request)

    app.state.platform.transport = httpx.MockTransport(upstream)
    with app.state.db() as db:
        sid = db.scalar(select(Session).where(Session.status == "ready")).id
    result = app.state.platform.execute(
        sid, None, BUSINESS, "list_models", {"page": 1, "page_size": 1}, "content-test"
    )
    assert result["data"]["result"]["models"] == [model]
