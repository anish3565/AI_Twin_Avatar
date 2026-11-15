import os
from dataclasses import dataclass

import httpx

GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
TIMEOUT_SECONDS = 20


@dataclass
class LLMResult:
    text: str
    provider: str
    model: str
    prompt_tokens: int | None
    completion_tokens: int | None
    fallback_used: bool


async def _groq(messages: list[dict]) -> LLMResult:
    model = os.environ.get("GROQ_MODEL", "openai/gpt-oss-120b")
    async with httpx.AsyncClient(timeout=TIMEOUT_SECONDS) as client:
        r = await client.post(
            GROQ_URL,
            headers={"Authorization": f"Bearer {os.environ['GROQ_API_KEY']}"},
            json={"model": model, "messages": messages, "temperature": 0},
        )
        r.raise_for_status()
    data = r.json()
    usage = data.get("usage", {})
    return LLMResult(
        text=data["choices"][0]["message"]["content"].strip(),
        provider="groq",
        model=model,
        prompt_tokens=usage.get("prompt_tokens"),
        completion_tokens=usage.get("completion_tokens"),
        fallback_used=False,
    )


async def _gemini(messages: list[dict]) -> LLMResult:
    model = os.environ.get("GEMINI_MODEL", "gemini-3.5-flash")
    system = "\n".join(m["content"] for m in messages if m["role"] == "system")
    user = "\n".join(m["content"] for m in messages if m["role"] == "user")
    async with httpx.AsyncClient(timeout=TIMEOUT_SECONDS) as client:
        r = await client.post(
            GEMINI_URL.format(model=model),
            headers={"x-goog-api-key": os.environ["GEMINI_API_KEY"]},
            json={
                "systemInstruction": {"parts": [{"text": system}]},
                "contents": [{"role": "user", "parts": [{"text": user}]}],
                "generationConfig": {"temperature": 0},
            },
        )
        r.raise_for_status()
    data = r.json()
    usage = data.get("usageMetadata", {})
    return LLMResult(
        text=data["candidates"][0]["content"]["parts"][0]["text"].strip(),
        provider="gemini",
        model=model,
        prompt_tokens=usage.get("promptTokenCount"),
        completion_tokens=usage.get("candidatesTokenCount"),
        fallback_used=True,
    )


async def complete(messages: list[dict]) -> LLMResult:
    try:
        return await _groq(messages)
    except Exception:
        return await _gemini(messages)
