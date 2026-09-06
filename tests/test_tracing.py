import os

from shared.tracing import apply_langsmith_aliases, run_config, tracing_enabled


def test_apply_langsmith_aliases_fills_legacy_names(monkeypatch):
    monkeypatch.delenv("LANGCHAIN_TRACING_V2", raising=False)
    monkeypatch.delenv("LANGCHAIN_API_KEY", raising=False)
    monkeypatch.delenv("LANGCHAIN_PROJECT", raising=False)
    monkeypatch.delenv("LANGCHAIN_ENDPOINT", raising=False)
    monkeypatch.setenv("LANGSMITH_TRACING", "true")
    monkeypatch.setenv("LANGSMITH_API_KEY", "lsv2_pt_test")
    monkeypatch.setenv("LANGSMITH_PROJECT", "pactlify")
    monkeypatch.setenv("LANGSMITH_ENDPOINT", "https://api.smith.langchain.com")

    apply_langsmith_aliases()

    assert os.environ["LANGCHAIN_TRACING_V2"] == "true"
    assert os.environ["LANGCHAIN_API_KEY"] == "lsv2_pt_test"
    assert os.environ["LANGCHAIN_PROJECT"] == "pactlify"
    assert os.environ["LANGCHAIN_ENDPOINT"] == "https://api.smith.langchain.com"
    assert tracing_enabled() is True


def test_apply_langsmith_aliases_fills_current_names(monkeypatch):
    monkeypatch.delenv("LANGSMITH_TRACING", raising=False)
    monkeypatch.delenv("LANGSMITH_API_KEY", raising=False)
    monkeypatch.delenv("LANGSMITH_PROJECT", raising=False)
    monkeypatch.setenv("LANGCHAIN_TRACING_V2", "true")
    monkeypatch.setenv("LANGCHAIN_API_KEY", "lsv2_pt_legacy")
    monkeypatch.setenv("LANGCHAIN_PROJECT", "pactlify")

    apply_langsmith_aliases()

    assert os.environ["LANGSMITH_TRACING"] == "true"
    assert os.environ["LANGSMITH_API_KEY"] == "lsv2_pt_legacy"
    assert os.environ["LANGSMITH_PROJECT"] == "pactlify"


def test_run_config_tags_source_and_job():
    config = run_config(source="fastapi", job_id="job_1")
    assert config["run_name"] == "pactlify"
    assert "pactlify" in config["tags"]
    assert "fastapi" in config["tags"]
    assert config["metadata"]["job_id"] == "job_1"
