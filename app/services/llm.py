"""Klien LLM tipis (API gaya OpenAI /chat/completions). Default: OpenRouter + model gratis.

Urutan percobaan: model utama, lalu tiap model cadangan (LLM_FALLBACK_MODELS). Satu model dicoba ulang sekali bila
kena rate limit (429) atau mengembalikan teks yang tampak seperti proses berpikir; kegagalan lain langsung pindah
ke model berikutnya. Seluruh proses dibatasi LLM_TOTAL_SECONDS. Jika semua gagal, hasilnya None supaya pemanggil
memakai teks fallback dan sesi tetap bisa selesai.
"""
import asyncio
import logging
import re
import time
from typing import NamedTuple

import httpx

from app.core.config import Settings

log = logging.getLogger("llm")


class ChatResult(NamedTuple):
    text: str
    model: str | None  # model yang benar-benar menjawab (bisa model cadangan)


_THINK = re.compile(r"<think>.*?</think>", re.DOTALL | re.IGNORECASE)
# Model reasoning kadang membocorkan proses berpikir ke content (mis. saat token habis). Jangan tampilkan ke pengguna.
_REASONING_LEAK = re.compile(
    r"^\s*(okay|ok,|so,|hmm|let me|let's|i need to|i should|i must|we need to|we should|first,|the user\b|they (got|had|have)\b)",
    re.IGNORECASE,
)
# Penanda proses berpikir yang bisa muncul di MANA SAJA (mis. setelah kalimat pembuka yang tampak wajar).
_REASONING_MARKERS = re.compile(
    r"\bI need to (write|produce|give|craft|make)\b|\bI should (write|give|start)\b|\blet me (write|draft|think|check)\b"
    r"|\b(3|three)\s*(-|to|–)\s*(5|five) sentences\b|\bstart with what the (session )?data shows\b",
    re.IGNORECASE,
)


def looks_like_reasoning(text: str) -> bool:
    return bool(_REASONING_LEAK.match(text) or _REASONING_MARKERS.search(text))


_RETRY = "retry"  # penanda: coba model yang sama sekali lagi


async def _ask(client: httpx.AsyncClient, settings: Settings, headers: dict, model: str,
               system: str, user: str, max_tokens: int) -> "ChatResult | str | None":
    body = {
        "model": model,
        "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
        "temperature": 0.5,
        "max_tokens": max_tokens,
    }
    if "openrouter.ai" in settings.llm_base_url:
        # Model reasoning: batasi dan sembunyikan proses berpikir agar token tidak habis sebelum jawaban.
        # Parameter ini khusus OpenRouter; provider lain (Groq, Gemini) bisa menolaknya.
        body["reasoning"] = {"effort": "low", "exclude": True}
    elif "groq.com" in settings.llm_base_url and model.startswith("openai/gpt-oss"):
        body["reasoning_effort"] = "low"  # proses berpikir gpt-oss ada di field terpisah; batasi agar token cukup untuk jawaban
    try:
        r = await client.post(f"{settings.llm_base_url.rstrip('/')}/chat/completions", json=body, headers=headers)
        if r.status_code == 429:  # model gratis sering kena batas
            log.warning("LLM %s: 429 rate limit", model)
            await asyncio.sleep(1.5)
            return _RETRY
        r.raise_for_status()
        data = r.json()
        text = data["choices"][0]["message"]["content"]
        used = data.get("model") or model
    except Exception as e:  # jaringan, timeout, HTTP error, JSON tak terduga
        log.warning("LLM %s gagal (%s): %s", model, type(e).__name__, e)
        return None
    text = _THINK.sub("", text or "").strip()  # model reasoning kadang menyertakan <think>
    if not text:
        log.warning("LLM %s: jawaban kosong", model)
        return _RETRY
    if looks_like_reasoning(text):
        log.warning("LLM %s: teks tampak seperti proses berpikir; dibuang", used)
        return _RETRY
    return ChatResult(text, used)


async def chat(settings: Settings, system: str, user: str, *, max_tokens: int = 350,
               transport: httpx.AsyncBaseTransport | None = None) -> ChatResult | None:
    if not settings.llm_api_key:
        return None
    headers = {
        "Authorization": f"Bearer {settings.llm_api_key}",
        "Content-Type": "application/json",
        "X-Title": "Loopa Smart Study Assistant",  # atribusi opsional OpenRouter
    }
    models = [settings.llm_model, *[m.strip() for m in settings.llm_fallback_models.split(",") if m.strip()]]
    deadline = time.monotonic() + settings.llm_total_seconds
    async with httpx.AsyncClient(timeout=settings.llm_timeout_seconds, transport=transport) as client:
        for model in models:
            for _attempt in (1, 2):
                if time.monotonic() >= deadline:
                    log.warning("LLM: batas waktu total %.0f dtk habis", settings.llm_total_seconds)
                    return None
                res = await _ask(client, settings, headers, model, system, user, max_tokens)
                if isinstance(res, ChatResult):
                    return res
                if res is None:  # kegagalan keras: pindah ke model berikutnya
                    break
    return None
