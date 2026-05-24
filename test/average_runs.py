"""Run multiple simulation episodes with hard per-run timeouts.

python -m test.average_runs --runs 50 --workers 4 --timeout 30
"""
from __future__ import annotations

import argparse
import multiprocessing as mp
import os
import time
from queue import Empty
from typing import Dict, List, Optional

from .single_run import run_single_episode


DEFAULT_RUNS = 20
DEFAULT_TIMEOUT_SECONDS = 30.0
POLL_INTERVAL_SECONDS = 0.1
COMMON_NUMERIC_METRICS = (
    "Tasks Completed",
    "Task Success Rate",
    "Total Task Time",
    "Avg Task Time",
    "Throughput",
    "Total AGV Collisions",
    "Total AGV Elevator Wait Blocks",
    "Scheduler Calls",
    "Scheduler Total Time",
    "Scheduler Avg Time",
    "Planner Calls",
    "Planner Total Time",
    "Planner Avg Time",
    "Decision Total Time",
    "Sim Steps",
    "sim_steps",
    "elapsed_seconds",
)


def _base_failed_result(
    seed: int,
    *,
    timeout: bool,
    error: str,
    elapsed_seconds: float,
) -> Dict:
    result = {key: 0.0 for key in COMMON_NUMERIC_METRICS}
    result.update(
        {
            "seed": seed,
            "finished": False,
            "timeout": timeout,
            "error": error,
            "elapsed_seconds": elapsed_seconds,
        }
    )
    return result


def _episode_worker(seed: int, result_queue) -> None:
    start_time = time.perf_counter()
    try:
        result = run_single_episode(seed=seed)
    except Exception as exc:
        result = _base_failed_result(
            seed,
            timeout=False,
            error=f"{type(exc).__name__}: {exc}",
            elapsed_seconds=time.perf_counter() - start_time,
        )
    result_queue.put(result)


def _start_episode(ctx, seed: int) -> Dict:
    result_queue = ctx.Queue(maxsize=1)
    process = ctx.Process(target=_episode_worker, args=(seed, result_queue))
    process.start()
    return {
        "seed": seed,
        "process": process,
        "queue": result_queue,
        "start_time": time.perf_counter(),
    }


def _stop_process(process) -> None:
    process.terminate()
    process.join(timeout=1.0)
    if process.is_alive():
        process.kill()
        process.join(timeout=1.0)


def _collect_finished_episode(task: Dict, timeout_seconds: Optional[float]) -> Optional[Dict]:
    process = task["process"]
    elapsed = time.perf_counter() - task["start_time"]

    if process.is_alive():
        if timeout_seconds is None or elapsed < timeout_seconds:
            return None
        _stop_process(process)
        return _base_failed_result(
            task["seed"],
            timeout=True,
            error="wall_time_limit_exceeded",
            elapsed_seconds=elapsed,
        )

    process.join()
    try:
        result = task["queue"].get(timeout=1.0)
    except Empty:
        result = _base_failed_result(
            task["seed"],
            timeout=False,
            error=f"worker exited without result (exitcode={process.exitcode})",
            elapsed_seconds=elapsed,
        )
    result.setdefault("seed", task["seed"])
    result.setdefault("finished", False)
    result.setdefault("timeout", False)
    result.setdefault("error", "")
    result.setdefault("elapsed_seconds", elapsed)
    return result


def run_parallel_episodes(
    num_runs: int,
    base_seed: int,
    workers: int,
    timeout_seconds: Optional[float],
) -> List[Dict]:
    """Run episodes concurrently and enforce a hard timeout per episode."""
    if num_runs <= 0:
        return []
    worker_count = max(1, min(workers, num_runs))
    ctx = mp.get_context("spawn")
    pending_seeds = [base_seed + i for i in range(num_runs)]
    running: List[Dict] = []
    results: List[Dict] = []

    while pending_seeds or running:
        while pending_seeds and len(running) < worker_count:
            seed = pending_seeds.pop(0)
            print(f"Starting episode {len(results) + len(running) + 1}/{num_runs} with seed {seed}")
            running.append(_start_episode(ctx, seed))

        still_running: List[Dict] = []
        for task in running:
            result = _collect_finished_episode(task, timeout_seconds)
            if result is None:
                still_running.append(task)
                continue
            results.append(result)
            status = "timeout" if result.get("timeout") else "done"
            if result.get("error") and not result.get("timeout"):
                status = "error"
            print(
                f"Episode seed={result.get('seed')} {status} "
                f"finished={result.get('finished')} "
                f"elapsed={result.get('elapsed_seconds', 0.0):.2f}s"
            )
        running = still_running

        if running:
            time.sleep(POLL_INTERVAL_SECONDS)

    return sorted(results, key=lambda item: item.get("seed", 0))


def _is_successful_result(result: Dict) -> bool:
    return (
        bool(result.get("finished"))
        and not bool(result.get("timeout"))
        and not bool(result.get("error"))
    )


def summarize_successful_results(results: List[Dict]) -> Dict:
    successful = [result for result in results if _is_successful_result(result)]
    if not successful:
        return {}

    excluded_keys = {"seed"}
    numeric_keys = sorted(
        {
            key
            for result in successful
            for key, value in result.items()
            if isinstance(value, (int, float))
            and not isinstance(value, bool)
            and key not in excluded_keys
        }
    )
    summary = {}
    for key in numeric_keys:
        values = [
            result[key]
            for result in successful
            if isinstance(result.get(key), (int, float))
            and not isinstance(result.get(key), bool)
        ]
        if values:
            summary[key] = sum(values) / len(values)
    return summary


def print_summary(results: List[Dict]) -> None:
    total = len(results)
    success_count = sum(1 for result in results if _is_successful_result(result))
    timeout_count = sum(1 for result in results if result.get("timeout"))
    error_count = sum(
        1
        for result in results
        if result.get("error") and not result.get("timeout")
    )
    unfinished_count = total - success_count - timeout_count
    success_ratio = success_count / total if total else 0.0

    print("\nRun Summary:")
    print(f"Total runs: {total}")
    print(f"Successful runs: {success_count}")
    print(f"Timed out runs: {timeout_count}")
    print(f"Unfinished or failed runs: {unfinished_count}")
    print(f"Error runs: {error_count}")
    print(f"Success ratio: {success_ratio:.2%}")

    averages = summarize_successful_results(results)
    print("\nAverage Metrics (successful runs only):")
    if not averages:
        print("No successful runs to average.")
        return
    for key, value in averages.items():
        print(f"{key}: {value:.6g}")


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--runs", type=int, default=DEFAULT_RUNS)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--workers", type=int, default=None)
    parser.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT_SECONDS)
    return parser.parse_args()


def main():
    args = parse_args()
    workers = args.workers
    if workers is None:
        workers = min(os.cpu_count() or 1, max(args.runs, 1))
    timeout_seconds = args.timeout if args.timeout > 0 else None

    print("Batch simulation config:")
    print(f"Runs: {args.runs}")
    print(f"Base seed: {args.seed}")
    print(f"Workers: {workers}")
    print(f"Timeout per run: {timeout_seconds if timeout_seconds is not None else 'disabled'}s")

    results = run_parallel_episodes(
        num_runs=args.runs,
        base_seed=args.seed,
        workers=workers,
        timeout_seconds=timeout_seconds,
    )
    print_summary(results)


if __name__ == "__main__":
    main()