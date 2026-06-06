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
    evaluation_runs = max(1, int(req.evaluation_runs))
    evaluation_workers = (
        None if req.evaluation_workers is None else max(1, int(req.evaluation_workers))
    )
    simulation_timeout_seconds = max(1.0, float(req.simulation_timeout_seconds))
    planner_reg = "evolve_planner"
    scheduler_reg = "evolve_scheduler"
    sys_cfg_json = req.system_config_json or ""

    return textwrap.dedent(f"""\
        from __future__ import annotations
        from concurrent.futures import ThreadPoolExecutor, as_completed
        import importlib.util, json, os, random, subprocess, sys, tempfile, traceback
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
        EVALUATION_RUNS = {evaluation_runs!r}
        _EVALUATION_WORKERS = {evaluation_workers!r}
        _SYS_CFG_JSON = {sys_cfg_json!r}
        _STAGE1_MAX_STEPS = 5000
        _SIM_TIMEOUT_SECONDS = {simulation_timeout_seconds!r}

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

        def _timeout_result(seed, max_steps, reason="timeout"):
            try:
                cfg = _make_config(seed, max_steps)
                limit = float(cfg.sim_config.max_steps)
                total_orders_limit = float(cfg.sim_config.total_orders_limit)
            except Exception:
                limit = float(max_steps if max_steps is not None else SystemConfig().sim_config.max_steps)
                total_orders_limit = float(SystemConfig().sim_config.total_orders_limit)
            return {{"finished": False,
                     "timeout": True,
                     "error": str(reason),
                     "seed": int(seed),
                     "task_success_rate": 0.0,
                     "avg_task_time": limit,
                     "throughput": 0.0,
                     "total_agv_collisions": total_orders_limit,
                     "max_steps": limit,
                     "sim_steps": limit,
                     "total_orders_limit": total_orders_limit}}

        def _run_single_child(program_path, seed, max_steps=None):
            request = {{"program_path": program_path, "seed": int(seed), "max_steps": max_steps}}
            in_file = tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8")
            out_file = tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8")
            try:
                json.dump(request, in_file)
                in_file.close()
                out_file.close()
                env = os.environ.copy()
                env["PYTHONPATH"] = os.pathsep.join(
                    [os.getcwd()] + ([env["PYTHONPATH"]] if env.get("PYTHONPATH") else [])
                )
                completed = subprocess.run(
                    [sys.executable, os.path.abspath(__file__), "--run-single-child", in_file.name, out_file.name],
                    cwd=os.getcwd(),
                    env=env,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    timeout=_SIM_TIMEOUT_SECONDS,
                )
                if completed.returncode != 0:
                    stderr = (completed.stderr or completed.stdout or "").strip()
                    return _timeout_result(seed, max_steps, stderr or f"child exited with {{completed.returncode}}")
                with open(out_file.name, "r", encoding="utf-8") as handle:
                    return json.load(handle)
            except subprocess.TimeoutExpired:
                return _timeout_result(seed, max_steps)
            except Exception as exc:
                return _timeout_result(seed, max_steps, exc)
            finally:
                for path in (in_file.name, out_file.name):
                    try:
                        os.unlink(path)
                    except OSError:
                        pass

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

        def _run_single_impl(program_path, seed, max_steps=None):
            _register_candidate(program_path)
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
                     "timeout": False,
                     "seed": int(seed),
                     "task_success_rate": float(m.get("Task Success Rate", 0.0)),
                     "avg_task_time": float(m.get("Avg Task Time", 0.0)),
                     "throughput": float(m.get("Throughput", 0.0)),
                     "total_agv_collisions": float(m.get("Total AGV Collisions", 0.0)),
                     "max_steps": float(cfg.sim_config.max_steps),
                     "sim_steps": float(ctx.clock.now()),
                     "total_orders_limit": float(cfg.sim_config.total_orders_limit)}}

        def _run_single(program_path, seed, max_steps=None):
            return _run_single_child(program_path, seed, max_steps=max_steps)

        def _child_entry():
            if len(sys.argv) != 4 or sys.argv[1] != "--run-single-child":
                raise SystemExit("usage: evaluator.py --run-single-child INPUT_JSON OUTPUT_JSON")
            with open(sys.argv[2], "r", encoding="utf-8") as handle:
                request = json.load(handle)
            try:
                result = _run_single_impl(
                    request["program_path"],
                    int(request["seed"]),
                    max_steps=request.get("max_steps"),
                )
            except Exception as exc:
                traceback.print_exc()
                result = _timeout_result(request.get("seed", 0), request.get("max_steps"), exc)
                result["timeout"] = False
            with open(sys.argv[3], "w", encoding="utf-8") as handle:
                json.dump(result, handle, ensure_ascii=False)

        def _clamp01(value):
            return min(max(float(value), 0.0), 1.0)

        def _evaluation_seeds(seeds=None):
            base = [int(s) for s in (seeds or SEEDS)]
            if not base:
                base = [0]
            if len(base) >= EVALUATION_RUNS:
                return base[:EVALUATION_RUNS]
            result = list(base)
            next_seed = result[-1] + 1
            while len(result) < EVALUATION_RUNS:
                result.append(next_seed)
                next_seed += 1
            return result

        def _default_worker_count(run_count):
            cpu_count = os.cpu_count() or 1
            return max(1, min(int(run_count), max(1, cpu_count // 2), 4))

        def _run_batch(program_path, seeds, max_steps=None):
            use_seeds = [int(s) for s in seeds]
            if not use_seeds:
                return []
            worker_count = min(
                len(use_seeds),
                _EVALUATION_WORKERS if _EVALUATION_WORKERS is not None else _default_worker_count(len(use_seeds)),
            )
            if worker_count <= 1:
                return [_run_single(program_path, seed, max_steps=max_steps) for seed in use_seeds]

            results = []
            with ThreadPoolExecutor(max_workers=worker_count) as executor:
                futures = {{
                    executor.submit(_run_single, program_path, seed, max_steps=max_steps): seed
                    for seed in use_seeds
                }}
                for future in as_completed(futures):
                    seed = futures[future]
                    try:
                        results.append(future.result())
                    except Exception as exc:
                        results.append(_timeout_result(seed, max_steps, exc))
            return sorted(results, key=lambda item: int(item.get("seed", 0)))

        def _is_successful_result(result):
            return (
                bool(result.get("finished"))
                and not bool(result.get("timeout"))
                and not bool(result.get("error"))
            )

        def _avg_successful(successful, key, default=0.0):
            values = [
                float(r[key])
                for r in successful
                if isinstance(r.get(key), (int, float)) and not isinstance(r.get(key), bool)
            ]
            return sum(values) / len(values) if values else float(default)

        def _compute_scores(results):
            n = len(results)
            if n == 0:
                return {{"combined_score": 0.0, "success_ratio": 0.0, "successful_runs": 0.0}}
            successful = [r for r in results if _is_successful_result(r)]
            success_count = len(successful)
            timed_out_runs = sum(1 for r in results if r.get("timeout"))
            error_runs = sum(1 for r in results if r.get("error") and not r.get("timeout"))
            unfinished_runs = n - success_count - timed_out_runs - error_runs
            failed_runs = n - success_count
            success_ratio = success_count / n
            timeout_rate = timed_out_runs / n
            error_rate = error_runs / n
            failure_rate = failed_runs / n

            task_success_rate = _avg_successful(successful, "task_success_rate")
            avg_task_time = _avg_successful(successful, "avg_task_time")
            throughput = _avg_successful(successful, "throughput")
            total_agv_collisions = _avg_successful(successful, "total_agv_collisions")
            max_steps = max(_avg_successful(successful or results, "max_steps", 1.0), 1.0)
            total_orders_limit = max(_avg_successful(successful or results, "total_orders_limit", 1.0), 1.0)

            success_score = _clamp01(success_ratio)
            task_time_scale = max(max_steps / 3.0, 1.0)
            throughput_scale = max(total_orders_limit / max_steps, 1e-9)
            collision_scale = max(2.0 * total_orders_limit, 1.0)

            task_time_score = 1.0 / (1.0 + max(avg_task_time, 0.0) / task_time_scale)
            throughput_score = max(throughput, 0.0) / (max(throughput, 0.0) + throughput_scale)
            collision_score = 1.0 / (1.0 + max(total_agv_collisions, 0.0) / collision_scale)
            if success_count == 0:
                task_time_score = 0.0
                throughput_score = 0.0
                collision_score = 0.0

            combined = (
                0.55 * success_score
                + 0.20 * task_time_score
                + 0.15 * throughput_score
                + 0.10 * collision_score
            )
            return {{"combined_score": combined,
                     "success_ratio": success_ratio,
                     "successful_runs": float(success_count),
                     "total_runs": float(n),
                     "task_success_rate": task_success_rate,
                     "avg_task_time": avg_task_time,
                     "throughput": throughput,
                     "total_agv_collisions": total_agv_collisions,
                     "success_score": success_score,
                     "task_time_score": task_time_score,
                     "throughput_score": throughput_score,
                     "collision_score": collision_score,
                     "timeout_rate": timeout_rate,
                     "timed_out_runs": float(timed_out_runs),
                     "error_rate": error_rate,
                     "error_runs": float(error_runs),
                     "unfinished_runs": float(max(unfinished_runs, 0)),
                     "failure_rate": failure_rate}}

        # ── cascade stage 1: quick single-seed validation ──

        def evaluate_stage1(program_path: str):
            try:
                r = _run_single(program_path, SEEDS[0], max_steps=_STAGE1_MAX_STEPS)
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
                results = _run_batch(program_path, _evaluation_seeds())
                return _compute_scores(results)
            except Exception as e:
                print(f"Evaluation failed: {{e}}")
                traceback.print_exc()
                return {{"combined_score":0.0,"error":str(e)}}

        if __name__ == "__main__":
            _child_entry()
    """)


