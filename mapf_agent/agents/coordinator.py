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
        """Phase 1: generate map from NL."""
        from mapf_agent.agents.input_parser import InputParserAgent
        from mapf_agent.agents.env_config_agent import EnvConfigAgent
        from mapf_agent.tools.validate_map import validate_map

        parser = InputParserAgent()
        parsed = parser.parse(nl_input, use_llm=self.use_llm)

        if not parsed.get("complete"):
            return {
                "ok": False,
                "error": f"Missing required: {parsed.get('missing_fields', [])}",
                "follow_up_question": parsed.get("follow_up_question", ""),
                "structured": parsed.get("map_config", {}),
            }

        env_agent = EnvConfigAgent()
        result = env_agent.generate(parsed["map_config"], use_llm=self.use_llm, max_retries=max_retries)

        if not result.get("ok"):
            return {
                "ok": False,
                "error": result.get("error", "Map generation failed"),
                "structured": parsed.get("map_config", {}),
            }

        map_json = result["map_json"]
        if output_path:
            os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
            with open(output_path, "w", encoding="utf-8") as f:
                json.dump(map_json, f, indent=2, ensure_ascii=False)

        return {
            "ok": True,
            "map_path": output_path,
            "map_json": map_json,
            "structured": parsed.get("map_config", {}),
        }

    def run_phase2(
        self,
        map_path: str,
        algorithm_nl: str,
        seed: Optional[int] = None,
        num_runs: int = 1,
    ) -> Dict[str, Any]:
        """Phase 2: select algorithm, run simulation, optimize."""
        from mapf_agent.agents.algorithm_agent import AlgorithmAgent
        from mapf_agent.agents.optimizer_agent import OptimizerAgent
        from mapf_agent.tools.run_simulation import run_simulation

        algo_agent = AlgorithmAgent()
        algo = algo_agent.select(algorithm_nl, use_llm=self.use_llm)

        run_result = run_simulation(
            map_file=map_path,
            planner_type=algo.get("planner_type"),
            scheduler_type=algo.get("scheduler_type"),
            seed=seed or agent_config.default_simulation_seed,
            num_runs=num_runs,
        )

        if not run_result.get("ok"):
            return run_result

        metrics = run_result.get("metrics", {})
        optimizer = OptimizerAgent()
        current_config = {
            "planner_type": algo.get("planner_type", "astar"),
            "scheduler_type": algo.get("scheduler_type", "ta"),
        }
        opt_result = optimizer.suggest(metrics, current_config, [], use_llm=self.use_llm)
        run_result["suggestion"] = opt_result.get("analysis", "")
        run_result["optimization_detail"] = opt_result

        return run_result

    def run_full(
        self,
        map_nl: str,
        algorithm_nl: str,
        map_output_path: Optional[str] = None,
        seed: Optional[int] = None,
        num_runs: int = 1,
    ) -> Dict[str, Any]:
        """Run phase1 then phase2."""
        p1 = self.run_phase1(map_nl, output_path=map_output_path)
        if not p1.get("ok"):
            return {"phase": 1, **p1}

        map_path = p1.get("map_path")
        if not map_path:
            import tempfile
            fd, map_path = tempfile.mkstemp(suffix=".json")
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(p1["map_json"], f, indent=2)

        p2 = self.run_phase2(map_path, algorithm_nl, seed=seed, num_runs=num_runs)
        p2["phase"] = 2
        p2["map_path"] = map_path
        return p2
