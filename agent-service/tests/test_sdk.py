"""Exercise real SDK streaming and tool-result round-trip against a fake HTTP provider."""

import json
import httpx
from openai import AsyncOpenAI
from app.agent_engine import AgentEngine


async def test_sdk_chat_completions_tool_roundtrip(settings, monkeypatch):
    requests = []

    def handle(request):
        data = json.loads(request.content)
        requests.append(data)
        assert request.url.path.endswith("/chat/completions")
        assert data["model"] == settings.llm.model
        if len(requests) == 1:
            chunks = [
                {
                    "role": "assistant",
                    "tool_calls": [
                        {
                            "index": 0,
                            "id": "call_test",
                            "type": "function",
                            "function": {
                                "name": "list_models",
                                "arguments": '{"name":"推荐","page":1,"page_size":10}',
                            },
                        }
                    ],
                },
                {},
            ]
            finish = "tool_calls"
        else:
            assert any(m.get("role") == "tool" for m in data["messages"])
            chunks = [
                {"role": "assistant", "content": "已查询到"},
                {"content": "推荐模型"},
            ]
            finish = "stop"
        events = []
        for i, delta in enumerate(chunks):
            events.append(
                "data: "
                + json.dumps(
                    {
                        "id": "chatcmpl-test",
                        "object": "chat.completion.chunk",
                        "created": 1,
                        "model": settings.llm.model,
                        "choices": [
                            {
                                "index": 0,
                                "delta": delta,
                                "finish_reason": finish
                                if i == len(chunks) - 1
                                else None,
                            }
                        ],
                    }
                )
            )
        return httpx.Response(
            200,
            headers={"content-type": "text/event-stream"},
            content=("\n\n".join(events) + "\n\ndata: [DONE]\n\n").encode(),
        )

    def client(**kwargs):
        kwargs.pop("http_client")
        return AsyncOpenAI(
            **kwargs,
            http_client=httpx.AsyncClient(transport=httpx.MockTransport(handle)),
        )

    monkeypatch.setattr("app.agent_engine.AsyncOpenAI", client)
    calls = []
    deltas = []

    async def invoke(name, args):
        calls.append((name, args))
        return {"ok": True, "data": [{"id": "m1", "name": "推荐模型"}]}

    async def delta(value):
        deltas.append(value)

    answer, history, usage = await AgentEngine(settings).run(
        [], "查询模型", {"environment": "dev"}, invoke, delta
    )
    assert calls[0][0] == "list_models"
    assert answer == "已查询到推荐模型"
    assert "".join(deltas) == answer
    assert len(requests) == 2
    assert any(item.get("type") == "function_call_output" for item in history)
