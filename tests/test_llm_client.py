"""Tests for foedus.agents.llm.client — pluggable LLM backends.

StubLLMClient is the deterministic backend used everywhere else in this
test suite; OllamaClient/ClaudeClient are only checked for env-driven
construction here (no real network calls — see tests/smoke for the
opt-in real-Ollama check).
"""

from __future__ import annotations

import pytest

from foedus.agents.llm.client import (
    ClaudeClient,
    OllamaClient,
    StubLLMClient,
    make_client_from_env,
)


def test_stub_client_returns_scripted_responses_in_order() -> None:
    client = StubLLMClient(["first", "second"])
    assert client.complete("sys", "user1") == "first"
    assert client.complete("sys", "user2") == "second"


def test_stub_client_records_calls() -> None:
    client = StubLLMClient(["a", "b"])
    client.complete("sys1", "user1")
    client.complete("sys2", "user2")
    assert client.calls == [("sys1", "user1"), ("sys2", "user2")]


def test_stub_client_raises_when_exhausted() -> None:
    client = StubLLMClient(["only"])
    client.complete("sys", "user")
    with pytest.raises(RuntimeError):
        client.complete("sys", "user")


def test_ollama_client_reads_model_and_host_from_env(monkeypatch) -> None:
    monkeypatch.setenv("FOEDUS_LLM_MODEL", "llama3.1:8b")
    monkeypatch.setenv("OLLAMA_HOST", "http://example:1234")
    client = OllamaClient()
    assert client.model == "llama3.1:8b"
    assert client.host == "http://example:1234"


def test_ollama_client_has_sane_defaults(monkeypatch) -> None:
    monkeypatch.delenv("FOEDUS_LLM_MODEL", raising=False)
    monkeypatch.delenv("OLLAMA_HOST", raising=False)
    client = OllamaClient()
    assert client.model
    assert client.host.startswith("http://")


class _FakeResponse:
    def __init__(self, content: str) -> None:
        self._content = content

    def raise_for_status(self) -> None:
        pass

    def json(self) -> dict:
        return {"message": {"content": self._content}}


def _capture_post(monkeypatch):
    """Patch httpx.post to record the JSON payload and return a canned reply."""
    captured: dict = {}

    def fake_post(url, json, timeout):  # noqa: A002 - mirror httpx's kwarg name
        captured["url"] = url
        captured["json"] = json
        captured["timeout"] = timeout
        return _FakeResponse("ok")

    import httpx
    monkeypatch.setattr(httpx, "post", fake_post)
    return captured


def test_ollama_default_sends_no_format_key(monkeypatch) -> None:
    """Existing callers are unaffected: with no schema the request carries no
    `format` key at all (byte-identical to the pre-G2 payload)."""
    captured = _capture_post(monkeypatch)
    OllamaClient(model="m").complete("sys", "user")
    assert "format" not in captured["json"]
    assert captured["json"]["model"] == "m"
    assert captured["json"]["stream"] is False
    assert captured["json"]["messages"] == [
        {"role": "system", "content": "sys"},
        {"role": "user", "content": "user"},
    ]


def test_ollama_instance_format_is_sent(monkeypatch) -> None:
    captured = _capture_post(monkeypatch)
    schema = {"type": "object"}
    OllamaClient(model="m", format=schema).complete("sys", "user")
    assert captured["json"]["format"] == schema


def test_ollama_per_call_format_is_sent(monkeypatch) -> None:
    captured = _capture_post(monkeypatch)
    schema = {"type": "object", "required": ["orders"]}
    OllamaClient(model="m").complete("sys", "user", format=schema)
    assert captured["json"]["format"] == schema


def test_ollama_per_call_format_overrides_instance(monkeypatch) -> None:
    captured = _capture_post(monkeypatch)
    inst = {"type": "object", "title": "instance"}
    call = {"type": "object", "title": "percall"}
    OllamaClient(model="m", format=inst).complete("sys", "user", format=call)
    assert captured["json"]["format"] == call


def test_ollama_complete_still_matches_protocol_two_arg_call(monkeypatch) -> None:
    """A caller using the base LLMClient protocol (system, user) keeps working;
    the new `format` arg is optional and defaults to unconstrained."""
    _capture_post(monkeypatch)
    assert OllamaClient(model="m").complete("sys", "user") == "ok"


def test_claude_client_reads_model_and_key_from_env(monkeypatch) -> None:
    monkeypatch.setenv("FOEDUS_LLM_MODEL", "claude-haiku-4-5-20251001")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test-123")
    client = ClaudeClient()
    assert client.model == "claude-haiku-4-5-20251001"
    assert client._api_key == "sk-test-123"


def test_claude_client_construction_requires_no_import(monkeypatch) -> None:
    """Constructing ClaudeClient must not import `anthropic` — only calling
    complete() does. This keeps local-only (Ollama) runs free of the dep."""
    import sys
    monkeypatch.setitem(sys.modules, "anthropic", None)
    # Constructing must not raise even though "anthropic" is unimportable.
    ClaudeClient()


def test_make_client_from_env_defaults_to_ollama(monkeypatch) -> None:
    monkeypatch.delenv("FOEDUS_LLM_BACKEND", raising=False)
    client = make_client_from_env()
    assert isinstance(client, OllamaClient)


def test_make_client_from_env_selects_claude(monkeypatch) -> None:
    monkeypatch.setenv("FOEDUS_LLM_BACKEND", "claude")
    client = make_client_from_env()
    assert isinstance(client, ClaudeClient)


def test_make_client_from_env_rejects_unknown_backend(monkeypatch) -> None:
    monkeypatch.setenv("FOEDUS_LLM_BACKEND", "bogus")
    with pytest.raises(ValueError):
        make_client_from_env()
