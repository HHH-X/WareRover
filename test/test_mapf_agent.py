"""
Tests for mapf_agent: agents, tools, and coordinator.
Run from project root: python -m pytest test/test_mapf_agent.py -v

All tests use use_llm=False (regex/rule fallback) so they work without an API key.
"""
import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from mapf_agent.tools.validate_map import validate_map, validate_schema, validate_semantic
from mapf_agent.agents.map_config_parser import InputParserAgent
from mapf_agent.agents.map_builder import MapBuilder
from mapf_agent.agents.algorithm_agent import AlgorithmAgent
from mapf_agent.agents.optimizer_agent import OptimizerAgent
from mapf_agent.agents.coordinator import Coordinator


# =========================================================================
# validate_map / validate_schema / validate_semantic
# =========================================================================

def test_validate_map_with_file_path():
    template = os.path.join(os.path.dirname(__file__), "..", "config", "maps", "template_map.json")
    assert os.path.isfile(template), f"Template not found: {template}"
    result = validate_map(template, trial_steps=0)
    assert result["ok"] is True


def test_validate_map_with_dict():
    minimal = {
        "map": {"width": 5, "height": 5},
        "boxes": [],
        "receivers": [{"receiver_id": 0, "position": [0, 0], "size": 1}],
        "wait_zones": [{"wait_zone_id": 0, "position": [1, 1], "size": 1}],
        "agvs": [{"agv_id": 0, "size": 1}],
        "obstacles": [],
    }
    result = validate_map(minimal, trial_steps=0)
    assert result["ok"] is True


def test_validate_map_invalid_json_string():
    result = validate_map("not json at all", trial_steps=0)
    assert result["ok"] is False
    assert "error" in result


def test_validate_map_bad_type():
    result = validate_map(12345, trial_steps=0)
    assert result["ok"] is False


def test_validate_schema_missing_agvs():
    bad = {"map": {"width": 5, "height": 5}, "boxes": [], "receivers": [], "wait_zones": []}
    result = validate_schema(bad)
    assert result.get("ok") is False or "warning" in result


def test_validate_schema_valid_minimal():
    valid = {
        "map": {"width": 5, "height": 5},
        "boxes": [],
        "receivers": [{"receiver_id": 0, "position": [0, 0], "size": 1}],
        "wait_zones": [{"wait_zone_id": 0, "position": [1, 1], "size": 1}],
        "agvs": [{"agv_id": 0, "size": 1}],
        "obstacles": [],
    }
    result = validate_schema(valid)
    assert result.get("ok") is True or "warning" in result


def test_validate_schema_bad_position_type():
    bad = {
        "map": {"width": 5, "height": 5},
        "boxes": [{"box_id": 0, "position": ["a", "b"], "goods_ids": [0], "size": 1}],
        "receivers": [{"receiver_id": 0, "position": [0, 0], "size": 1}],
        "wait_zones": [{"wait_zone_id": 0, "position": [1, 1], "size": 1}],
        "agvs": [{"agv_id": 0, "size": 1}],
        "obstacles": [],
    }
    result = validate_schema(bad)
    assert result.get("ok") is False or "warning" in result


def test_validate_semantic_size_mismatch():
    data = {
        "map": {"width": 10, "height": 10},
        "boxes": [],
        "receivers": [{"receiver_id": 0, "position": [0, 0], "size": 1}],
        "wait_zones": [{"wait_zone_id": 0, "position": [1, 1], "size": 2}],
        "agvs": [{"agv_id": 0, "size": 1}],
        "obstacles": [],
    }
    result = validate_semantic(data)
    assert result["ok"] is False
    assert "size" in result["error"]


def test_validate_semantic_overlap():
    data = {
        "map": {"width": 10, "height": 10},
        "boxes": [{"box_id": 0, "position": [5, 5], "goods_ids": [0], "size": 1}],
        "receivers": [{"receiver_id": 0, "position": [5, 5], "size": 1}],
        "wait_zones": [{"wait_zone_id": 0, "position": [1, 1], "size": 1}],
        "agvs": [{"agv_id": 0, "size": 1}],
        "obstacles": [],
    }
    result = validate_semantic(data)
    assert result["ok"] is False
    assert "overlap" in result["error"].lower()


