from __future__ import annotations

import json

from mapf_agent.evolve.core import EvolveRequest, OptimizationTarget
from mapf_agent.evolve.evaluator_template import build_evaluator_code
from mapf_agent.evolve.layout import build_layout_initial_program, load_layout_constraints
from mapf_agent.evolve.map_validation import validate_layout_map


def _constraints() -> dict:
    return load_layout_constraints(
        json.dumps(
            {
                "map": {"width": 12, "height": 10, "floors": 2},
                "agvs": [{"size": 1, "count": 4}, {"size": 2, "count": 2}],
                "boxes": [{"size": 1, "count": 12}],
                "receivers": [{"size": 1, "count": 8}],
                "wait_zones": {"per_agv": True},
                "elevators": [
                    {"size": 1, "count": 1, "fixed_positions": [[5, 5]]},
                    {"size": 2, "count": 1},
                ],
                "simulation": {"planner_type": "astar", "scheduler_type": "ta", "max_steps": 200},
            }
        )
    )


def _generated_map(constraints: dict) -> dict:
    namespace = {}
    exec(build_layout_initial_program(), namespace)
    return namespace["generate_map"](constraints)


def test_default_layout_generator_produces_valid_map() -> None:
    constraints = _constraints()
    report = validate_layout_map(_generated_map(constraints), constraints)

    assert report["valid"], report["errors"]
    assert report["reachability_score"] == 1.0


def test_layout_validation_rejects_overlap() -> None:
    constraints = _constraints()
    map_data = _generated_map(constraints)
    first_floor = map_data["floors"][0]
    first_floor["receivers"][0]["position"] = first_floor["boxes"][0]["position"]

    report = validate_layout_map(map_data, constraints)

    assert not report["valid"]
    assert any("overlaps" in error for error in report["errors"])


def test_layout_validation_rejects_moved_fixed_elevator() -> None:
    constraints = _constraints()
    map_data = _generated_map(constraints)
    map_data["elevators"][0]["position"] = [1, 1]

    report = validate_layout_map(map_data, constraints)

    assert not report["valid"]
    assert any("fixed elevator position missing" in error for error in report["errors"])


def test_layout_evaluator_source_compiles() -> None:
    req = EvolveRequest(
        target=OptimizationTarget.LAYOUT,
        layout_constraints="unused",
        layout_constraints_json=json.dumps(_constraints()),
    )
    code = build_evaluator_code(req, OptimizationTarget.LAYOUT)

    compile(code, "layout_evaluator.py", "exec")