def build_layout_evaluator_code(req: "EvolveRequest") -> str:
    seeds = list(int(s) for s in req.seeds)
    evaluation_runs = max(1, int(req.evaluation_runs))
    evaluation_workers = (
        None if req.evaluation_workers is None else max(1, int(req.evaluation_workers))
    )
    simulation_timeout_seconds = max(1.0, float(req.simulation_timeout_seconds))
    constraints_json = req.layout_constraints_json or "{}"
    sys_cfg_json = req.system_config_json or ""

    return textwrap.dedent(f"""\
        from __future__ import annotations
        from concurrent.futures import ThreadPoolExecutor, as_completed
        import importlib.util, json, os, random, subprocess, sys, tempfile, traceback
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
        EVALUATION_RUNS = {evaluation_runs!r}
        _EVALUATION_WORKERS = {evaluation_workers!r}
        CONSTRAINTS = json.loads({constraints_json!r})
        _SYS_CFG_JSON = {sys_cfg_json!r}
        _STAGE1_MAX_STEPS = 200
        _SIM_TIMEOUT_SECONDS = {simulation_timeout_seconds!r}

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

        def _timeout_result(seed, max_steps, reason="timeout"):
            try:
                cfg = _make_config(seed, "", max_steps)
                limit = float(cfg.sim_config.max_steps)
                total_orders_limit = float(cfg.sim_config.total_orders_limit)
            except Exception:
                limit = float(max_steps if max_steps is not None else SystemConfig().sim_config.max_steps)
                total_orders_limit = float(SystemConfig().sim_config.total_orders_limit)
            return {{"finished": False,
                     "timeout": True,
                     "error": str(reason),
                     "seed": int(seed),
                     "task_success_rate": 0.0,
                     "avg_task_time": limit,
                     "throughput": 0.0,
                     "total_agv_collisions": total_orders_limit,
                     "total_agv_elevator_wait_blocks": total_orders_limit,
                     "max_steps": limit,
                     "sim_steps": limit,
                     "total_orders_limit": total_orders_limit}}

        def _run_single_child(seed, map_data: Dict[str, Any], max_steps=None, collect_artifacts: bool = False):
            request = {{
                "seed": int(seed),
                "map_data": map_data,
                "max_steps": max_steps,
                "collect_artifacts": bool(collect_artifacts),
            }}
            in_file = tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8")
            out_file = tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8")
            try:
                json.dump(request, in_file, ensure_ascii=False)
                in_file.close()
                out_file.close()
                env = os.environ.copy()
                env["PYTHONPATH"] = os.pathsep.join(
                    [os.getcwd()] + ([env["PYTHONPATH"]] if env.get("PYTHONPATH") else [])
                )
                completed = subprocess.run(
                    [sys.executable, os.path.abspath(__file__), "--run-single-child", in_file.name, out_file.name],
                    cwd=os.getcwd(),
                    env=env,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    timeout=_SIM_TIMEOUT_SECONDS,
                )
                if completed.returncode != 0:
                    stderr = (completed.stderr or completed.stdout or "").strip()
                    return _timeout_result(seed, max_steps, stderr or f"child exited with {{completed.returncode}}")
                with open(out_file.name, "r", encoding="utf-8") as handle:
                    return json.load(handle)
            except subprocess.TimeoutExpired:
                return _timeout_result(seed, max_steps)
            except Exception as exc:
                return _timeout_result(seed, max_steps, exc)
            finally:
                for path in (in_file.name, out_file.name):
                    try:
                        os.unlink(path)
                    except OSError:
                        pass

        def _observe_heatmap(ctx, heatmap: Dict[str, Dict[str, int]]) -> None:
            for agv_id, pos in ctx.agv_manager.get_all_current_pos().items():
                floor_id = str(ctx.agv_manager.get_agv_floor(agv_id))
                key = f"{{int(pos[0])}},{{int(pos[1])}}"
                heatmap.setdefault(floor_id, {{}})[key] = heatmap.setdefault(floor_id, {{}}).get(key, 0) + 1

        def _run_single_impl(seed, map_data: Dict[str, Any], max_steps=None, collect_artifacts: bool = False):
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
                         "timeout": False,
                         "seed": int(seed),
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

        def _run_single(seed, map_data: Dict[str, Any], max_steps=None, collect_artifacts: bool = False):
            return _run_single_child(
                seed,
                map_data,
                max_steps=max_steps,
                collect_artifacts=collect_artifacts,
            )

        def _child_entry():
            if len(sys.argv) != 4 or sys.argv[1] != "--run-single-child":
                raise SystemExit("usage: evaluator.py --run-single-child INPUT_JSON OUTPUT_JSON")
            with open(sys.argv[2], "r", encoding="utf-8") as handle:
                request = json.load(handle)
            try:
                result = _run_single_impl(
                    int(request["seed"]),
                    request["map_data"],
                    max_steps=request.get("max_steps"),
                    collect_artifacts=bool(request.get("collect_artifacts")),
                )
            except Exception as exc:
                traceback.print_exc()
                result = _timeout_result(request.get("seed", 0), request.get("max_steps"), exc)
                result["timeout"] = False
            with open(sys.argv[3], "w", encoding="utf-8") as handle:
                json.dump(result, handle, ensure_ascii=False)

        def _clamp01(value):
            return min(max(float(value), 0.0), 1.0)

        def _evaluation_seeds(seeds=None):
            base = [int(s) for s in (seeds or SEEDS)]
            if not base:
                base = [0]
            if len(base) >= EVALUATION_RUNS:
                return base[:EVALUATION_RUNS]
            result = list(base)
            next_seed = result[-1] + 1
            while len(result) < EVALUATION_RUNS:
                result.append(next_seed)
                next_seed += 1
            return result

        def _default_worker_count(run_count):
            cpu_count = os.cpu_count() or 1
            return max(1, min(int(run_count), max(1, cpu_count // 2), 4))

        def _run_batch(seeds, map_data: Dict[str, Any], max_steps=None, collect_artifacts: bool = False):
            use_seeds = [int(s) for s in seeds]
            if not use_seeds:
                return []
            worker_count = min(
                len(use_seeds),
                _EVALUATION_WORKERS if _EVALUATION_WORKERS is not None else _default_worker_count(len(use_seeds)),
            )
            if worker_count <= 1:
                return [
                    _run_single(
                        seed,
                        map_data,
                        max_steps=max_steps,
                        collect_artifacts=(collect_artifacts and idx == 0),
                    )
                    for idx, seed in enumerate(use_seeds)
                ]

            results = []
            with ThreadPoolExecutor(max_workers=worker_count) as executor:
                futures = {{
                    executor.submit(
                        _run_single,
                        seed,
                        map_data,
                        max_steps=max_steps,
                        collect_artifacts=(collect_artifacts and idx == 0),
                    ): seed
                    for idx, seed in enumerate(use_seeds)
                }}
                for future in as_completed(futures):
                    seed = futures[future]
                    try:
                        results.append(future.result())
                    except Exception as exc:
                        results.append(_timeout_result(seed, max_steps, exc))
            return sorted(results, key=lambda item: int(item.get("seed", 0)))

        def _is_successful_result(result):
            return (
                bool(result.get("finished"))
                and not bool(result.get("timeout"))
                and not bool(result.get("error"))
            )

        def _avg_successful(successful, key, default=0.0):
            values = [
                float(r[key])
                for r in successful
                if isinstance(r.get(key), (int, float)) and not isinstance(r.get(key), bool)
            ]
            return sum(values) / len(values) if values else float(default)

        def _compute_scores(results, validation):
            n = len(results)
            if n == 0:
                return {{"combined_score": 0.0, "success_ratio": 0.0, "successful_runs": 0.0}}
            successful = [r for r in results if _is_successful_result(r)]
            success_count = len(successful)
            timed_out_runs = sum(1 for r in results if r.get("timeout"))
            error_runs = sum(1 for r in results if r.get("error") and not r.get("timeout"))
            unfinished_runs = n - success_count - timed_out_runs - error_runs
            failed_runs = n - success_count
            success_ratio = success_count / n
            timeout_rate = timed_out_runs / n
            error_rate = error_runs / n
            failure_rate = failed_runs / n
            task_success_rate = _avg_successful(successful, "task_success_rate")
            avg_task_time = _avg_successful(successful, "avg_task_time")
            throughput = _avg_successful(successful, "throughput")
            total_agv_collisions = _avg_successful(successful, "total_agv_collisions")
            total_agv_elevator_wait_blocks = _avg_successful(successful, "total_agv_elevator_wait_blocks")
            max_steps = max(_avg_successful(successful or results, "max_steps", 1.0), 1.0)
            total_orders_limit = max(_avg_successful(successful or results, "total_orders_limit", 1.0), 1.0)

            validity_score = 1.0
            reachability_score = _clamp01(validation.get("reachability_score", 1.0))
            success_score = _clamp01(success_ratio)
            task_time_scale = max(max_steps / 3.0, 1.0)
            throughput_scale = max(total_orders_limit / max_steps, 1e-9)
            congestion_events = max(total_agv_collisions, 0.0) + max(total_agv_elevator_wait_blocks, 0.0)
            congestion_scale = max(2.0 * total_orders_limit, 1.0)

            task_time_score = 1.0 / (1.0 + max(avg_task_time, 0.0) / task_time_scale)
            throughput_score = max(throughput, 0.0) / (max(throughput, 0.0) + throughput_scale)
            congestion_score = 1.0 / (1.0 + congestion_events / congestion_scale)
            if success_count == 0:
                task_time_score = 0.0
                throughput_score = 0.0
                congestion_score = 0.0

            combined = (
                0.50 * success_score
                + 0.15 * task_time_score
                + 0.10 * throughput_score
                + 0.10 * congestion_score
                + 0.10 * reachability_score
                + 0.05 * validity_score
            )
            return {{"combined_score": combined,
                     "validity_score": validity_score,
                     "reachability_score": reachability_score,
                     "success_ratio": success_ratio,
                     "successful_runs": float(success_count),
                     "total_runs": float(n),
                     "task_success_rate": task_success_rate,
                     "avg_task_time": avg_task_time,
                     "throughput": throughput,
                     "total_agv_collisions": total_agv_collisions,
                     "total_agv_elevator_wait_blocks": total_agv_elevator_wait_blocks,
                     "success_score": success_score,
                     "task_time_score": task_time_score,
                     "throughput_score": throughput_score,
                     "congestion_score": congestion_score,
                     "timeout_rate": timeout_rate,
                     "timed_out_runs": float(timed_out_runs),
                     "error_rate": error_rate,
                     "error_runs": float(error_runs),
                     "unfinished_runs": float(max(unfinished_runs, 0)),
                     "failure_rate": failure_rate}}

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
            results = _run_batch(
                _evaluation_seeds(seeds),
                map_data,
                max_steps=max_steps,
                collect_artifacts=collect_artifacts,
            )
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

        if __name__ == "__main__":
            _child_entry()
    """)