def test_validate_semantic_out_of_bounds():
    data = {
        "map": {"width": 5, "height": 5},
        "boxes": [],
        "receivers": [{"receiver_id": 0, "position": [0, 0], "size": 1}],
        "wait_zones": [{"wait_zone_id": 0, "position": [10, 10], "size": 1}],
        "agvs": [{"agv_id": 0, "size": 1}],
        "obstacles": [],
    }
    result = validate_semantic(data)
    assert result["ok"] is False
    assert "out of bounds" in result["error"]


def test_validate_semantic_wz_agv_id_mismatch():
    data = {
        "map": {"width": 10, "height": 10},
        "boxes": [],
        "receivers": [{"receiver_id": 0, "position": [0, 0], "size": 1}],
        "wait_zones": [{"wait_zone_id": 5, "position": [1, 1], "size": 1}],
        "agvs": [{"agv_id": 0, "size": 1}],
        "obstacles": [],
    }
    result = validate_semantic(data)
    assert result["ok"] is False
    assert "match" in result["error"].lower()


def test_validate_semantic_fewer_wz_than_agvs():
    data = {
        "map": {"width": 10, "height": 10},
        "boxes": [],
        "receivers": [{"receiver_id": 0, "position": [0, 0], "size": 1}],
        "wait_zones": [{"wait_zone_id": 0, "position": [1, 1], "size": 1}],
        "agvs": [
            {"agv_id": 0, "size": 1},
            {"agv_id": 1, "size": 1},
        ],
        "obstacles": [],
    }
    result = validate_semantic(data)
    assert result["ok"] is False


def test_validate_semantic_ok():
    data = {
        "map": {"width": 10, "height": 10},
        "boxes": [{"box_id": 0, "position": [5, 5], "goods_ids": [0], "size": 1}],
        "receivers": [{"receiver_id": 0, "position": [0, 0], "size": 1}],
        "wait_zones": [
            {"wait_zone_id": 0, "position": [1, 1], "size": 1},
            {"wait_zone_id": 1, "position": [3, 3], "size": 2},
        ],
        "agvs": [
            {"agv_id": 0, "size": 1},
            {"agv_id": 1, "size": 2},
        ],
        "obstacles": [[8, 8]],
    }
    result = validate_semantic(data)
    assert result["ok"] is True


# =========================================================================
# InputParserAgent (regex fallback)
# =========================================================================

def test_input_parser_basic():
    agent = InputParserAgent()
    out = agent.parse("20x15 map with 4 agvs, 2 large 2 small", use_llm=False)
    assert out["complete"] is True
    mc = out["map_config"]
    assert mc["width"] == 20
    assert mc["height"] == 15
    assert mc["agvs"]["count"] == 4
    assert len(mc["agvs"]["sizes"]) == 4
    assert mc["agvs"]["sizes"].count(2) == 2
    assert mc["agvs"]["sizes"].count(1) == 2


def test_input_parser_missing_info():
    agent = InputParserAgent()
    out = agent.parse("some agvs", use_llm=False)
    assert out["complete"] is False
    assert len(out["missing_fields"]) > 0
    assert out["follow_up_question"] != ""


def test_input_parser_missing_agvs():
    agent = InputParserAgent()
    out = agent.parse("20x15 map", use_llm=False)
    assert out["complete"] is False
    assert any("AGV" in f for f in out["missing_fields"])


def test_input_parser_defaults():
    agent = InputParserAgent()
    out = agent.parse("10x10, 3 agvs", use_llm=False)
    mc = out["map_config"]
    assert out["complete"] is True
    assert mc["shelves"]["count"] == 9
    assert mc["receivers"]["count"] == 2
    assert mc["obstacles"]["count"] == 0
    assert mc["agvs"]["sizes"] == [1, 1, 1]


