"""Thin LLM client wrapping OpenAI-compatible API."""
from __future__ import annotations

import json
import time
from typing import Any, Dict, List, Optional

from openai import APIConnectionError, APIError, OpenAI, RateLimitError

from mapf_agent.llm_config import build_openai_client_kwargs, load_llm_settings

_CLIENT: Optional[OpenAI] = None
_CLIENT_SIGNATURE: Optional[tuple[str, str]] = None


def _client() -> OpenAI:
    global _CLIENT, _CLIENT_SIGNATURE
    settings = load_llm_settings()
    signature = (settings.api_key, settings.base_url)
    if _CLIENT is not None and _CLIENT_SIGNATURE == signature:
        return _CLIENT
    _CLIENT = OpenAI(**build_openai_client_kwargs(settings))
    _CLIENT_SIGNATURE = signature
    return _CLIENT


def _model() -> str:
    return load_llm_settings().model


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


def chat_completion(
    messages: List[Dict[str, Any]],
    *,
    tools: Any = None,
    temperature: float = 0.2,
    max_tokens: int = 4096,
    retries: int = 3,
):
    """Call LLM and return the raw ChatCompletionMessage (supports tool calling)."""
    kwargs: Dict[str, Any] = {
        "model": _model(),
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    if tools:
        kwargs["tools"] = tools

    last_err: Optional[Exception] = None
    for attempt in range(retries):
        try:
            resp = _client().chat.completions.create(**kwargs)
            return resp.choices[0].message
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
