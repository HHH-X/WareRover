"""
Algorithm config Agent: use LLM to interpret algorithm requests and select
planner/scheduler, with map-aware recommendations. Falls back to keyword matching.
"""
from __future__ import annotations

import json
import os
import re
from typing import Any, Dict, Optional

from mapf_agent.config import agent_config


def _load_prompt() -> str:
    path = os.path.join(agent_config.prompts_dir, "algorithm.txt")
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


KEYWORD_MAP = {
    "astar": ("astar", "ta"),
    "a*": ("astar", "ta"),
    "a-star": ("astar", "ta"),
    "cbs": ("cbs_fw", "ta"),
    "cbs_fw": ("cbs_fw", "ta"),
    "dhc": ("dhc", "ta"),
    "random": ("astar", "random"),
}


class AlgorithmAgent:
    """Select or configure MAPF algorithm from natural language."""

    def __init__(self):
        self._prompt = _load_prompt()

    def select(
        self,
        nl_text: str,
        map_info: Optional[Dict[str, Any]] = None,
        use_llm: bool = True,
    ) -> Dict[str, Any]:
        """
        Map NL to algorithm config.

        Returns dict with: planner_type, scheduler_type, optimize, optimize_target,
        max_iterations, reasoning.
        """
        if use_llm:
            try:
                return self._select_llm(nl_text, map_info)
            except Exception:
                pass
        return self._select_keyword(nl_text)

    def _select_llm(self, nl_text: str, map_info: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        from mapf_agent.llm import chat_completion_json

        user_content = f"User request: {nl_text}"
        if map_info:
            user_content += f"\n\nMap info:\n```json\n{json.dumps(map_info, ensure_ascii=False)}\n```"

        messages = [
            {"role": "system", "content": self._prompt},
            {"role": "user", "content": user_content},
        ]
        result = chat_completion_json(messages)
        result.setdefault("planner_type", "astar")
        result.setdefault("scheduler_type", "ta")
        result.setdefault("optimize", False)
        result.setdefault("optimize_target", "")
        result.setdefault("max_iterations", 3)
        result.setdefault("reasoning", "")
        return result

    def _select_keyword(self, nl_text: str) -> Dict[str, Any]:
        text = (nl_text or "").strip().lower()
        planner, scheduler = "astar", "ta"
        for keyword, (p, s) in KEYWORD_MAP.items():
            if keyword in text:
                planner, scheduler = p, s
                break

        optimize = any(k in text for k in ("优化", "optimize", "迭代", "iterate"))
        max_iter = 3
        m = re.search(r"(\d+)\s*(?:轮|rounds?|iterations?|次)", text)
        if m:
            max_iter = max(1, int(m.group(1)))

        return {
            "planner_type": planner,
            "scheduler_type": scheduler,
            "optimize": optimize,
            "optimize_target": "planner" if optimize else "",
            "max_iterations": max_iter,
            "reasoning": f"Keyword matched: {planner}/{scheduler}",
        }
