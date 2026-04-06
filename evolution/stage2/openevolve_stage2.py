"""
Stage-2 optimization pipeline for MAPF planner/scheduler implementations.

Supports:
- optimize planner only
- optimize scheduler only
- optimize both in one program

Input sources can be file paths or raw code strings.
"""

from __future__ import annotations

import textwrap
import uuid
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Dict, Optional, Sequence, Union


CodeSource = Union[str, Path]


class OptimizationTarget(str, Enum):
    PLANNER = "planner"
    SCHEDULER = "scheduler"
    BOTH = "both"


@dataclass
class Stage2EvolutionRequest:
    target: OptimizationTarget
    planner_source: Optional[CodeSource] = None
    scheduler_source: Optional[CodeSource] = None

    # Baseline counterpart used when only one side is optimized.
    baseline_planner_type: str = "astar"
    baseline_scheduler_type: str = "random"

    # OpenEvolve settings
    config_path: Optional[CodeSource] = None
    iterations: Optional[int] = None
    output_root: CodeSource = "evolution/stage2_runs"
    cleanup_temp: bool = False

    # Evaluation controls
    seeds: Sequence[int] = (42, 43, 44)
    planner_registry_name: str = "stage2_evolved_planner"
    scheduler_registry_name: str = "stage2_evolved_scheduler"


@dataclass
class Stage2EvolutionResult:
    run_dir: str
    output_dir: Optional[str]
    initial_program_path: str
    evaluator_path: str
    config_path: str
    best_score: float
    best_metrics: Dict[str, Any]
    best_code: str


def _as_target(value: Union[OptimizationTarget, str]) -> OptimizationTarget:
    if isinstance(value, OptimizationTarget):
        return value
    return OptimizationTarget(str(value).strip().lower())


def _read_source(source: CodeSource, label: str) -> str:
    src = Path(str(source))
    if src.exists():
        return src.read_text(encoding="utf-8")
    code = str(source)
    if not code.strip():
        raise ValueError(f"{label} source is empty")
    return code


def _strip_evolve_markers(code: str) -> str:
    return (
        code.replace("# EVOLVE-BLOCK-START", "")
        .replace("# EVOLVE-BLOCK-END", "")
        .strip()
    )


def _build_initial_program(target: OptimizationTarget, planner_code: str, scheduler_code: str) -> str:
    chunks = ["# EVOLVE-BLOCK-START"]
    if target in (OptimizationTarget.PLANNER, OptimizationTarget.BOTH):
        chunks.append("# -------- Planner Candidate --------")
        chunks.append(_strip_evolve_markers(planner_code))
    if target in (OptimizationTarget.SCHEDULER, OptimizationTarget.BOTH):
        chunks.append("# -------- Scheduler Candidate --------")
        chunks.append(_strip_evolve_markers(scheduler_code))
    chunks.append("# EVOLVE-BLOCK-END")
    return "\n\n".join(chunks) + "\n"


def _build_default_config_yaml(target: OptimizationTarget) -> str:
    return textwrap.dedent(
        f"""\
        max_iterations: 10
        checkpoint_interval: 5

        llm:
          primary_model: "DeepSeek-V3.2"
          primary_model_weight: 0.8
          secondary_model: "DeepSeek-V3.2"
          secondary_model_weight: 0.2
          api_base: "https://api.modelarts-maas.com/v1"
          api_key: "gMUA0hpwCkyk2FQ32r7Al9XipidNzbaCad2uIXHzDzkXFsQbm9IYouRnUsPG379dKzM6hL604YwUoEWyDnEW5Q"
          temperature: 0.7
          max_tokens: 10000
          timeout: 120

        prompt:
          system_message: "Optimize complete MAPF {target.value} implementation class code while preserving interface compatibility and runtime robustness."

        database:
          population_size: 30
          archive_size: 10
          num_islands: 2
          elite_selection_ratio: 0.2
          exploitation_ratio: 0.7
          similarity_threshold: 0.99

        evaluator:
          timeout: 180
          cascade_evaluation: false
          parallel_evaluations: 2

        diff_based_evolution: true
        max_code_length: 60000
        """
    )


