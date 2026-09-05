# Task 3 Report: OpenRouter Wrapper

## Outcome
Implemented `shared/llm.py` with `chat(...)` and `chat_sync(...)` using `OPENROUTER_API_KEY`, `OPENROUTER_MODEL` defaulting to `openai/gpt-4o-mini`, `LLM_TIMEOUT`, and a single retry on `httpx.ConnectError` only.

## RED
- `pytest outskillai/tests/test_llm.py -q`
- Initial failure: `ModuleNotFoundError: No module named 'shared.llm'`

## GREEN
- `pytest outskillai/tests/test_llm.py -q`
- Result: `3 passed`
- `pytest -q`
- Result: `5 passed`

## Notes
- Timeout exceptions are not retried.
- A first connection error is retried once; a second connection error is surfaced.
- LangSmith/tracing-related env handling is wrapped so it cannot raise into callers.
