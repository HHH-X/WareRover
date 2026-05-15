"""Generate the evaluator Python source that OpenEvolve will execute."""
from __future__ import annotations

import textwrap
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from mapf_agent.evolve.core import EvolveRequest, OptimizationTarget


def build_evaluator_code(req: "EvolveRequest", target: "OptimizationTarget") -> str:
    if target.value == "layout":
        return build_layout_evaluator_code(req)

    seeds = list(int(s) for s in req.seeds)
    planner_reg = "evolve_planner"
    scheduler_reg = "evolve_scheduler"
    sys_cfg_json = req.system_config_json or ""

    return textwrap.dedent(f"""\
        from __future__ import annotations
        import importlib.util, json, random, traceback
        from typing import Any, Dict, Type
        import numpy as np
        from config.settings import SystemConfig
        from core.agvmanager import AGVManager
        from core.env import Env
        from core.fault_manager import FaultManager
        from core.warehouse_map import WarehouseMap
        from core.elevator import ElevatorManager
        from core.ordermanager import OrderManager
        from core.simulator import Simulator
        from planner.base_planner import BasePlanner
        from scheduler.base_scheduler import BaseScheduler
        from utils.algorithm_registry import AlgorithmRegistry
        from utils.logger import GlobalLogger
        from utils.simulation_clock import SimulationClock
        from utils.simulation_context import SimulationContext

        TARGET = {target.value!r}
        SEEDS = {seeds!r}
        _SYS_CFG_JSON = {sys_cfg_json!r}
        _STAGE1_MAX_STEPS = 200

        _registry = AlgorithmRegistry()

        def _load_module(path: str):
            spec = importlib.util.spec_from_file_location("candidate", path)
            if spec is None or spec.loader is None:
                raise RuntimeError(f"Cannot load candidate module from {{path}}")
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            return mod

        def _pick_subclass(mod, base, kind):
            candidates = [
                v for v in mod.__dict__.values()
                if isinstance(v, type)
                and issubclass(v, base)
                and v is not base
                and v.__module__ == mod.__name__
            ]
            if not candidates:
                imported = [
                    v.__name__ for v in mod.__dict__.values()
                    if isinstance(v, type) and issubclass(v, base) and v is not base
                ]
                suffix = f"; imported candidates: {{imported}}" if imported else ""
                raise RuntimeError(f"No local {{kind}} subclass found in candidate module{{suffix}}")
            if len(candidates) == 1:
                return candidates[0]

            name_matches = [c for c in candidates if kind.lower() in c.__name__.lower()]
            if len(name_matches) == 1:
                return name_matches[0]
            names = [c.__name__ for c in candidates]
            raise RuntimeError(f"Ambiguous {{kind}} subclasses in candidate module: {{names}}")

        def _register_candidate(program_path):
            mod = _load_module(program_path)
            if TARGET in ("planner", "both"):
                _registry.register_planner("{planner_reg}", _pick_subclass(mod, BasePlanner, "planner"))
            if TARGET in ("scheduler", "both"):
                _registry.register_scheduler("{scheduler_reg}", _pick_subclass(mod, BaseScheduler, "scheduler"))

        def _make_config(seed, max_steps=None):
            if _SYS_CFG_JSON:
                cfg = SystemConfig()
                patch = json.loads(_SYS_CFG_JSON)
                for section_name, section_vals in patch.items():
                    section = getattr(cfg, section_name, None)
                    if section is None:
                        continue
                    for k, v in section_vals.items():
                        if hasattr(section, k):
                            setattr(section, k, v)
            else:
                cfg = SystemConfig()
            cfg.sim_config.order_seed = seed
            cfg.fault_config.fault_seed = seed
            if max_steps is not None:
                cfg.sim_config.max_steps = max_steps
            return cfg

        def _run_single(seed, max_steps=None):
            random.seed(seed); np.random.seed(seed)
            cfg = _make_config(seed, max_steps)
            if TARGET == "planner":
                cfg.sim_config.planner_type = "{planner_reg}"
            elif TARGET == "scheduler":
                cfg.sim_config.scheduler_type = "{scheduler_reg}"
            elif TARGET == "both":
                cfg.sim_config.planner_type = "{planner_reg}"
                cfg.sim_config.scheduler_type = "{scheduler_reg}"
            ctx = SimulationContext()
            ctx.system_config = cfg
            ctx.logger = GlobalLogger(ctx)
            ctx.clock = SimulationClock(ctx)
            ctx.warehouse_map = WarehouseMap(ctx)
            ctx.order_manager = OrderManager(ctx)
            ctx.agv_manager = AGVManager(ctx)
            ctx.elevator_manager = ElevatorManager(ctx)
            ctx.env = Env(ctx)
            ctx.fault_manager = FaultManager(ctx)
            ctx.scheduler = _registry.build_scheduler(ctx)
            ctx.planner = _registry.build_planner(ctx)
            ctx.simulator = Simulator(ctx)
            while not ctx.order_manager.is_all_orders_completed() and ctx.clock.now() < cfg.sim_config.max_steps:
                ctx.simulator.step(); ctx.fault_manager.step()
            m = ctx.logger.get_final_metrics(ctx.clock.now())
            return {{"finished": bool(ctx.order_manager.is_all_orders_completed()),
                     "task_success_rate": float(m.get("Task Success Rate", 0.0)),
                     "avg_task_time": float(m.get("Avg Task Time", 0.0)),
                     "throughput": float(m.get("Throughput", 0.0)),
                     "total_agv_collisions": float(m.get("Total AGV Collisions", 0.0)),
                     "max_steps": float(cfg.sim_config.max_steps),
                     "total_orders_limit": float(cfg.sim_config.total_orders_limit)}}

        def _clamp01(value):
            return min(max(float(value), 0.0), 1.0)

        def _compute_scores(results):
            n = len(results)
            task_success_rate = sum(r["task_success_rate"] for r in results) / n
            avg_task_time = sum(r["avg_task_time"] for r in results) / n
            throughput = sum(r["throughput"] for r in results) / n
            total_agv_collisions = sum(r["total_agv_collisions"] for r in results) / n
            max_steps = max(sum(r["max_steps"] for r in results) / n, 1.0)
            total_orders_limit = max(sum(r["total_orders_limit"] for r in results) / n, 1.0)

            success_score = _clamp01(task_success_rate)
            task_time_scale = max(max_steps / 3.0, 1.0)
            throughput_scale = max(total_orders_limit / max_steps, 1e-9)
            collision_scale = max(2.0 * total_orders_limit, 1.0)

            task_time_score = 1.0 / (1.0 + max(avg_task_time, 0.0) / task_time_scale)
            throughput_score = max(throughput, 0.0) / (max(throughput, 0.0) + throughput_scale)
            collision_score = 1.0 / (1.0 + max(total_agv_collisions, 0.0) / collision_scale)

            task_time_score *= success_score
            throughput_score *= success_score

            combined = (
                0.40 * success_score
                + 0.25 * throughput_score
                + 0.20 * task_time_score
                + 0.15 * collision_score
            )
            return {{"combined_score": combined,
                     "success_score": success_score,
                     "task_time_score": task_time_score,
                     "throughput_score": throughput_score,
                     "collision_score": collision_score}}

        # ── cascade stage 1: quick single-seed validation ──

        def evaluate_stage1(program_path: str):
            try:
                _register_candidate(program_path)
                r = _run_single(SEEDS[0], max_steps=_STAGE1_MAX_STEPS)
                return _compute_scores([r])
            except Exception as e:
                print(f"Stage-1 failed: {{e}}")
                traceback.print_exc()
                return {{"combined_score":0.0,"error":str(e)}}

        # ── cascade stage 2 / full evaluation ──

        def evaluate_stage2(program_path: str):
            return evaluate(program_path)

        def evaluate(program_path: str):
            try:
                _register_candidate(program_path)
                results = [_run_single(s) for s in SEEDS]
                return _compute_scores(results)
            except Exception as e:
                print(f"Evaluation failed: {{e}}")
                traceback.print_exc()
                return {{"combined_score":0.0,"error":str(e)}}
    """)


