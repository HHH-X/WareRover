"""Generate the evaluator Python source that OpenEvolve will execute."""
from __future__ import annotations

import textwrap
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from mapf_agent.evolve.core import EvolveRequest, OptimizationTarget


def build_evaluator_code(req: "EvolveRequest", target: "OptimizationTarget") -> str:
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
        BASELINE_PLANNER = {req.baseline_planner_type!r}
        BASELINE_SCHEDULER = {req.baseline_scheduler_type!r}
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

        def _resolve_types():
            pt = "{planner_reg}" if TARGET in ("planner","both") else BASELINE_PLANNER
            st = "{scheduler_reg}" if TARGET in ("scheduler","both") else BASELINE_SCHEDULER
            return pt, st

        def _run_single(seed, pt, st, max_steps=None):
            random.seed(seed); np.random.seed(seed)
            cfg = _make_config(seed, max_steps)
            cfg.sim_config.planner_type = pt
            cfg.sim_config.scheduler_type = st
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
                     "collision_score": collision_score,
                     "task_success_rate": task_success_rate,
                     "avg_task_time": avg_task_time,
                     "throughput": throughput,
                     "total_agv_collisions": total_agv_collisions}}

        # ── cascade stage 1: quick single-seed validation ──

        def evaluate_stage1(program_path: str):
            try:
                _register_candidate(program_path)
                pt, st = _resolve_types()
                r = _run_single(SEEDS[0], pt, st, max_steps=_STAGE1_MAX_STEPS)
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
                pt, st = _resolve_types()
                results = [_run_single(s, pt, st) for s in SEEDS]
                return _compute_scores(results)
            except Exception as e:
                print(f"Evaluation failed: {{e}}")
                traceback.print_exc()
                return {{"combined_score":0.0,"error":str(e)}}
    """)
