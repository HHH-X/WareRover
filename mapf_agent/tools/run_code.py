"""Code testing tool: load generated code and run a smoke test."""
from __future__ import annotations

import copy
from typing import TYPE_CHECKING

from config.settings import SystemConfig
from mapf_agent.run_sim import run_simulation
from utils.algorithm_registry import default_registry

if TYPE_CHECKING:
    from mapf_agent.state import AgentState

_SMOKE_TEST_STEPS = 50


def _extract_code(raw: str) -> str:
    """Strip markdown code fences if present."""
    if "```python" in raw:
        raw = raw.split("```python", 1)[1]
        raw = raw.split("```", 1)[0]
    elif "```" in raw:
        raw = raw.split("```", 1)[1]
        raw = raw.split("```", 1)[0]
    return raw.strip()


def test_code(code: str, algo_type: str, reg_name: str,
              state: "AgentState") -> str:
    """Load code into registry and run a smoke test. Returns '测试通过' or error."""
    code = _extract_code(code)

    try:
        if algo_type == "planner":
            default_registry.load_generated_planner(code, reg_name)
        else:
            default_registry.load_generated_scheduler(code, reg_name)
    except Exception as exc:
        return f"代码加载失败: {exc}"

    cfg = copy.deepcopy(state.get("system_config") or SystemConfig())
    cfg.sim_config.max_steps = _SMOKE_TEST_STEPS
    if state.get("map_file_path"):
        cfg.sim_config.map_file = state["map_file_path"]
    if algo_type == "planner":
        cfg.sim_config.planner_type = reg_name
    else:
        cfg.sim_config.scheduler_type = reg_name

    try:
        run_simulation(config=cfg, max_steps=_SMOKE_TEST_STEPS)
    except Exception as exc:
        return f"冒烟测试失败: {exc}"

    return "测试通过"
