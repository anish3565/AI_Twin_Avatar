import json
import os
from collections.abc import AsyncIterator
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


async def _groq_stream(messages: list[dict], info: dict) -> AsyncIterator[str]:
    model = os.environ.get("GROQ_MODEL", "openai/gpt-oss-120b")
    info.update(provider="groq", model=model, fallback_used=False)
    payload = {
        "model": model,
        "messages": messages,
        "temperature": 0,
        "stream": True,
        "stream_options": {"include_usage": True},
    }
    async with httpx.AsyncClient(timeout=TIMEOUT_SECONDS) as client:
        async with client.stream(
            "POST",
            GROQ_URL,
            headers={"Authorization": f"Bearer {os.environ['GROQ_API_KEY']}"},
            json=payload,
        ) as r:
            r.raise_for_status()
            async for line in r.aiter_lines():
                if not line.startswith("data: "):
                    continue
                data_text = line[len("data: "):]
                if data_text.strip() == "[DONE]":
                    break
                data = json.loads(data_text)
                usage = data.get("usage")
                if usage:
                    info["prompt_tokens"] = usage.get("prompt_tokens")
                    info["completion_tokens"] = usage.get("completion_tokens")
                choices = data.get("choices") or []
                delta = choices[0].get("delta", {}).get("content") if choices else None
                if delta:
                    yield delta


async def stream(messages: list[dict], info: dict) -> AsyncIterator[str]:
    yielded = False
    try:
        async for delta in _groq_stream(messages, info):
            yielded = True
            yield delta
    except Exception:
        if yielded:
            raise
        result = await _gemini(messages)
        info.update(
            provider=result.provider,
            model=result.model,
            fallback_used=True,
            prompt_tokens=result.prompt_tokens,
            completion_tokens=result.completion_tokens,
        )
        yield result.text


async def complete(messages: list[dict]) -> LLMResult:
    try:
        return await _groq(messages)
    except Exception:
        return await _gemini(messages)