def _build_evaluator_code(request: Stage2EvolutionRequest, target: OptimizationTarget) -> str:
    seeds = list(int(s) for s in request.seeds)
    return textwrap.dedent(
        f"""\
        from __future__ import annotations

        import importlib.util
        import random
        from typing import Any, Dict, List, Tuple, Type

        import numpy as np

        from config.settings import SystemConfig
        from core.agvmanager import AGVManager
        from core.env import Env
        from core.fault_manager import FaultManager
        from core.gridmap import GridMap
        from core.ordermanager import OrderManager
        from core.simulator import Simulator
        from planner.base_planner import BasePlanner
        from scheduler.base_scheduler import BaseScheduler
        from utils.algorithm_factory import build_planner, build_scheduler
        from utils.algorithm_registry import PlannerRegistry, SchedulerRegistry, init_default_registries
        from utils.logger import GlobalLogger
        from utils.simulation_clock import SimulationClock
        from utils.simulation_context import SimulationContext

        TARGET = {target.value!r}
        BASELINE_PLANNER = {request.baseline_planner_type!r}
        BASELINE_SCHEDULER = {request.baseline_scheduler_type!r}
        PLANNER_REG_NAME = {request.planner_registry_name!r}
        SCHEDULER_REG_NAME = {request.scheduler_registry_name!r}
        SEEDS = {seeds!r}


        def _safe_score01(v: float) -> float:
            if v < 0:
                return 0.0
            if v > 1:
                return 1.0
            return float(v)


        def _normalize_inverse(value: float) -> float:
            if value < 0:
                value = 0
            return 1.0 / (1.0 + float(value))


        def _load_module(program_path: str):
            spec = importlib.util.spec_from_file_location("stage2_candidate", program_path)
            if spec is None or spec.loader is None:
                raise RuntimeError("Cannot load candidate module")
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            return module


        def _pick_subclass(module, base_cls: Type, kind: str):
            candidates = []
            for _, value in module.__dict__.items():
                if isinstance(value, type) and issubclass(value, base_cls) and value is not base_cls:
                    candidates.append(value)
            if not candidates:
                raise RuntimeError(f"No {{kind}} subclass found in candidate module")
            local = [c for c in candidates if c.__module__ == module.__name__]
            return local[0] if local else candidates[0]


        def _run_single(seed: int, planner_type: str, scheduler_type: str) -> Dict[str, Any]:
            random.seed(seed)
            np.random.seed(seed)

            ctx = SimulationContext()
            ctx.system_config = SystemConfig()
            ctx.system_config.sim_config.order_seed = seed
            ctx.system_config.fault_config.fault_seed = seed
            ctx.system_config.sim_config.planner_type = planner_type
            ctx.system_config.sim_config.scheduler_type = scheduler_type
            init_default_registries()

            ctx.logger = GlobalLogger(ctx)
            ctx.clock = SimulationClock(ctx)
            ctx.grid_map = GridMap(ctx)
            ctx.order_manager = OrderManager(ctx)
            ctx.agv_manager = AGVManager(ctx)
            ctx.env = Env(ctx)
            ctx.fault_manager = FaultManager(ctx)
            ctx.scheduler = build_scheduler(ctx)
            ctx.planner = build_planner(ctx)
            ctx.simulator = Simulator(ctx)

            while (
                not ctx.order_manager.is_all_orders_completed()
                and ctx.clock.now() < ctx.system_config.sim_config.max_steps
            ):
                ctx.simulator.step()
                ctx.fault_manager.step()

            metrics = ctx.logger.get_final_metrics(ctx.clock.now())
            return {{
                "finished": bool(ctx.order_manager.is_all_orders_completed()),
                "task_success_rate": float(metrics.get("Task Success Rate", 0.0)),
                "sim_steps": float(metrics.get("Sim Steps", ctx.clock.now())),
                "planner_avg_time": float(metrics.get("Planner Avg Time", 0.0)),
            }}


        def evaluate(program_path: str):
            try:
                module = _load_module(program_path)

                planner_cls = None
                scheduler_cls = None
                if TARGET in ("planner", "both"):
                    planner_cls = _pick_subclass(module, BasePlanner, "planner")
                    PlannerRegistry.register(PLANNER_REG_NAME, planner_cls)
                if TARGET in ("scheduler", "both"):
                    scheduler_cls = _pick_subclass(module, BaseScheduler, "scheduler")
                    SchedulerRegistry.register(SCHEDULER_REG_NAME, scheduler_cls)

                run_metrics = []
                for seed in SEEDS:
                    # Set active algo types before each run.
                    if TARGET == "planner":
                        active_planner = PLANNER_REG_NAME
                        active_scheduler = BASELINE_SCHEDULER
                    elif TARGET == "scheduler":
                        active_planner = BASELINE_PLANNER
                        active_scheduler = SCHEDULER_REG_NAME
                    else:
                        active_planner = PLANNER_REG_NAME
                        active_scheduler = SCHEDULER_REG_NAME

                    run_metrics.append(_run_single(int(seed), active_planner, active_scheduler))

                completion_mean = sum(m["task_success_rate"] for m in run_metrics) / len(run_metrics)
                makespan_mean = sum(m["sim_steps"] for m in run_metrics) / len(run_metrics)
                planner_time_mean = sum(m["planner_avg_time"] for m in run_metrics) / len(run_metrics)
                stability_ratio = sum(1.0 if m["finished"] else 0.0 for m in run_metrics) / len(run_metrics)

                completion_score = _safe_score01(completion_mean)
                makespan_score = _normalize_inverse(makespan_mean)
                time_score = _normalize_inverse(planner_time_mean * 1e3)
                stability_score = _safe_score01(stability_ratio)
                combined_score = (
                    0.35 * completion_score
                    + 0.35 * makespan_score
                    + 0.20 * time_score
                    + 0.10 * stability_score
                )

                return {{
                    "completion_score": float(completion_score),
                    "makespan_score": float(makespan_score),
                    "time_score": float(time_score),
                    "stability_score": float(stability_score),
                    "combined_score": float(combined_score),
                    "completion_mean": float(completion_mean),
                    "makespan_mean": float(makespan_mean),
                    "planner_time_mean": float(planner_time_mean),
                    "stability_ratio": float(stability_ratio),
                    "seed_count": float(len(SEEDS)),
                }}
            except Exception as e:
                return {{
                    "completion_score": 0.0,
                    "makespan_score": 0.0,
                    "time_score": 0.0,
                    "stability_score": 0.0,
                    "combined_score": 0.0,
                    "error": str(e),
                }}
        """
    )


