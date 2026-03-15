"""
Optimizer Agent: use LLM to analyze simulation metrics and suggest
algorithm/parameter improvements. Tracks optimization history to avoid repeats.
"""
from __future__ import annotations

import json
import os
from typing import Any, Dict, List, Optional

from mapf_agent.config import agent_config


def _load_prompt() -> str:
    path = os.path.join(agent_config.prompts_dir, "optimizer.txt")
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


class OptimizerAgent:
    """Analyze metrics and produce optimization suggestions."""

    def __init__(self):
        self._prompt = _load_prompt()

    def suggest(
        self,
        metrics: Dict[str, Any],
        current_config: Dict[str, Any],
        history: Optional[List[Dict[str, Any]]] = None,
        use_llm: bool = True,
    ) -> Dict[str, Any]:
        """
        Analyze metrics and return optimization suggestion.

        Returns dict with: analysis, should_continue, suggestion.
        """
        if use_llm:
            try:
                return self._suggest_llm(metrics, current_config, history or [])
            except Exception:
                pass
        return self._suggest_rules(metrics, current_config, history or [])

    def _suggest_llm(
        self,
        metrics: Dict[str, Any],
        current_config: Dict[str, Any],
        history: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        from mapf_agent.llm import chat_completion_json

        user_content = (
            f"Current metrics:\n```json\n{json.dumps(metrics, indent=2)}\n```\n\n"
            f"Current config:\n```json\n{json.dumps(current_config, indent=2)}\n```\n\n"
            f"Optimization history ({len(history)} previous iterations):\n"
            f"```json\n{json.dumps(history, indent=2)}\n```"
        )

        messages = [
            {"role": "system", "content": self._prompt},
            {"role": "user", "content": user_content},
        ]
        result = chat_completion_json(messages)
        result.setdefault("analysis", "")
        result.setdefault("should_continue", False)
        result.setdefault("suggestion", {"action": "satisfied", "reasoning": ""})
        return result

    def _suggest_rules(
        self,
        metrics: Dict[str, Any],
        current_config: Dict[str, Any],
        history: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """Rule-based fallback analysis."""
        lines = []
        task_success = metrics.get("Task Success Rate")
        finished = metrics.get("finished")
        sim_steps = metrics.get("sim_steps")
        current_planner = current_config.get("planner_type", "astar")

        tried_planners = {h.get("planner_type") for h in history if "planner_type" in h}

        action = "satisfied"
        new_planner = None
        new_scheduler = None
        param_changes: Dict[str, Any] = {}

        if task_success is not None and task_success < 0.5:
            lines.append(f"Task success rate is low ({task_success:.1%}).")
            if current_planner == "astar" and "cbs_fw" not in tried_planners:
                action = "change_algorithm"
                new_planner = "cbs_fw"
                lines.append("Suggesting CBS-FW for better conflict resolution.")
            elif current_planner != "dhc" and "dhc" not in tried_planners:
                action = "change_algorithm"
                new_planner = "dhc"
                lines.append("Suggesting DHC as an alternative.")
        elif task_success is not None and task_success < 0.9:
            lines.append(f"Task success rate is moderate ({task_success:.1%}).")

        if finished is False:
            lines.append("Simulation did not finish all orders.")
            if sim_steps and sim_steps >= 999:
                action = "adjust_params"
                param_changes["max_steps"] = (sim_steps or 1000) * 2
                lines.append("Suggesting increased max_steps.")

        should_continue = action != "satisfied" and len(history) < 3

        if not lines:
            lines.append("Metrics look acceptable.")

        return {
            "analysis": " ".join(lines),
            "should_continue": should_continue,
            "suggestion": {
                "action": action,
                "new_planner_type": new_planner,
                "new_scheduler_type": new_scheduler,
                "param_changes": param_changes,
                "reasoning": " ".join(lines),
            },
        }
