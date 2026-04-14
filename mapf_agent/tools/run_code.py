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


def _truncate(text: str, max_len: int = 200) -> str:
    text = text.replace("\n", " ").strip()
    return text if len(text) <= max_len else text[:max_len] + "..."


def test_code(code: str, algo_type: str, reg_name: str,
              state: "AgentState") -> str:
    """Load code into registry and run a smoke test. Returns '测试通过' or error."""
    code = _extract_code(code)
    line_count = code.count("\n") + 1
    print(f"  [工具调用] test_code → 代码 ({line_count} 行)")

    try:
        if algo_type == "planner":
            default_registry.load_generated_planner(code, reg_name)
        else:
            default_registry.load_generated_scheduler(code, reg_name)
    except Exception as exc:
        result = f"代码加载失败: {exc}"
        print(f"  [工具返回] ✗ {_truncate(result)}")
        return result

    cfg = copy.deepcopy(state.get("system_config") or SystemConfig())
    cfg.sim_config.max_steps = _SMOKE_TEST_STEPS
    if state.get("map_file_path"):
        cfg.sim_config.map_file = state["map_file_path"]
    if algo_type == "planner":
        cfg.sim_config.planner_type = reg_name
    else:
        cfg.sim_config.scheduler_type = reg_name

    print(f"  [测试中] 冒烟测试 ({_SMOKE_TEST_STEPS} 步仿真)...")
    try:
        run_simulation(config=cfg, max_steps=_SMOKE_TEST_STEPS)
    except Exception as exc:
        result = f"冒烟测试失败: {exc}"
        print(f"  [工具返回] ✗ {_truncate(result)}")
        return result

    print("  [工具返回] ✓ 测试通过")
    return "测试通过"
