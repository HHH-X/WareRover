"""
Coordinator: orchestrate the MAPF Agent workflow using LangGraph.
Supports three modes: map-only, algorithm-only, and full (both).
Handles multi-turn conversation for missing information.
"""
from __future__ import annotations

import uuid
from typing import Any, Dict, Optional

from langgraph.checkpoint.memory import MemorySaver
from langgraph.types import Command


class Coordinator:
    """Run the MAPF workflow: map generation, algorithm selection, simulation, optimization."""

    def __init__(self, use_llm: bool = True):
        self.use_llm = bool(use_llm)
        self._compiled = None
        self._checkpointer = MemorySaver()
        # A stable ID for the whole conversation; enables interrupt/resume.
        self._thread_id = str(uuid.uuid4())

    def _get_compiled_graph(self):
        if self._compiled is None:
            from mapf_agent.workflow.graph import build_graph
            self._compiled = build_graph().compile(checkpointer=self._checkpointer)
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
            "conversation_history": [],
            "map_intent_flag": False,
            "map_intent_content": "",
            "sim_intent_flag": False,
            "sim_intent_content": "",
            "algorithm_text": "",
            "algo_generate_flag": False,
            "algo_generate_content": "",
            "algo_optimize_flag": False,
            "algo_optimize_content": "",
            "map_config": {},
            "map_valid": False,
            "map_json": {},
            "env_config_path": "",
            "sim_config_delta": {},
            "pending_question": "",
            "pending_type": "",
            "need_user_input": False,
            "map_gen_attempts": 0,
            "map_gen_max_attempts": 3,
            "metrics": {},
            "metrics_ran": False,
            "optimization_history": [],
            "iteration": 0,
            "algo_config": {},
            "algo_ready": False,
            "algo_attempts": 0,
            "algo_history": [],
            "terminate": False,
            "max_iterations": 3,
            "error": "",
        }

        config = {"configurable": {"thread_id": self._thread_id}}
        result = graph.invoke(initial_state, config=config)
        return self._normalize_result(result)

    def resume(self, human_response: str) -> Dict[str, Any]:
        """
        Resume workflow after human provides missing information.
        Call this when run() returned a state with non-empty pending_question.
        """
        graph = self._get_compiled_graph()
        config = {"configurable": {"thread_id": self._thread_id}}
        result = graph.invoke(Command(resume=human_response), config=config)
        return self._normalize_result(result)

    def _normalize_result(self, result: Dict[str, Any]) -> Dict[str, Any]:
        """
        Normalize LangGraph interrupt payload into the fields expected by existing CLI:
        - `pending_question`
        - `pending_type`
        - `metrics` (for result decisions)
        """
        # `__interrupt__` is added when the graph hits `langgraph.types.interrupt()`.
        interrupts = result.get("__interrupt__")
        if interrupts:
            # Usually it's a list/tuple with one Interrupt.
            intr0 = interrupts[0] if isinstance(interrupts, (list, tuple)) else interrupts
            value = getattr(intr0, "value", None) if not isinstance(intr0, dict) else intr0
            if isinstance(intr0, dict):
                value = intr0

            if isinstance(value, dict):
                question = value.get("question") or value.get("message") or ""
                pending_type = value.get("pending_type") or value.get("type") or ""
                if value.get("metrics") is not None:
                    # Make sure CLI sees metrics even if checkpoint state differs.
                    result.setdefault("metrics", value.get("metrics") or {})
                    result.setdefault("metrics_ran", True)
            else:
                question = str(value or "")
                pending_type = "user_question"

            if question:
                result["pending_question"] = question
            if pending_type:
                result["pending_type"] = pending_type
            result["need_user_input"] = True

        return dict(result)

    # ---- Convenience methods for backward compatibility ----

    def run_phase1(self, nl_input: str, output_path: Optional[str] = None, max_retries: int = 3) -> Dict[str, Any]:
        """
        Phase 1 wrapper: generate map from NL by driving the LangGraph workflow
        in \"map_only\" mode. Multi-turn clarification is not handled here;
        callers should switch to interactive mode for that.
        """
        state = self.run(nl_input, output_path=output_path, mode_hint="env_only")
        # Non-interactive wrapper: auto-close the "result decision" interrupt.
        if state.get("pending_question") and state.get("pending_type") == "result_decision":
            state = self.resume("结束")
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
        state = self.run(algorithm_nl, output_path=None, map_path=map_path, mode_hint="algorithm_only")
        if state.get("pending_question") and state.get("pending_type") == "result_decision":
            state = self.resume("结束")
        if state.get("pending_question"):
            return {
                "ok": False,
                "error": state.get("error") or "Workflow paused for additional input",
                "follow_up_question": state.get("pending_question", ""),
                "pending_type": state.get("pending_type", ""),
                "metrics": {},
            }
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
        state = self.run(user_input, output_path=map_output_path, map_path=None, mode_hint="both")
        if state.get("pending_question") and state.get("pending_type") == "result_decision":
            state = self.resume("结束")
        if state.get("pending_question"):
            return {
                "ok": False,
                "error": state.get("error") or "Workflow paused for additional input",
                "follow_up_question": state.get("pending_question", ""),
                "pending_type": state.get("pending_type", ""),
                "phase": 0,
            }
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