def test_input_parser_homogeneous():
    agent = InputParserAgent()
    out = agent.parse("10x10, 5 agvs", use_llm=False)
    mc = out["map_config"]
    assert mc["agvs"]["count"] == 5
    assert mc["agvs"]["sizes"] == [1, 1, 1, 1, 1]


def test_input_parser_shelves_override():
    agent = InputParserAgent()
    out = agent.parse("10x10, 2 agvs, shelf 5", use_llm=False)
    mc = out["map_config"]
    assert mc["shelves"]["count"] == 5


def test_input_parser_sim_config_empty():
    agent = InputParserAgent()
    out = agent.parse("10x10, 2 agvs", use_llm=False)
    assert out["sim_config"] == {}


def test_input_parser_output_structure():
    agent = InputParserAgent()
    out = agent.parse("10x10, 2 agvs", use_llm=False)
    assert "complete" in out
    assert "missing_fields" in out
    assert "follow_up_question" in out
    assert "map_config" in out
    assert "sim_config" in out


# =========================================================================
# EnvConfigAgent (fallback)
# =========================================================================

def test_env_config_generate_basic():
    agent = MapBuilder()
    map_config = {
        "width": 8, "height": 6,
        "agvs": {"count": 2, "sizes": [1, 1]},
        "shelves": {"count": 3},
        "receivers": {"count": 1},
        "obstacles": {"count": 0},
    }
    result = agent.generate(map_config, use_llm=False)
    assert result["ok"] is True
    mj = result["map_json"]
    assert mj["map"]["width"] == 8
    assert mj["map"]["height"] == 6
    assert len(mj["agvs"]) == 2
    assert len(mj["wait_zones"]) == 2
    assert len(mj["boxes"]) == 3
    assert len(mj["receivers"]) == 1


def test_env_config_generate_validates():
    agent = MapBuilder()
    map_config = {
        "width": 15, "height": 15,
        "agvs": {"count": 3, "sizes": [1, 1, 2]},
        "shelves": {"count": 5},
        "receivers": {"count": 2},
        "obstacles": {"count": 2},
    }
    result = agent.generate(map_config, use_llm=False)
    assert result["ok"] is True
    val = validate_map(result["map_json"], trial_steps=0)
    assert val["ok"] is True


def test_env_config_agv_wait_zone_match():
    agent = MapBuilder()
    map_config = {
        "width": 20, "height": 20,
        "agvs": {"count": 2, "sizes": [1, 2]},
        "shelves": {"count": 4},
        "receivers": {"count": 1},
        "obstacles": {"count": 0},
    }
    result = agent.generate(map_config, use_llm=False)
    assert result["ok"] is True
    mj = result["map_json"]
    agv_sizes = {a["agv_id"]: a["size"] for a in mj["agvs"]}
    for wz in mj["wait_zones"]:
        assert wz["size"] == agv_sizes[wz["wait_zone_id"]]


def test_env_config_boxes_have_goods():
    agent = MapBuilder()
    map_config = {
        "width": 10, "height": 10,
        "agvs": {"count": 1, "sizes": [1]},
        "shelves": {"count": 4},
        "receivers": {"count": 1},
        "obstacles": {"count": 0},
    }
    result = agent.generate(map_config, use_llm=False)
    assert result["ok"] is True
    for box in result["map_json"]["boxes"]:
        assert len(box["goods_ids"]) >= 1


def test_env_config_sequential_box_ids():
    agent = MapBuilder()
    map_config = {
        "width": 10, "height": 10,
        "agvs": {"count": 1, "sizes": [1]},
        "shelves": {"count": 5},
        "receivers": {"count": 1},
        "obstacles": {"count": 0},
    }
    result = agent.generate(map_config, use_llm=False)
    assert result["ok"] is True
    ids = [b["box_id"] for b in result["map_json"]["boxes"]]
    assert ids == list(range(len(ids)))