def run_stage2_evolution(request: Stage2EvolutionRequest) -> Stage2EvolutionResult:
    """
    Run stage-2 evolution based on target mode and code source format.

    Example:
        from evolution.stage2 import Stage2EvolutionRequest, OptimizationTarget, run_stage2_evolution

        result = run_stage2_evolution(
            Stage2EvolutionRequest(
                target=OptimizationTarget.PLANNER,
                planner_source="planner/astar_planner.py",
                config_path="openevolve/examples/function_minimization/config.yaml",
                iterations=3,
            )
        )
    """
    target = _as_target(request.target)

    if target in (OptimizationTarget.PLANNER, OptimizationTarget.BOTH) and not request.planner_source:
        raise ValueError("planner_source is required for planner/both optimization")
    if target in (OptimizationTarget.SCHEDULER, OptimizationTarget.BOTH) and not request.scheduler_source:
        raise ValueError("scheduler_source is required for scheduler/both optimization")

    planner_code = _read_source(request.planner_source, "planner") if request.planner_source else ""
    scheduler_code = _read_source(request.scheduler_source, "scheduler") if request.scheduler_source else ""

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    run_id = f"stage2_{target.value}_{timestamp}_{uuid.uuid4().hex[:6]}"
    run_dir = Path(request.output_root) / run_id
    run_dir.mkdir(parents=True, exist_ok=True)

    initial_program_path = run_dir / "initial_program.py"
    evaluator_path = run_dir / "evaluator.py"
    config_path = run_dir / "config.yaml"
    openevolve_output_dir = run_dir / "openevolve_output"

    initial_program_path.write_text(
        _build_initial_program(target, planner_code, scheduler_code),
        encoding="utf-8",
    )
    evaluator_path.write_text(_build_evaluator_code(request, target), encoding="utf-8")

    if request.config_path:
        cfg_text = _read_source(request.config_path, "config")
    else:
        cfg_text = _build_default_config_yaml(target)
    config_path.write_text(cfg_text, encoding="utf-8")

    # Lazy import to avoid forcing OpenEvolve dependency at module import time.
    import sys

    repo_root = Path(__file__).resolve().parents[2]
    openevolve_src = repo_root / "openevolve"
    if str(repo_root) not in sys.path:
        sys.path.insert(0, str(repo_root))
    if str(openevolve_src) not in sys.path:
        sys.path.insert(0, str(openevolve_src))

    from openevolve.api import run_evolution

    evo_result = run_evolution(
        initial_program=str(initial_program_path),
        evaluator=str(evaluator_path),
        config=str(config_path),
        iterations=request.iterations,
        output_dir=str(openevolve_output_dir),
        cleanup=request.cleanup_temp,
    )

    return Stage2EvolutionResult(
        run_dir=str(run_dir),
        output_dir=evo_result.output_dir,
        initial_program_path=str(initial_program_path),
        evaluator_path=str(evaluator_path),
        config_path=str(config_path),
        best_score=float(evo_result.best_score),
        best_metrics=dict(evo_result.metrics or {}),
        best_code=evo_result.best_code or "",
    )
