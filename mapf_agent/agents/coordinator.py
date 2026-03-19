"""
Coordinator: orchestrate the MAPF Agent workflow using LangGraph.
Supports three modes: map-only, algorithm-only, and full (both).
Handles multi-turn conversation for missing information.
"""
from __future__ import annotations

import json
import os
from typing import Any, Dict, Optional

from mapf_agent.config import agent_config


class Coordinator:
    """Run the MAPF workflow: map generation, algorithm selection, simulation, optimization."""

    def __init__(self, use_llm: bool = True):
        self.use_llm = bool(use_llm)
        self._compiled = None

    def _get_compiled_graph(self):
        if self._compiled is None:
            from mapf_agent.workflow.graph import build_graph
            self._compiled = build_graph().compile()
        return self._compiled

    def run(
        self,
        user_input: str,
        output_path: Optional[str] = None,
        map_path: Optional[str] = None,
        mode_hint: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Run the full workflow from user input.
        Returns the final state dict with results.

        If the workflow pauses for human input (pending_question),
        the caller should call resume() with the user's answer.
        """
        graph = self._get_compiled_graph()
        initial_state: Dict[str, Any] = {
            "user_input": user_input,
            "output_path": output_path or "",
            "map_path": map_path or "",
            "use_llm": self.use_llm,
            "human_response": "",
            "pending_question": "",
            "env_extract_attempts": 0,
            "env_validation_attempts": 0,
            "env_validation_max_attempts": 5,
            "iteration": 0,
            "optimization_history": [],
        }
        if mode_hint:
            initial_state["route_hint"] = mode_hint

        # if map_path and os.path.isfile(map_path):
        #     with open(map_path, "r", encoding="utf-8") as f:
        #         initial_state["map_json"] = json.load(f)

        result = graph.invoke(initial_state)
        self._last_state = dict(result)
        return result

    def resume(self, human_response: str) -> Dict[str, Any]:
        """
        Resume workflow after human provides missing information.
        Call this when run() returned a state with non-empty pending_question.
        """
        if not hasattr(self, "_last_state"):
            raise RuntimeError("No workflow to resume. Call run() first.")

        state = dict(self._last_state)
        state["human_response"] = human_response
        state["pending_question"] = ""

        graph = self._get_compiled_graph()
        result = graph.invoke(state)
        self._last_state = dict(result)
        return result

    # ---- Convenience methods for backward compatibility ----

    def run_phase1(self, nl_input: str, output_path: Optional[str] = None, max_retries: int = 3) -> Dict[str, Any]:
        """
        Phase 1 wrapper: generate map from NL by driving the LangGraph workflow
        in \"map_only\" mode. Multi-turn clarification is not handled here;
        callers should switch to interactive mode for that.
        """
        state = self.run(nl_input, output_path=output_path, mode_hint="map_only")
        ok = bool(state.get("map_json")) and not state.get("error")
        if not ok:
            return {
                "ok": False,
                "error": state.get("error", "Map generation failed"),
                "follow_up_question": state.get("pending_question", ""),
                "structured": state.get("map_config", {}),
            }

        return {
            "ok": True,
            "map_path": state.get("map_path"),
            "map_json": state.get("map_json"),
            "structured": state.get("map_config", {}),
        }

    def run_phase2(
        self,
        map_path: str,
        algorithm_nl: str,
        seed: Optional[int] = None,
        num_runs: int = 1,
    ) -> Dict[str, Any]:
        """
        Phase 2 wrapper: select algorithm, run simulation, and optionally
        optimize using the LangGraph workflow in \"algorithm_only\" mode.
        """
        # Seed/num_runs are currently controlled inside the workflow/simulation
        # tool; we keep the signature for backward compatibility.
        state = self.run(
            algorithm_nl,
            output_path=None,
            map_path=map_path,
            mode_hint="algorithm_only",
        )
        if state.get("error"):
            return {"ok": False, "error": state["error"], "metrics": {}}

        return {
            "ok": True,
            "metrics": state.get("metrics", {}),
            "optimization_history": state.get("optimization_history", []),
            "algo_config": state.get("algo_config", {}),
        }

    def run_full(
        self,
        map_nl: str,
        algorithm_nl: str,
        map_output_path: Optional[str] = None,
        seed: Optional[int] = None,
        num_runs: int = 1,
    ) -> Dict[str, Any]:
        """
        Run both phases in one shot by driving the workflow in \"both\" mode.
        """
        user_input = f"{map_nl}\n\n{algorithm_nl}"
        state = self.run(
            user_input,
            output_path=map_output_path,
            map_path=None,
            mode_hint="both",
        )
        if state.get("error"):
            return {"ok": False, "error": state["error"], "phase": 0}

        return {
            "ok": True,
            "map_path": state.get("map_path"),
            "map_json": state.get("map_json"),
            "metrics": state.get("metrics", {}),
            "optimization_history": state.get("optimization_history", []),
            "algo_config": state.get("algo_config", {}),
            "phase": 2,
        }