# =========================================================================
# AlgorithmAgent (keyword fallback)
# =========================================================================

def test_algo_agent_astar():
    agent = AlgorithmAgent()
    out = agent.select("use astar", use_llm=False)
    assert out["planner_type"] == "astar"
    assert out["scheduler_type"] == "ta"
    assert out["optimize"] is False


def test_algo_agent_cbs():
    agent = AlgorithmAgent()
    out = agent.select("CBS planner", use_llm=False)
    assert out["planner_type"] == "cbs_fw"


def test_algo_agent_dhc():
    agent = AlgorithmAgent()
    out = agent.select("use dhc", use_llm=False)
    assert out["planner_type"] == "dhc"


def test_algo_agent_random_scheduler():
    agent = AlgorithmAgent()
    out = agent.select("random scheduler", use_llm=False)
    assert out["scheduler_type"] == "random"


def test_algo_agent_default():
    agent = AlgorithmAgent()
    out = agent.select("run something", use_llm=False)
    assert out["planner_type"] == "astar"
    assert out["scheduler_type"] == "ta"


def test_algo_agent_optimize_flag():
    agent = AlgorithmAgent()
    out = agent.select("astar with optimize", use_llm=False)
    assert out["optimize"] is True
    assert out["optimize_target"] == "planner"


def test_algo_agent_iterations():
    agent = AlgorithmAgent()
    out = agent.select("astar, optimize 5 rounds", use_llm=False)
    assert out["optimize"] is True
    assert out["max_iterations"] == 5


def test_algo_agent_chinese_optimize():
    agent = AlgorithmAgent()
    out = agent.select("cbs 优化 3轮", use_llm=False)
    assert out["planner_type"] == "cbs_fw"
    assert out["optimize"] is True
    assert out["max_iterations"] == 3


def test_algo_agent_output_structure():
    agent = AlgorithmAgent()
    out = agent.select("astar", use_llm=False)
    assert "planner_type" in out
    assert "scheduler_type" in out
    assert "optimize" in out
    assert "optimize_target" in out
    assert "max_iterations" in out
    assert "reasoning" in out


# =========================================================================
# OptimizerAgent (rule-based fallback)
# =========================================================================

def test_optimizer_good_metrics():
    agent = OptimizerAgent()
    metrics = {"Task Success Rate": 0.95, "finished": True, "sim_steps": 500}
    config = {"planner_type": "astar", "scheduler_type": "ta"}
    out = agent.suggest(metrics, config, [], use_llm=False)
    assert out["should_continue"] is False
    assert out["suggestion"]["action"] == "satisfied"


def test_optimizer_low_success():
    agent = OptimizerAgent()
    metrics = {"Task Success Rate": 0.3, "finished": False, "sim_steps": 800}
    config = {"planner_type": "astar", "scheduler_type": "ta"}
    out = agent.suggest(metrics, config, [], use_llm=False)
    assert out["should_continue"] is True
    assert out["suggestion"]["action"] == "change_algorithm"
    assert out["suggestion"]["new_planner_type"] == "cbs_fw"


def test_optimizer_step_limit_hit():
    agent = OptimizerAgent()
    metrics = {"Task Success Rate": 0.7, "finished": False, "sim_steps": 1000}
    config = {"planner_type": "cbs_fw", "scheduler_type": "ta"}
    out = agent.suggest(metrics, config, [], use_llm=False)
    assert out["suggestion"]["action"] == "adjust_params"
    assert out["suggestion"]["param_changes"].get("max_steps", 0) > 1000


def test_optimizer_avoids_repeat():
    agent = OptimizerAgent()
    metrics = {"Task Success Rate": 0.3, "finished": False, "sim_steps": 500}
    config = {"planner_type": "astar", "scheduler_type": "ta"}
    history = [{"planner_type": "cbs_fw"}]
    out = agent.suggest(metrics, config, history, use_llm=False)
    assert out["suggestion"].get("new_planner_type") != "cbs_fw"


