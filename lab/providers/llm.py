"""LLM provider — routes to Anthropic or OpenAI, handles retries.

Vision support:
  Pass image content blocks in messages using Anthropic format:
    {"role": "user", "content": [
        {"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": "<b64>"}},
        {"type": "text", "text": "What is in this image?"}
    ]}

  Helper: build_image_block(path) → dict  (reads file, returns content block)
"""
from __future__ import annotations
import asyncio
import base64
import mimetypes
import os
from pathlib import Path
from typing import Any
import httpx
from ..core.config import LabConfig, ModelProfile


def build_image_block(path: str | Path) -> dict:
    """
    Read an image file and return an Anthropic vision content block.

    Supports: JPEG, PNG, GIF, WEBP.
    Raises ValueError for unsupported types or missing files.
    """
    p = Path(path)
    if not p.exists():
        raise ValueError(f"Image not found: {path}")
    mime, _ = mimetypes.guess_type(str(p))
    supported = {"image/jpeg", "image/png", "image/gif", "image/webp"}
    if mime not in supported:
        raise ValueError(f"Unsupported image type: {mime}. Supported: jpeg, png, gif, webp")
    data = base64.standard_b64encode(p.read_bytes()).decode("ascii")
    return {
        "type": "image",
        "source": {
            "type": "base64",
            "media_type": mime,
            "data": data,
        },
    }


def _normalize_messages(messages: list[dict]) -> list[dict]:
    """
    Ensure all messages have a 'content' field that is either a string or a list.
    Passes through already-structured content blocks unchanged.
    """
    out = []
    for msg in messages:
        content = msg.get("content", "")
        if isinstance(content, (str, list)):
            out.append(msg)
        else:
            out.append({**msg, "content": str(content)})
    return out


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
        """Send a completion request. Returns response text.

        Messages may contain vision content blocks (Anthropic format).
        For OpenAI-compatible providers, image blocks are silently stripped
        since vision support varies by model.
        """
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
            "messages": _normalize_messages(messages),
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
        # Strip image blocks for OpenAI-compatible providers (flatten to text)
        for msg in messages:
            content = msg.get("content", "")
            if isinstance(content, list):
                text_parts = [
                    block.get("text", "")
                    for block in content
                    if block.get("type") == "text"
                ]
                all_messages.append({**msg, "content": " ".join(text_parts)})
            else:
                all_messages.append(msg)

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
