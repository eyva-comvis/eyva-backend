"""Tes AI rekomendasi: klien LLM dengan transport palsu (tanpa jaringan) dan fallback."""
import asyncio
import json

import httpx
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import app
from app.services import llm
from app.services.insights import LOOPA_CONTEXT, break_context, fallback_break_tip, generate_break_tip, generate_insight
from app.schemas.models import SummaryOut


def _settings(key="k") -> Settings:
    return Settings(llm_api_key=key, llm_model="deepseek/test:free", llm_base_url="https://llm.example/v1")


def _summary(**kw) -> SummaryOut:
    base = dict(session_id="s", status="ENDED", end_reason="COMPLETED", total_study_seconds=1500, total_break_seconds=300,
                total_pause_seconds=10, blocks_completed=1, blocks_stopped_early=0, blink_count=300, yawn_count=2,
                eye_closure_count=1, estimated_drowsy_seconds=40, alert_1_count=1, alert_2_count=0, events=[])
    return SummaryOut(**(base | kw))


def _ok_transport(captured: list, content="Take a short walk."):
    def handler(req: httpx.Request) -> httpx.Response:
        captured.append(json.loads(req.content))
        captured.append(dict(req.headers))
        return httpx.Response(200, json={"choices": [{"message": {"content": content}}]})
    return httpx.MockTransport(handler)


def test_chat_sends_context_model_and_strips_think():
    cap: list = []
    out = asyncio.run(llm.chat(_settings(), "SYS", "USER", transport=_ok_transport(cap, "<think>hmm</think>  Hello  ")))
    assert out.text == "Hello" and out.model == "deepseek/test:free"
    body, headers = cap
    assert body["model"] == "deepseek/test:free"
    assert body["messages"][0] == {"role": "system", "content": "SYS"}
    assert headers["authorization"] == "Bearer k"


def test_chat_without_key_or_on_error_returns_none():
    assert asyncio.run(llm.chat(_settings(key=""), "s", "u")) is None
    bad = httpx.MockTransport(lambda r: httpx.Response(429, json={"error": "rate limit"}))
    assert asyncio.run(llm.chat(_settings(), "s", "u", transport=bad)) is None
    boom = httpx.MockTransport(lambda r: (_ for _ in ()).throw(httpx.ConnectError("down")))
    assert asyncio.run(llm.chat(_settings(), "s", "u", transport=boom)) is None


def test_generate_insight_uses_llm_and_never_sends_frames(monkeypatch):
    seen = {}

    async def fake_chat(settings, system, user, **kw):
        seen.update(system=system, user=user)
        return llm.ChatResult("Great session. Try a stretch.", "m1")

    monkeypatch.setattr(llm, "chat", fake_chat)
    r = asyncio.run(generate_insight(_summary(), _settings()))
    assert r.source == "llm" and r.text.startswith("Great") and r.model == "m1"
    assert seen["system"] == LOOPA_CONTEXT and "image" not in seen["user"].lower()
    assert '"blinks_per_minute": 12.0' in seen["user"]


def test_insight_falls_back_when_llm_unavailable(monkeypatch):
    async def none_chat(*a, **kw):
        return None

    monkeypatch.setattr(llm, "chat", none_chat)
    r = asyncio.run(generate_insight(_summary(), _settings()))
    assert r.source == "fallback" and r.text


def test_break_tip_endpoint_fallback_and_context():
    with TestClient(app) as c:
        sid = c.post("/sessions", json={"configured_study_seconds": 60, "configured_break_seconds": 60}).json()["id"]
        c.post(f"/sessions/{sid}/blocks")
        bid = next(iter(app.state.store.get(sid).blocks))
        c.post(f"/sessions/{sid}/blocks/{bid}/complete")
        ctx = break_context(app.state.store.get(sid))
        assert ctx["block_number"] == 1 and ctx["camera_data_available"] is False
        r = c.post(f"/sessions/{sid}/break-tip")
        assert r.status_code == 200 and r.json()["text"]  # tanpa key: fallback
        assert c.post("/sessions/does-not-exist/break-tip").status_code == 404


