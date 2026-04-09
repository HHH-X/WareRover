"""Centralised API-key loader.

Reads the key from ``<project_root>/api_key.txt`` first; falls back to the
``OPENAI_API_KEY`` environment variable when the file is absent or empty.
"""
from __future__ import annotations

import os
from pathlib import Path

_KEY_FILE = Path(__file__).resolve().parent.parent / "api_key.txt"


def load_api_key() -> str:
    if _KEY_FILE.is_file():
        key = _KEY_FILE.read_text(encoding="utf-8").strip()
        if key:
            return key
    key = os.getenv("OPENAI_API_KEY", "").strip()
    if not key:
        raise RuntimeError(
            "未找到 API Key：请在项目根目录创建 api_key.txt 或设置环境变量 OPENAI_API_KEY"
        )
    return key
