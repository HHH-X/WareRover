"""LLM service layer: unified OpenAI-compatible API wrapper with retry and JSON mode."""
from __future__ import annotations

import json
import time
import logging
from typing import Any, Dict, List, Optional

from openai import OpenAI, APIError, APIConnectionError, RateLimitError

from mapf_agent.config import agent_config

logger = logging.getLogger(__name__)

_client: Optional[OpenAI] = None


def _get_client() -> OpenAI:
    global _client
    if _client is not None:
        return _client
    api_key = agent_config.get_api_key()
    if not api_key:
        raise RuntimeError(
            "LLM API key not configured. Create mapf_agent/api_key and put your API key in it (one line)."
        )
    kwargs: Dict[str, Any] = {"api_key": api_key}
    if agent_config.llm_base_url:
        kwargs["base_url"] = agent_config.llm_base_url
    _client = OpenAI(**kwargs)
    return _client


def reset_client():
    """Force re-creation of the OpenAI client (useful after config change)."""
    global _client
    _client = None


def chat_completion(
    messages: List[Dict[str, str]],
    *,
    json_mode: bool = False,
    temperature: Optional[float] = None,
    max_tokens: Optional[int] = None,
    model: Optional[str] = None,
    max_retries: int = 3,
) -> str:
    """
    Send a chat completion request and return the assistant's response text.

    Args:
        messages: List of {"role": ..., "content": ...} dicts.
        json_mode: If True, set response_format to JSON object.
        temperature: Override default temperature.
        max_tokens: Override default max_tokens.
        model: Override default model.
        max_retries: Max retry attempts on transient errors.

    Returns:
        The assistant message content string.
    """
    client = _get_client()
    kwargs: Dict[str, Any] = {
        "model": model or agent_config.llm_model,
        "messages": messages,
        "temperature": temperature if temperature is not None else agent_config.llm_temperature,
        "max_tokens": max_tokens or agent_config.llm_max_tokens,
    }
    if json_mode:
        kwargs["response_format"] = {"type": "json_object"}

    last_err = None
    for attempt in range(max_retries):
        try:
            response = client.chat.completions.create(**kwargs)
            return response.choices[0].message.content or ""
        except RateLimitError as e:
            last_err = e
            wait = 2 ** attempt
            logger.warning("Rate limited, retrying in %ds (attempt %d/%d)", wait, attempt + 1, max_retries)
            time.sleep(wait)
        except (APIError, APIConnectionError) as e:
            last_err = e
            wait = 2 ** attempt
            logger.warning("API error: %s, retrying in %ds (attempt %d/%d)", e, wait, attempt + 1, max_retries)
            time.sleep(wait)

    raise RuntimeError(f"LLM request failed after {max_retries} attempts: {last_err}")


def chat_completion_json(
    messages: List[Dict[str, str]],
    **kwargs,
) -> Dict[str, Any]:
    """Chat completion that parses the response as JSON dict."""
    raw = chat_completion(messages, json_mode=True, **kwargs)
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        start = raw.find("{")
        end = raw.rfind("}") + 1
        if start >= 0 and end > start:
            return json.loads(raw[start:end])
        raise ValueError(f"LLM response is not valid JSON: {raw[:200]}")
