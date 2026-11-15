import pytest
from fastapi.testclient import TestClient

from app import db, llm, main
from app.llm import LLMResult


@pytest.fixture
def saved(monkeypatch):
    calls = {"messages": [], "sessions": []}
    monkeypatch.setattr(db, "save_message", lambda **kw: calls["messages"].append(kw))
    monkeypatch.setattr(db, "create_session", lambda sid, code: calls["sessions"].append((sid, code)))
    monkeypatch.setenv("CONTACT_EMAIL", "anish@example.com")
    monkeypatch.setenv("CONTACT_LINKEDIN", "https://linkedin.com/in/example")
    return calls


def stub_llm(monkeypatch, text, fallback=False):
    async def fake(messages):
        return LLMResult(
            text=text,
            provider="gemini" if fallback else "groq",
            model="stub",
            prompt_tokens=10,
            completion_tokens=5,
            fallback_used=fallback,
        )

    monkeypatch.setattr(llm, "complete", fake)


def test_session_returns_id_and_logs(saved):
    client = TestClient(main.app)
    r = client.post("/session", json={"invite_code": None})
    assert r.status_code == 200
    assert saved["sessions"] == [(r.json()["session_id"], None)]


def test_chat_answered(monkeypatch, saved):
    stub_llm(monkeypatch, "I built a chatbot for STPI.")
    client = TestClient(main.app)
    r = client.post("/chat", json={"session_id": "s1", "message": "What did you build?"})
    body = r.json()
    assert body["outcome"] == "answered"
    assert body["reply"] == "I built a chatbot for STPI."
    logged = saved["messages"][0]
    assert logged["outcome"] == "answered"
    assert logged["fallback_used"] is False


def test_chat_unknown_offers_contact(monkeypatch, saved):
    stub_llm(monkeypatch, "UNKNOWN")
    client = TestClient(main.app)
    r = client.post("/chat", json={"session_id": "s1", "message": "What is your salary?"})
    body = r.json()
    assert body["outcome"] == "unknown"
    assert "anish@example.com" in body["reply"]
    assert saved["messages"][0]["outcome"] == "unknown"


def test_chat_fallback_is_recorded(monkeypatch, saved):
    stub_llm(monkeypatch, "Some answer.", fallback=True)
    client = TestClient(main.app)
    client.post("/chat", json={"session_id": "s1", "message": "Hi"})
    assert saved["messages"][0]["provider"] == "gemini"
    assert saved["messages"][0]["fallback_used"] is True


def test_chat_error_when_both_providers_fail(monkeypatch, saved):
    async def boom(messages):
        raise RuntimeError("down")

    monkeypatch.setattr(llm, "complete", boom)
    client = TestClient(main.app)
    r = client.post("/chat", json={"session_id": "s1", "message": "Hi"})
    assert r.json()["outcome"] == "error"
    assert saved["messages"][0]["error_type"] == "RuntimeError"


def test_chat_rejects_empty_message(saved):
    client = TestClient(main.app)
    r = client.post("/chat", json={"session_id": "s1", "message": ""})
    assert r.status_code == 422
