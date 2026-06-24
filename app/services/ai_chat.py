import os
import json
import httpx
from typing import AsyncGenerator

# Cliente generico compatible con el formato OpenAI chat/completions.
# Gemini, Groq y OpenRouter (entre otros) hablan este mismo formato,
# asi que cambiar de proveedor es solo cuestion de cambiar estas 3 env vars,
# sin tocar código.
AI_BASE_URL = os.getenv("AI_BASE_URL", "https://generativelanguage.googleapis.com/v1beta/openai")
AI_API_KEY  = os.getenv("AI_API_KEY", "")
AI_MODEL    = os.getenv("AI_MODEL", "gemini-2.0-flash")


class AIChatError(Exception):
    pass


async def chat_completion(messages: list[dict]) -> str:
    if not AI_API_KEY:
        raise AIChatError("AI_API_KEY no configurada")

    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(
            f"{AI_BASE_URL.rstrip('/')}/chat/completions",
            headers={"Authorization": f"Bearer {AI_API_KEY}"},
            json={"model": AI_MODEL, "messages": messages},
        )
        if resp.status_code >= 400:
            raise AIChatError(f"AI provider error {resp.status_code}: {resp.text[:300]}")
        data = resp.json()
        return data["choices"][0]["message"]["content"]


async def chat_completion_stream(messages: list[dict]) -> AsyncGenerator[str, None]:
    """Yield fragmentos de texto a medida que el modelo los va generando (SSE)."""
    if not AI_API_KEY:
        raise AIChatError("AI_API_KEY no configurada")

    async with httpx.AsyncClient(timeout=60) as client:
        async with client.stream(
            "POST",
            f"{AI_BASE_URL.rstrip('/')}/chat/completions",
            headers={"Authorization": f"Bearer {AI_API_KEY}"},
            json={"model": AI_MODEL, "messages": messages, "stream": True},
        ) as resp:
            if resp.status_code >= 400:
                raw = await resp.aread()
                raise AIChatError(f"AI provider error {resp.status_code}: {raw[:300]}")

            async for line in resp.aiter_lines():
                if not line.startswith("data: "):
                    continue
                payload = line[len("data: "):].strip()
                if payload == "[DONE]":
                    break
                try:
                    obj   = json.loads(payload)
                    delta = obj["choices"][0]["delta"].get("content")
                except (json.JSONDecodeError, KeyError, IndexError):
                    continue
                if delta:
                    yield delta


async def get_rate_limit_status() -> dict:
    """Hace un request minimo (max_tokens=1) solo para leer los headers de rate limit."""
    if not AI_API_KEY:
        raise AIChatError("AI_API_KEY no configurada")

    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.post(
            f"{AI_BASE_URL.rstrip('/')}/chat/completions",
            headers={"Authorization": f"Bearer {AI_API_KEY}"},
            json={"model": AI_MODEL, "messages": [{"role": "user", "content": "hi"}], "max_tokens": 1},
        )
        if resp.status_code >= 400:
            raise AIChatError(f"AI provider error {resp.status_code}: {resp.text[:300]}")
        h = resp.headers
        return {
            "limit_requests":     h.get("x-ratelimit-limit-requests"),
            "remaining_requests": h.get("x-ratelimit-remaining-requests"),
            "reset_requests":     h.get("x-ratelimit-reset-requests"),
            "limit_tokens":       h.get("x-ratelimit-limit-tokens"),
            "remaining_tokens":   h.get("x-ratelimit-remaining-tokens"),
            "reset_tokens":       h.get("x-ratelimit-reset-tokens"),
        }
