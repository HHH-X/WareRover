"""OpenEvolve stage-2 optimization pipeline (migrated from evolution/stage2/)."""
from __future__ import annotations

import textwrap
import uuid
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Dict, Optional, Sequence, Union

CodeSource = Union[str, Path]
_REPO_ROOT = Path(__file__).resolve().parent.parent


class OptimizationTarget(str, Enum):
    PLANNER = "planner"
    SCHEDULER = "scheduler"
    BOTH = "both"


@dataclass
class EvolveRequest:
    target: OptimizationTarget
    planner_source: Optional[CodeSource] = None
    scheduler_source: Optional[CodeSource] = None
    baseline_planner_type: str = "astar"
    baseline_scheduler_type: str = "random"
    config_path: Optional[CodeSource] = None
    iterations: Optional[int] = None
    output_root: CodeSource = "agent/evolve_runs"
    seeds: Sequence[int] = (42, 43, 44)


@dataclass
class EvolveResult:
    run_dir: str
    output_dir: Optional[str]
    best_score: float
    best_metrics: Dict[str, Any]
    best_code: str


def _read_source(source: CodeSource, label: str) -> str:
    src = Path(str(source))
    if src.exists():
        return src.read_text(encoding="utf-8")
    code = str(source)
    if not code.strip():
        raise ValueError(f"{label} source is empty")
    return code


def _strip_markers(code: str) -> str:
    return code.replace("# EVOLVE-BLOCK-START", "").replace("# EVOLVE-BLOCK-END", "").strip()


def _build_initial_program(target: OptimizationTarget, planner_code: str, scheduler_code: str) -> str:
    chunks = ["# EVOLVE-BLOCK-START"]
    if target in (OptimizationTarget.PLANNER, OptimizationTarget.BOTH):
        chunks.append("# -------- Planner Candidate --------")
        chunks.append(_strip_markers(planner_code))
    if target in (OptimizationTarget.SCHEDULER, OptimizationTarget.BOTH):
        chunks.append("# -------- Scheduler Candidate --------")
        chunks.append(_strip_markers(scheduler_code))
    chunks.append("# EVOLVE-BLOCK-END")
    return "\n\n".join(chunks) + "\n"


def _build_default_config(target: OptimizationTarget) -> str:
    return textwrap.dedent(f"""\
        max_iterations: 10
        checkpoint_interval: 5
        llm:
          primary_model: "DeepSeek-V3.2"
          primary_model_weight: 0.8
          secondary_model: "DeepSeek-V3.2"
          secondary_model_weight: 0.2
          api_base: "https://api.modelarts-maas.com/v1"
          api_key: "$OPENAI_API_KEY"
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
    """)


