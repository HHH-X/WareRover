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
        self.use_llm = use_llm
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
        initial_state = {
            "user_input": user_input,
            "use_llm": self.use_llm,
            "output_path": output_path or "",
            "map_path": map_path or "",
            "map_gen_attempts": 0,
            "iteration": 0,
            "optimization_history": [],
        }
        if mode_hint:
            initial_state["route_hint"] = mode_hint

        if map_path and os.path.isfile(map_path):
            with open(map_path, "r", encoding="utf-8") as f:
                initial_state["map_json"] = json.load(f)

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

        from mapf_agent.workflow.graph import parse_map_input, generate_map, apply_sim_config
        from mapf_agent.workflow.graph import check_parse_complete, check_map_gen, after_sim_config

        parse_result = parse_map_input(state)
        state.update(parse_result)

        if state.get("pending_question"):
            self._last_state = state
            return state

        gen_result = generate_map(state)
        state.update(gen_result)

        if not state.get("map_json"):
            self._last_state = state
            return state

        apply_sim_config(state)

        route = state.get("route", "map")
        if route == "both" and state.get("algorithm_text"):
            from mapf_agent.workflow.graph import select_algorithm, run_simulation_node, analyze_and_optimize
            algo_result = select_algorithm(state)
            state.update(algo_result)

            sim_result = run_simulation_node(state)
            state.update(sim_result)

            if state.get("algo_config", {}).get("optimize"):
                max_iter = state.get("max_iterations", 3)
                for _ in range(max_iter):
                    opt_result = analyze_and_optimize(state)
                    state.update(opt_result)
                    last_hist = (state.get("optimization_history") or [{}])[-1]
                    suggestion = last_hist.get("suggestion", {})
                    if suggestion.get("action") == "satisfied" or state.get("iteration", 0) >= max_iter:
                        break
                    sim_result = run_simulation_node(state)
                    state.update(sim_result)

        self._last_state = state
        return state

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
