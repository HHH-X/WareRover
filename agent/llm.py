"""Thin LLM client wrapping OpenAI-compatible API."""
from __future__ import annotations

import json
import os
import time
from typing import Any, Dict, List, Optional

from openai import APIConnectionError, APIError, OpenAI, RateLimitError

_CLIENT: Optional[OpenAI] = None


def _client() -> OpenAI:
    global _CLIENT
    if _CLIENT is not None:
        return _CLIENT
    key = os.getenv("OPENAI_API_KEY", "").strip()
    if not key:
        raise RuntimeError("请设置环境变量 OPENAI_API_KEY")
    kwargs: Dict[str, Any] = {"api_key": key}
    base_url = os.getenv("OPENAI_BASE_URL")
    if base_url:
        kwargs["base_url"] = base_url
    _CLIENT = OpenAI(**kwargs)
    return _CLIENT


def _model() -> str:
    return os.getenv("MAPF_AGENT_MODEL", "DeepSeek-V3.2")


def chat(
    messages: List[Dict[str, str]],
    *,
    json_mode: bool = False,
    temperature: float = 0.2,
    max_tokens: int = 4096,
    retries: int = 3,
) -> str:
    kwargs: Dict[str, Any] = {
        "model": _model(),
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    if json_mode:
        kwargs["response_format"] = {"type": "json_object"}

    last_err: Optional[Exception] = None
    for attempt in range(retries):
        try:
            resp = _client().chat.completions.create(**kwargs)
            return resp.choices[0].message.content or ""
        except (RateLimitError, APIError, APIConnectionError) as exc:
            last_err = exc
            if attempt < retries - 1:
                time.sleep(2 ** attempt)
    raise RuntimeError(f"LLM 调用失败: {last_err}")


def chat_json(messages: List[Dict[str, str]], **kwargs: Any) -> Dict[str, Any]:
    raw = chat(messages, json_mode=True, **kwargs)
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        start = raw.find("{")
        end = raw.rfind("}") + 1
        if start >= 0 and end > start:
            return json.loads(raw[start:end])
        raise ValueError(f"LLM 返回非 JSON: {raw[:200]}")
