from __future__ import annotations

from pathlib import Path

from config.settings import SystemConfig
from mapf_agent_v2.session.state import new_initial_state
from mapf_agent_v2.tools.codegen_tool import generate_algorithm_code
from mapf_agent_v2.tools.config_tool import apply_patch_to_system_config, validate_patch
from mapf_agent_v2.tools.map_tool import fill_defaults, generate_map_json, missing_required
from mapf_agent_v2.tools.optimize_tool import run_stage2_optimization
from mapf_agent_v2.workflow.graph import build_graph
from utils.algorithm_registry import PlannerRegistry


def test_intent_order_run_only(monkeypatch) -> None:
    from mapf_agent_v2.workflow.nodes import intent_node as intent_node_module

    monkeypatch.setattr(intent_node_module, "parse_intents", lambda _: [{"type": "run", "content": "run"}])
    graph = build_graph()
    state = new_initial_state()
    state["user_input"] = "运行仿真"
    out = graph.invoke(state, config={"configurable": {"thread_id": "t-order"}})
    assert "conversation_history" in out
    assert "metrics" in out


def test_map_spec_completion_defaults() -> None:
    spec = {"width": 20, "height": 15, "agv_count": 8}
    completed = fill_defaults(spec)
    assert missing_required(completed) == []
    map_json = generate_map_json(completed)
    assert map_json["map"]["width"] == 20
    assert len(map_json["agvs"]) == 8


def test_config_patch_apply() -> None:
    cfg = SystemConfig()
    patch = {"updates": [{"key": "sim_config.max_steps", "value": 888}]}
    assert validate_patch(patch) == []
    assert apply_patch_to_system_config(cfg, patch) == []
    assert cfg.sim_config.max_steps == 888


def test_langgraph_resume(monkeypatch) -> None:
    from langgraph.types import Command
    from mapf_agent_v2.workflow.nodes import intent_node as intent_node_module
    from mapf_agent_v2.workflow.nodes import map_node as map_node_module

    monkeypatch.setattr(intent_node_module, "parse_intents", lambda _: [{"type": "map", "content": "生成地图"}])

    def fake_parse(text: str):
        if "width" in text:
            return {"width": 20, "height": 15, "agv_count": 5}
        return {}

    monkeypatch.setattr(map_node_module, "parse_map_spec", fake_parse)
    graph = build_graph()
    state = new_initial_state()
    state["user_input"] = "生成地图"
    config = {"configurable": {"thread_id": "resume-test"}}
    out = graph.invoke(state, config=config)
    assert "__interrupt__" in out
    resumed = graph.invoke(Command(resume="width=20,height=15,agv=5"), config=config)
    assert "map_file_path" in resumed
    assert str(resumed["map_file_path"]).endswith(".json")


def test_codegen_registry_integration(monkeypatch) -> None:
    from mapf_agent_v2.tools import codegen_tool as codegen_tool_module

    fake_code = """
from typing import Dict, List, Tuple
from planner.base_planner import BasePlanner
from scheduler.base_scheduler import BaseScheduler

class DemoPlanner(BasePlanner):
    def plan(self, targets: Dict[int, Tuple[Tuple[int, int], Tuple[int, int]]], scheduler: BaseScheduler) -> Dict[int, List[Tuple[int, int]]]:
        return {agv_id: [] for agv_id in targets}
"""
    monkeypatch.setattr(codegen_tool_module, "chat_completion", lambda *args, **kwargs: fake_code)
    name, path = generate_algorithm_code("planner", "demo_planner", "生成一个简单 planner")
    assert PlannerRegistry.has(name)
    assert Path(path).is_file()


def test_optimize_stage2_smoke(monkeypatch) -> None:
    from mapf_agent_v2.optimization.stage2 import Stage2EvolutionResult
    from mapf_agent_v2.tools import optimize_tool as optimize_tool_module

    monkeypatch.setattr(
        optimize_tool_module,
        "run_stage2_evolution",
        lambda req: Stage2EvolutionResult(
            run_dir="tmp/run",
            output_dir="tmp/out",
            initial_program_path="tmp/run/initial_program.py",
            evaluator_path="tmp/run/evaluator.py",
            config_path="tmp/run/config.yaml",
            best_score=0.9,
            best_metrics={"combined_score": 0.9},
            best_code="# code",
        ),
    )
    out = run_stage2_optimization(target="planner", planner_source="planner/astar_planner.py", iterations=1)
    assert out["ok"] is True
    assert out["best_score"] == 0.9

