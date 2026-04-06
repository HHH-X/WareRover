from __future__ import annotations

import json
import os
import time
from typing import Any, Dict, List, Optional

from openai import APIConnectionError, APIError, OpenAI, RateLimitError

_CLIENT: Optional[OpenAI] = None


def _api_key() -> str:
    # Research-oriented: env first, fallback to old local key file.
    key = os.getenv("OPENAI_API_KEY") or os.getenv("MAPF_AGENT_API_KEY")
    if key:
        return key.strip()
    legacy = "D:/Project/WareRover-private/mapf_agent/api_key"
    if os.path.isfile(legacy):
        with open(legacy, "r", encoding="utf-8") as f:
            return (f.readline() or "").strip()
    return ""


def _base_url() -> Optional[str]:
    return os.getenv("OPENAI_BASE_URL") or os.getenv("MAPF_AGENT_BASE_URL") or "https://api.modelarts-maas.com/v1"


def _model() -> str:
    return os.getenv("MAPF_AGENT_MODEL", "DeepSeek-V3.2")


def _client() -> OpenAI:
    global _CLIENT
    if _CLIENT is not None:
        return _CLIENT
    key = _api_key()
    if not key:
        raise RuntimeError("未找到 LLM API key。请设置 OPENAI_API_KEY 或 MAPF_AGENT_API_KEY。")
    kwargs: Dict[str, Any] = {"api_key": key}
    base_url = _base_url()
    if base_url:
        kwargs["base_url"] = base_url
    _CLIENT = OpenAI(**kwargs)
    return _CLIENT


def chat_completion(
    messages: List[Dict[str, str]],
    *,
    json_mode: bool = False,
    temperature: float = 0.2,
    max_tokens: int = 4096,
    model: Optional[str] = None,
    retries: int = 3,
) -> str:
    kwargs: Dict[str, Any] = {
        "model": model or _model(),
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    if json_mode:
        kwargs["response_format"] = {"type": "json_object"}

    err: Optional[Exception] = None
    for attempt in range(retries):
        try:
            resp = _client().chat.completions.create(**kwargs)
            return resp.choices[0].message.content or ""
        except (RateLimitError, APIError, APIConnectionError) as e:
            err = e
            if attempt < retries - 1:
                time.sleep(2 ** attempt)
    raise RuntimeError(f"LLM 调用失败: {err}")


def chat_completion_json(messages: List[Dict[str, str]], **kwargs: Any) -> Dict[str, Any]:
    raw = chat_completion(messages, json_mode=True, **kwargs)
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        start = raw.find("{")
        end = raw.rfind("}") + 1
        if start >= 0 and end > start:
            return json.loads(raw[start:end])
        raise ValueError(f"LLM 返回非 JSON: {raw[:200]}")

