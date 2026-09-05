import importlib
import sys

import httpx
import pytest


def load_llm(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    monkeypatch.setenv("OPENROUTER_MODEL", "test/model")
    monkeypatch.delenv("LANGSMITH_API_KEY", raising=False)
    monkeypatch.delenv("LANGCHAIN_API_KEY", raising=False)
    monkeypatch.delenv("LANGCHAIN_TRACING_V2", raising=False)
    sys.modules.pop("shared.llm", None)
    return importlib.import_module("shared.llm")


@pytest.mark.asyncio
async def test_chat_does_not_retry_timeouts(monkeypatch):
    llm = load_llm(monkeypatch)
    instances = []

    class FakeAsyncClient:
        def __init__(self, *args, **kwargs):
            self.calls = 0
            instances.append(self)

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def post(self, *args, **kwargs):
            self.calls += 1
            request = httpx.Request("POST", "https://openrouter.ai/api/v1/chat/completions")
            raise httpx.ReadTimeout("timeout", request=request)

    monkeypatch.setattr(llm.httpx, "AsyncClient", FakeAsyncClient)

    with pytest.raises(httpx.ReadTimeout):
        await llm.chat([{"role": "user", "content": "hello"}], timeout=0.1)

    assert instances[0].calls == 1


@pytest.mark.asyncio
async def test_chat_retries_one_connection_error_then_succeeds(monkeypatch):
    llm = load_llm(monkeypatch)
    instances = []

    class FakeAsyncClient:
        def __init__(self, *args, **kwargs):
            self.calls = 0
            instances.append(self)

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def post(self, *args, **kwargs):
            self.calls += 1
            request = httpx.Request("POST", "https://openrouter.ai/api/v1/chat/completions")
            if self.calls == 1:
                raise httpx.ConnectError("connect", request=request)
            return httpx.Response(
                200,
                request=request,
                json={"choices": [{"message": {"content": "ok"}}]},
            )

    monkeypatch.setattr(llm.httpx, "AsyncClient", FakeAsyncClient)

    result = await llm.chat([{"role": "user", "content": "hello"}])

    assert result == "ok"
    assert instances[0].calls == 2


@pytest.mark.asyncio
async def test_chat_raises_after_second_connection_error(monkeypatch):
    llm = load_llm(monkeypatch)
    instances = []

    class FakeAsyncClient:
        def __init__(self, *args, **kwargs):
            self.calls = 0
            instances.append(self)

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def post(self, *args, **kwargs):
            self.calls += 1
            request = httpx.Request("POST", "https://openrouter.ai/api/v1/chat/completions")
            raise httpx.ConnectError("connect", request=request)

    monkeypatch.setattr(llm.httpx, "AsyncClient", FakeAsyncClient)

    with pytest.raises(httpx.ConnectError):
        await llm.chat([{"role": "user", "content": "hello"}])

    assert instances[0].calls == 2

