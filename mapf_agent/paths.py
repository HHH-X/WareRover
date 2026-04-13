"""Centralized output path management for mapf_agent."""
from __future__ import annotations

from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
OUTPUT_ROOT = PROJECT_ROOT / "output"


def output_dir(category: str) -> Path:
    """Return (and create) a subdirectory under the unified output root."""
    d = OUTPUT_ROOT / category
    d.mkdir(parents=True, exist_ok=True)
    return d
