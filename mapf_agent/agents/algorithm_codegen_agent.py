"""
Algorithm codegen agent (interface placeholder).

The current repository does NOT support automatic code generation of new
planner/scheduler implementations. This agent defines a stable interface
for future extension while providing a useful fallback today:
map algorithm NL to existing planner/scheduler via AlgorithmAgent.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional


class AlgorithmCodegenAgent:
    """Placeholder interface for generating new MAPF algorithms."""

    def propose_code_changes(
        self, algorithm_text: str, map_info: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        # Future: analyze existing codebase and propose diffs.
        return {
            "ok": False,
            "reason": "当前代码库尚不支持 planner/scheduler 的代码生成与落地。",
            "algorithm_text": algorithm_text,
        }

    def apply_changes(self, proposed: Dict[str, Any]) -> Dict[str, Any]:
        # Future: apply patches and register modules.
        raise NotImplementedError("apply_changes is not implemented yet.")

    def validate_via_run_simulation(self, *args: Any, **kwargs: Any) -> Dict[str, Any]:
        # Future: run simulation as validation.
        raise NotImplementedError("validate_via_run_simulation is not implemented yet.")

    # ---- Practical fallback today ----

    def get_planner_candidates(self, base_planner: Optional[str]) -> List[str]:
        """
        Provide a small deterministic planner candidate list to try when
        the initial guess fails.
        """
        candidates = [base_planner, "astar", "cbs_fw", "dhc"]
        out: List[str] = []
        for c in candidates:
            if c and c not in out:
                out.append(c)
        return out