def test_optimizer_stops_after_history_limit():
    agent = OptimizerAgent()
    metrics = {"Task Success Rate": 0.3, "finished": False, "sim_steps": 500}
    config = {"planner_type": "astar", "scheduler_type": "ta"}
    history = [{}, {}, {}]
    out = agent.suggest(metrics, config, history, use_llm=False)
    assert out["should_continue"] is False


def test_optimizer_output_structure():
    agent = OptimizerAgent()
    out = agent.suggest({}, {"planner_type": "astar"}, [], use_llm=False)
    assert "analysis" in out
    assert "should_continue" in out
    assert "suggestion" in out
    assert "action" in out["suggestion"]
    assert "reasoning" in out["suggestion"]


# =========================================================================
# Coordinator (no-llm)
# =========================================================================

def test_coordinator_phase1_success():
    coord = Coordinator(use_llm=False)
    out = coord.run_phase1("10x10, 2 agvs", output_path=None)
    assert out["ok"] is True
    assert "map_json" in out
    assert out["map_json"]["map"]["width"] == 10
    assert out["map_json"]["map"]["height"] == 10
    assert len(out["map_json"]["agvs"]) == 2


def test_coordinator_phase1_missing():
    coord = Coordinator(use_llm=False)
    out = coord.run_phase1("some description", output_path=None)
    assert out["ok"] is False


def test_coordinator_phase1_writes_file():
    coord = Coordinator(use_llm=False)
    fd, tmp = tempfile.mkstemp(suffix=".json")
    os.close(fd)
    try:
        out = coord.run_phase1("10x10, 2 agvs", output_path=tmp)
        assert out["ok"] is True
        assert os.path.isfile(tmp)
        with open(tmp, "r", encoding="utf-8") as f:
            data = json.load(f)
        assert data["map"]["width"] == 10
    finally:
        if os.path.isfile(tmp):
            os.unlink(tmp)


def test_coordinator_phase1_validates_output():
    coord = Coordinator(use_llm=False)
    out = coord.run_phase1("15x15, 3 agvs, 2 large 1 small", output_path=None)
    assert out["ok"] is True
    val = validate_map(out["map_json"], trial_steps=0)
    assert val["ok"] is True


def test_coordinator_phase1_het_sizes():
    coord = Coordinator(use_llm=False)
    out = coord.run_phase1("20x20, 4 agvs, 2 large 2 small", output_path=None)
    assert out["ok"] is True
    sizes = [a["size"] for a in out["map_json"]["agvs"]]
    assert sizes.count(2) == 2
    assert sizes.count(1) == 2


# =========================================================================
# Integration: parse -> generate -> validate pipeline
# =========================================================================

def test_integration_parse_then_generate():
    parser = InputParserAgent()
    parsed = parser.parse("20x15, 4 agvs, 2 large 2 small", use_llm=False)
    assert parsed["complete"] is True

    env = MapBuilder()
    gen = env.generate(parsed["map_config"], use_llm=False)
    assert gen["ok"] is True

    val = validate_map(gen["map_json"], trial_steps=0)
    assert val["ok"] is True

    mj = gen["map_json"]
    assert mj["map"]["width"] == 20
    assert mj["map"]["height"] == 15
    assert len(mj["agvs"]) == 4


def test_integration_parse_with_shelves():
    parser = InputParserAgent()
    parsed = parser.parse("12x12, 3 agvs, shelf 8, receiver 3", use_llm=False)
    assert parsed["complete"] is True
    assert parsed["map_config"]["shelves"]["count"] == 8
    assert parsed["map_config"]["receivers"]["count"] == 3

    env = MapBuilder()
    gen = env.generate(parsed["map_config"], use_llm=False)
    assert gen["ok"] is True
    assert len(gen["map_json"]["boxes"]) == 8
    assert len(gen["map_json"]["receivers"]) == 3
