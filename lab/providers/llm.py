"""LLM provider — routes to Anthropic or OpenAI, handles retries."""
from __future__ import annotations
import asyncio
import os
from typing import Any
import httpx
from ..core.config import LabConfig, ModelProfile


class LLMProvider:
    def __init__(self, config: LabConfig):
        self.config = config

    async def complete(
        self,
        model: ModelProfile,
        messages: list[dict],
        temperature: float = 0.7,
        max_tokens: int = 8192,
        system: str | None = None,
    ) -> str:
        """Send a completion request. Returns response text."""
        if model.provider == "anthropic":
            return await self._anthropic(model, messages, temperature, max_tokens, system)
        elif model.provider in ("openai", "openrouter"):
            return await self._openai(model, messages, temperature, max_tokens, system)
        raise ValueError(f"Unknown provider: {model.provider}")

    async def _anthropic(
        self,
        model: ModelProfile,
        messages: list[dict],
        temperature: float,
        max_tokens: int,
        system: str | None,
    ) -> str:
        headers = {
            "x-api-key": self.config.anthropic_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        }
        payload: dict[str, Any] = {
            "model": model.id,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
        }
        if system:
            payload["system"] = system

        for attempt in range(3):
            try:
                async with httpx.AsyncClient(timeout=180.0) as client:
                    r = await client.post(
                        "https://api.anthropic.com/v1/messages",
                        headers=headers,
                        json=payload,
                    )
                    r.raise_for_status()
                    data = r.json()
                    return data["content"][0]["text"]
            except (httpx.HTTPStatusError, httpx.TimeoutException) as e:
                if attempt == 2:
                    raise
                await asyncio.sleep(2 ** attempt)
        return ""

    async def _openai(
        self,
        model: ModelProfile,
        messages: list[dict],
        temperature: float,
        max_tokens: int,
        system: str | None,
    ) -> str:
        base = (
            "https://openrouter.ai/api/v1"
            if model.provider == "openrouter"
            else "https://api.openai.com/v1"
        )
        key = (
            os.environ.get("OPENROUTER_API_KEY", "")
            if model.provider == "openrouter"
            else self.config.openai_key
        )
        all_messages = []
        if system:
            all_messages.append({"role": "system", "content": system})
        all_messages.extend(messages)

        for attempt in range(3):
            try:
                async with httpx.AsyncClient(timeout=180.0) as client:
                    r = await client.post(
                        f"{base}/chat/completions",
                        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
                        json={"model": model.id, "messages": all_messages,
                              "temperature": temperature, "max_tokens": max_tokens},
                    )
                    r.raise_for_status()
                    return r.json()["choices"][0]["message"]["content"]
            except (httpx.HTTPStatusError, httpx.TimeoutException):
                if attempt == 2:
                    raise
                await asyncio.sleep(2 ** attempt)
        return ""

    async def complete_parallel(
        self,
        model: ModelProfile,
        prompts: list[str],
        system: str | None = None,
        temperature: float = 0.7,
    ) -> list[str]:
        """Run multiple prompts in parallel against the same model."""
        tasks = [
            self.complete(model, [{"role": "user", "content": p}], temperature, system=system)
            for p in prompts
        ]
        return list(await asyncio.gather(*tasks))
