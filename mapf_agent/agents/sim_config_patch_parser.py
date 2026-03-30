"""
SimConfig delta parsing agent.

Convert natural language "modify simulation config" into a validated subset dict
that can be applied on top of config.settings.SimConfig/FaultConfig.
"""

from __future__ import annotations

import os
import re
from typing import Any, Dict

from mapf_agent.config import agent_config
from mapf_agent.llm import chat_completion_json


def _load_prompt() -> str:
    path = os.path.join(agent_config.prompts_dir, "sim_config_patch_parser.txt")
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


class SimConfigPatchParserAgent:
    def __init__(self) -> None:
        self._prompt = _load_prompt()

    def parse(self, nl_text: str, *, use_llm: bool = True) -> Dict[str, Any]:
        text = (nl_text or "").strip()
        if not text:
            return {}

        result = chat_completion_json(
            [
                {"role": "system", "content": self._prompt},
                {"role": "user", "content": text},
            ]
        )
        return result if isinstance(result, dict) else {}