def _build_evaluator_code(req: EvolveRequest, target: OptimizationTarget) -> str:
    seeds = list(int(s) for s in req.seeds)
    planner_reg = "evolve_planner"
    scheduler_reg = "evolve_scheduler"
    return textwrap.dedent(f"""\
        from __future__ import annotations
        import importlib.util, random
        from typing import Any, Dict, Type
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
        BASELINE_PLANNER = {req.baseline_planner_type!r}
        BASELINE_SCHEDULER = {req.baseline_scheduler_type!r}
        SEEDS = {seeds!r}

        def _load_module(path: str):
            spec = importlib.util.spec_from_file_location("candidate", path)
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            return mod

        def _pick_subclass(mod, base, kind):
            for v in mod.__dict__.values():
                if isinstance(v, type) and issubclass(v, base) and v is not base:
                    if v.__module__ == mod.__name__:
                        return v
            for v in mod.__dict__.values():
                if isinstance(v, type) and issubclass(v, base) and v is not base:
                    return v
            raise RuntimeError(f"No {{kind}} subclass found")

        def _run_single(seed, pt, st):
            random.seed(seed); np.random.seed(seed)
            ctx = SimulationContext()
            ctx.system_config = SystemConfig()
            ctx.system_config.sim_config.order_seed = seed
            ctx.system_config.fault_config.fault_seed = seed
            ctx.system_config.sim_config.planner_type = pt
            ctx.system_config.sim_config.scheduler_type = st
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
            while not ctx.order_manager.is_all_orders_completed() and ctx.clock.now() < ctx.system_config.sim_config.max_steps:
                ctx.simulator.step(); ctx.fault_manager.step()
            m = ctx.logger.get_final_metrics(ctx.clock.now())
            return {{"finished": bool(ctx.order_manager.is_all_orders_completed()),
                     "task_success_rate": float(m.get("Task Success Rate", 0.0)),
                     "sim_steps": float(m.get("Sim Steps", ctx.clock.now())),
                     "planner_avg_time": float(m.get("Planner Avg Time", 0.0))}}

        def evaluate(program_path: str):
            try:
                mod = _load_module(program_path)
                if TARGET in ("planner", "both"):
                    PlannerRegistry.register("{planner_reg}", _pick_subclass(mod, BasePlanner, "planner"))
                if TARGET in ("scheduler", "both"):
                    SchedulerRegistry.register("{scheduler_reg}", _pick_subclass(mod, BaseScheduler, "scheduler"))
                results = []
                for s in SEEDS:
                    pt = "{planner_reg}" if TARGET in ("planner","both") else BASELINE_PLANNER
                    st = "{scheduler_reg}" if TARGET in ("scheduler","both") else BASELINE_SCHEDULER
                    results.append(_run_single(s, pt, st))
                comp = sum(r["task_success_rate"] for r in results)/len(results)
                mk = sum(r["sim_steps"] for r in results)/len(results)
                pt_t = sum(r["planner_avg_time"] for r in results)/len(results)
                stab = sum(1.0 if r["finished"] else 0.0 for r in results)/len(results)
                cs = min(max(comp,0),1)
                ms = 1.0/(1.0+max(mk,0))
                ts = 1.0/(1.0+max(pt_t*1e3,0))
                ss = min(max(stab,0),1)
                combined = 0.35*cs + 0.35*ms + 0.20*ts + 0.10*ss
                return {{"combined_score":combined,"completion_score":cs,"makespan_score":ms,
                         "time_score":ts,"stability_score":ss}}
            except Exception as e:
                return {{"combined_score":0.0,"error":str(e)}}
    """)


def run_evolution(request: EvolveRequest) -> EvolveResult:
    target = request.target
    if target in (OptimizationTarget.PLANNER, OptimizationTarget.BOTH) and not request.planner_source:
        raise ValueError("planner_source is required for planner/both optimization")
    if target in (OptimizationTarget.SCHEDULER, OptimizationTarget.BOTH) and not request.scheduler_source:
        raise ValueError("scheduler_source is required for scheduler/both optimization")

    planner_code = _read_source(request.planner_source, "planner") if request.planner_source else ""
    scheduler_code = _read_source(request.scheduler_source, "scheduler") if request.scheduler_source else ""

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    run_id = f"evolve_{target.value}_{ts}_{uuid.uuid4().hex[:6]}"
    run_dir = Path(request.output_root) / run_id
    run_dir.mkdir(parents=True, exist_ok=True)

    init_path = run_dir / "initial_program.py"
    eval_path = run_dir / "evaluator.py"
    cfg_path = run_dir / "config.yaml"
    out_dir = run_dir / "openevolve_output"

    init_path.write_text(_build_initial_program(target, planner_code, scheduler_code), encoding="utf-8")
    eval_path.write_text(_build_evaluator_code(request, target), encoding="utf-8")
    cfg_text = _read_source(request.config_path, "config") if request.config_path else _build_default_config(target)
    cfg_path.write_text(cfg_text, encoding="utf-8")

    import sys
    oe_src = _REPO_ROOT / "openevolve"
    if str(_REPO_ROOT) not in sys.path:
        sys.path.insert(0, str(_REPO_ROOT))
    if str(oe_src) not in sys.path:
        sys.path.insert(0, str(oe_src))

    from openevolve.api import run_evolution as oe_run

    evo = oe_run(
        initial_program=str(init_path),
        evaluator=str(eval_path),
        config=str(cfg_path),
        iterations=request.iterations,
        output_dir=str(out_dir),
        cleanup=False,
    )

    return EvolveResult(
        run_dir=str(run_dir),
        output_dir=evo.output_dir,
        best_score=float(evo.best_score),
        best_metrics=dict(evo.metrics or {}),
        best_code=evo.best_code or "",
    )
