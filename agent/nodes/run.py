"""Run simulation node."""
from __future__ import annotations

import copy
from typing import Dict

from config.settings import SystemConfig
from agent.run_sim import run_simulation
from agent.state import AgentState
from utils.algorithm_registry import default_registry


def run_node(state: AgentState) -> Dict:
    config: SystemConfig = copy.deepcopy(state.get("system_config") or SystemConfig())

    # If a map was generated earlier, ensure it's set
    if state.get("map_file_path"):
        config.sim_config.map_file = state["map_file_path"]

    # Register any generated algorithms before running
    gen = state.get("generated_code") or {}
    for kind, path in gen.items():
        try:
            code = open(path, encoding="utf-8").read()
            if kind == "planner":
                default_registry.load_generated_planner(code, "agent_generated_planner")
                config.sim_config.planner_type = "agent_generated_planner"
            elif kind == "scheduler":
                default_registry.load_generated_scheduler(code, "agent_generated_scheduler")
                config.sim_config.scheduler_type = "agent_generated_scheduler"
        except Exception as exc:
            return {"error": f"注册生成的{kind}算法失败: {exc}"}

    try:
        metrics = run_simulation(config=config)
    except Exception as exc:
        return {"error": f"仿真运行失败: {exc}"}

    return {"run_metrics": metrics, "error": ""}