def test_break_tip_llm_path(monkeypatch):
    async def fake_chat(settings, system, user, **kw):
        return llm.ChatResult("Stretch your shoulders.", "m2")

    monkeypatch.setattr(llm, "chat", fake_chat)
    ctx = {"last_block_alert_2": 0, "last_block_alert_1": 0, "session_yawns": 0, "session_prolonged_eye_closures": 0}
    assert asyncio.run(generate_break_tip(ctx, _settings())).source == "llm"
    assert "two alerts" in fallback_break_tip({**ctx, "last_block_alert_2": 1}).text


def test_chat_sends_reasoning_controls_and_drops_leaked_reasoning():
    cap: list = []
    asyncio.run(llm.chat(_settings(), "S", "U", transport=_ok_transport(cap)))
    assert "reasoning" not in cap[0]  # provider non-OpenRouter (mis. Groq) bisa menolak parameter ini
    cap_or: list = []
    s_or = Settings(llm_api_key="k", llm_model="m:free", llm_base_url="https://openrouter.ai/api/v1")
    asyncio.run(llm.chat(s_or, "S", "U", transport=_ok_transport(cap_or)))
    assert cap_or[0]["reasoning"] == {"effort": "low", "exclude": True}
    cap_g: list = []
    s_g = Settings(llm_api_key="k", llm_model="openai/gpt-oss-120b", llm_base_url="https://api.groq.com/openai/v1")
    asyncio.run(llm.chat(s_g, "S", "U", transport=_ok_transport(cap_g)))
    assert cap_g[0]["reasoning_effort"] == "low" and "reasoning" not in cap_g[0]
    leak = _ok_transport([], "I need to write ONE short tip for the Break page: 2-3 sentences...")
    assert asyncio.run(llm.chat(_settings(), "S", "U", transport=leak)) is None
    ok = _ok_transport([], "Stand up and stretch for a minute.")
    assert asyncio.run(llm.chat(_settings(), "S", "U", transport=ok)).text.startswith("Stand")


def test_chat_tries_backup_model_after_primary_keeps_leaking():
    asked: list[str] = []

    def handler(req: httpx.Request) -> httpx.Response:
        model = json.loads(req.content)["model"]
        asked.append(model)
        text = "I need to write a tip..." if model == "primary:free" else "Stretch and drink water."
        return httpx.Response(200, json={"choices": [{"message": {"content": text}}]})

    s = Settings(llm_api_key="k", llm_model="primary:free", llm_fallback_models="backup:free", llm_base_url="https://x/v1")
    res = asyncio.run(llm.chat(s, "S", "U", transport=httpx.MockTransport(handler)))
    assert res.model == "backup:free" and res.text.startswith("Stretch")
    assert asked == ["primary:free", "primary:free", "backup:free"]  # primary dicoba 2x lalu pindah


def test_chat_total_budget_stops_attempts():
    s = Settings(llm_api_key="k", llm_model="a", llm_fallback_models="b,c", llm_total_seconds=0.0, llm_base_url="https://x/v1")
    called = []
    t = httpx.MockTransport(lambda r: called.append(1) or httpx.Response(200, json={"choices": [{"message": {"content": "ok"}}]}))
    assert asyncio.run(llm.chat(s, "S", "U", transport=t)) is None and not called


def test_reasoning_detector_catches_leaks_anywhere_but_not_good_answers():
    bad = [
        "The user had a very short study session. I need to write 3-5 sentences.",
        "They got 1 prolonged eye closure, which triggered Alert 1.",
        "Short session. Let me write the recommendation now.",
        "Okay, let's think about this.",
    ]
    good = [
        "You studied for about 25 minutes with a steady rhythm. Try standing up and stretching during your next break.",
        "Stand up, stretch your arms overhead, and look out a window for 20 seconds.",
    ]
    assert all(llm.looks_like_reasoning(t) for t in bad)
    assert not any(llm.looks_like_reasoning(t) for t in good)