def build_layout_evaluator_code(req: "EvolveRequest") -> str:
    seeds = list(int(s) for s in req.seeds)
    constraints_json = req.layout_constraints_json or "{}"
    sys_cfg_json = req.system_config_json or ""

    return textwrap.dedent(f"""\
        from __future__ import annotations
        import importlib.util, json, os, random, tempfile, traceback
        from typing import Any, Dict, List
        import numpy as np
        from config.settings import SystemConfig
        from core.agvmanager import AGVManager
        from core.env import Env
        from core.fault_manager import FaultManager
        from core.warehouse_map import WarehouseMap
        from core.elevator import ElevatorManager
        from core.ordermanager import OrderManager
        from core.simulator import Simulator
        from mapf_agent.evolve.map_validation import validate_layout_map
        from openevolve.evaluation_result import EvaluationResult
        from utils.algorithm_registry import default_registry
        from utils.logger import GlobalLogger
        from utils.simulation_clock import SimulationClock
        from utils.simulation_context import SimulationContext

        SEEDS = {seeds!r}
        CONSTRAINTS = json.loads({constraints_json!r})
        _SYS_CFG_JSON = {sys_cfg_json!r}
        _STAGE1_MAX_STEPS = 200

        def _load_module(path: str):
            spec = importlib.util.spec_from_file_location("candidate_layout", path)
            if spec is None or spec.loader is None:
                raise RuntimeError(f"Cannot load candidate module from {{path}}")
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            return mod

        def _generate_map(program_path: str) -> Dict[str, Any]:
            mod = _load_module(program_path)
            func = getattr(mod, "generate_map", None)
            if not callable(func):
                raise RuntimeError("candidate must define generate_map(constraints)")
            result = func(json.loads(json.dumps(CONSTRAINTS)))
            if not isinstance(result, dict):
                raise RuntimeError("generate_map() must return a dict")
            return result

        def _make_config(seed, map_file: str, max_steps=None):
            cfg = SystemConfig()
            if _SYS_CFG_JSON:
                patch = json.loads(_SYS_CFG_JSON)
                for section_name, section_vals in patch.items():
                    section = getattr(cfg, section_name, None)
                    if section is None:
                        continue
                    for k, v in section_vals.items():
                        if hasattr(section, k):
                            setattr(section, k, v)

            sim_patch = dict(CONSTRAINTS.get("simulation") or {{}})
            if "planner_type" in sim_patch:
                cfg.sim_config.planner_type = sim_patch.pop("planner_type")
            if "scheduler_type" in sim_patch:
                cfg.sim_config.scheduler_type = sim_patch.pop("scheduler_type")
            for k, v in sim_patch.items():
                if hasattr(cfg.sim_config, k):
                    setattr(cfg.sim_config, k, v)
            cfg.sim_config.map_file = map_file
            cfg.sim_config.order_seed = seed
            cfg.fault_config.fault_seed = seed
            if max_steps is not None:
                cfg.sim_config.max_steps = max_steps
            return cfg

        def _write_temp_map(map_data: Dict[str, Any]) -> str:
            handle = tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8")
            try:
                json.dump(map_data, handle, ensure_ascii=False)
                return handle.name
            finally:
                handle.close()

        def _top_heatmap(heatmap: Dict[str, Dict[str, int]], limit: int = 20) -> Dict[str, List[Dict[str, Any]]]:
            result = {{}}
            for floor_id, cells in heatmap.items():
                ordered = sorted(cells.items(), key=lambda item: item[1], reverse=True)[:limit]
                result[floor_id] = [
                    {{"position": [int(part) for part in key.split(",")], "visits": int(visits)}}
                    for key, visits in ordered
                ]
            return result

        def _observe_heatmap(ctx, heatmap: Dict[str, Dict[str, int]]) -> None:
            for agv_id, pos in ctx.agv_manager.get_all_current_pos().items():
                floor_id = str(ctx.agv_manager.get_agv_floor(agv_id))
                key = f"{{int(pos[0])}},{{int(pos[1])}}"
                heatmap.setdefault(floor_id, {{}})[key] = heatmap.setdefault(floor_id, {{}}).get(key, 0) + 1

        def _run_single(seed, map_data: Dict[str, Any], max_steps=None, collect_artifacts: bool = False):
            random.seed(seed); np.random.seed(seed)
            map_file = _write_temp_map(map_data)
            heatmap: Dict[str, Dict[str, int]] = {{}}
            try:
                cfg = _make_config(seed, map_file, max_steps)
                ctx = SimulationContext()
                ctx.system_config = cfg
                ctx.logger = GlobalLogger(ctx)
                ctx.clock = SimulationClock(ctx)
                ctx.warehouse_map = WarehouseMap(ctx)
                ctx.order_manager = OrderManager(ctx)
                ctx.agv_manager = AGVManager(ctx)
                ctx.elevator_manager = ElevatorManager(ctx)
                ctx.env = Env(ctx)
                ctx.fault_manager = FaultManager(ctx)
                ctx.scheduler = default_registry.build_scheduler(ctx)
                ctx.planner = default_registry.build_planner(ctx)
                ctx.simulator = Simulator(ctx)
                while not ctx.order_manager.is_all_orders_completed() and ctx.clock.now() < cfg.sim_config.max_steps:
                    if collect_artifacts:
                        _observe_heatmap(ctx, heatmap)
                    ctx.simulator.step(); ctx.fault_manager.step()
                if collect_artifacts:
                    _observe_heatmap(ctx, heatmap)
                m = ctx.logger.get_final_metrics(ctx.clock.now())
                result = {{"finished": bool(ctx.order_manager.is_all_orders_completed()),
                         "task_success_rate": float(m.get("Task Success Rate", 0.0)),
                         "avg_task_time": float(m.get("Avg Task Time", 0.0)),
                         "throughput": float(m.get("Throughput", 0.0)),
                         "total_agv_collisions": float(m.get("Total AGV Collisions", 0.0)),
                         "total_agv_elevator_wait_blocks": float(m.get("Total AGV Elevator Wait Blocks", 0.0)),
                         "max_steps": float(cfg.sim_config.max_steps),
                         "total_orders_limit": float(cfg.sim_config.total_orders_limit),
                         "sim_steps": float(ctx.clock.now())}}
                if collect_artifacts:
                    result["artifacts"] = {{
                        "traffic_heatmap": _top_heatmap(heatmap),
                        "congestion_report": {{
                            "total_agv_collisions": result["total_agv_collisions"],
                            "total_agv_elevator_wait_blocks": result["total_agv_elevator_wait_blocks"],
                            "block_reason_counts": ctx.agv_manager.block_reason_counts,
                        }},
                        "runtime_tail": ctx.logger.get_runtime_logs(20),
                    }}
                return result
            finally:
                try:
                    os.unlink(map_file)
                except OSError:
                    pass

        def _clamp01(value):
            return min(max(float(value), 0.0), 1.0)

        def _compute_scores(results, validation):
            n = len(results)
            task_success_rate = sum(r["task_success_rate"] for r in results) / n
            avg_task_time = sum(r["avg_task_time"] for r in results) / n
            throughput = sum(r["throughput"] for r in results) / n
            total_agv_collisions = sum(r["total_agv_collisions"] for r in results) / n
            total_agv_elevator_wait_blocks = sum(r["total_agv_elevator_wait_blocks"] for r in results) / n
            max_steps = max(sum(r["max_steps"] for r in results) / n, 1.0)
            total_orders_limit = max(sum(r["total_orders_limit"] for r in results) / n, 1.0)

            validity_score = 1.0
            reachability_score = _clamp01(validation.get("reachability_score", 1.0))
            success_score = _clamp01(task_success_rate)
            task_time_scale = max(max_steps / 3.0, 1.0)
            throughput_scale = max(total_orders_limit / max_steps, 1e-9)
            congestion_events = max(total_agv_collisions, 0.0) + max(total_agv_elevator_wait_blocks, 0.0)
            congestion_scale = max(2.0 * total_orders_limit, 1.0)

            task_time_score = 1.0 / (1.0 + max(avg_task_time, 0.0) / task_time_scale)
            throughput_score = max(throughput, 0.0) / (max(throughput, 0.0) + throughput_scale)
            congestion_score = 1.0 / (1.0 + congestion_events / congestion_scale)

            task_time_score *= success_score
            throughput_score *= success_score
            combined = (
                0.35 * success_score
                + 0.20 * throughput_score
                + 0.15 * task_time_score
                + 0.15 * congestion_score
                + 0.10 * reachability_score
                + 0.05 * validity_score
            )
            return {{"combined_score": combined,
                     "validity_score": validity_score,
                     "reachability_score": reachability_score,
                     "success_score": success_score,
                     "task_time_score": task_time_score,
                     "throughput_score": throughput_score,
                     "congestion_score": congestion_score}}

        def _invalid_result(validation, stage: str):
            return EvaluationResult(
                metrics={{
                    "combined_score": 0.0,
                    "validity_score": 0.0,
                    "reachability_score": float(validation.get("reachability_score", 0.0)),
                    "stage1_passed": 0.0 if stage == "stage1" else 1.0,
                }},
                artifacts={{
                    "validation_report": json.dumps(validation, ensure_ascii=False, indent=2),
                    "map_summary": json.dumps(validation.get("summary", {{}}), ensure_ascii=False, indent=2),
                }},
            )

        def _evaluate(program_path: str, max_steps=None, seeds=None, collect_artifacts: bool = False, stage: str = "full"):
            map_data = _generate_map(program_path)
            validation = validate_layout_map(map_data, CONSTRAINTS)
            if not validation.get("valid"):
                return _invalid_result(validation, stage)
            use_seeds = list(seeds or SEEDS)
            results = [
                _run_single(seed, map_data, max_steps=max_steps, collect_artifacts=(collect_artifacts and idx == 0))
                for idx, seed in enumerate(use_seeds)
            ]
            metrics = _compute_scores(results, validation)
            if stage == "stage1":
                metrics["stage1_passed"] = 1.0
            artifacts = {{
                "validation_report": json.dumps(validation, ensure_ascii=False, indent=2),
                "map_summary": json.dumps(validation.get("summary", {{}}), ensure_ascii=False, indent=2),
            }}
            for result in results:
                if result.get("artifacts"):
                    for key, value in result["artifacts"].items():
                        artifacts[key] = json.dumps(value, ensure_ascii=False, indent=2)
                    break
            return EvaluationResult(metrics=metrics, artifacts=artifacts)

        def evaluate_stage1(program_path: str):
            try:
                return _evaluate(program_path, max_steps=_STAGE1_MAX_STEPS, seeds=[SEEDS[0]], stage="stage1")
            except Exception as e:
                print(f"Stage-1 failed: {{e}}")
                traceback.print_exc()
                return EvaluationResult(metrics={{"combined_score":0.0,"stage1_passed":0.0,"error":0.0}},
                                        artifacts={{"stderr": str(e), "traceback": traceback.format_exc()}})

        def evaluate_stage2(program_path: str):
            return evaluate(program_path)

        def evaluate(program_path: str):
            try:
                return _evaluate(program_path, collect_artifacts=True)
            except Exception as e:
                print(f"Evaluation failed: {{e}}")
                traceback.print_exc()
                return EvaluationResult(metrics={{"combined_score":0.0,"error":0.0}},
                                        artifacts={{"stderr": str(e), "traceback": traceback.format_exc()}})
    """)
