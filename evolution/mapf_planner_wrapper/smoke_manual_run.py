from __future__ import annotations

import json
import subprocess
import sys
import time
from pathlib import Path


def _noop_diff() -> str:
    search_block = (
        "    scored.sort(reverse=True)\n"
        "    return [agv_id for _, agv_id in scored]"
    )
    return (
        "<<<<<<< SEARCH\n"
        f"{search_block}\n"
        "=======\n"
        f"{search_block}\n"
        ">>>>>>> REPLACE"
    )


def main() -> int:
    repo_root = Path(__file__).resolve().parents[2]
    output_dir = repo_root / "evolution" / "mapf_planner_wrapper" / "openevolve_output"
    queue_dir = output_dir / "manual_tasks_queue"

    cmd = [
        sys.executable,
        "openevolve/openevolve-run.py",
        "evolution/mapf_planner_wrapper/initial_program.py",
        "evolution/mapf_planner_wrapper/evaluator.py",
        "--config",
        "evolution/mapf_planner_wrapper/config.yaml",
        "--output",
        "evolution/mapf_planner_wrapper/openevolve_output",
        "--iterations",
        "1",
    ]

    proc = subprocess.Popen(cmd, cwd=str(repo_root))
    answered = set()

    try:
        while proc.poll() is None:
            if queue_dir.exists():
                for task_file in queue_dir.glob("*.json"):
                    if task_file.name.endswith(".answer.json"):
                        continue
                    answer_file = task_file.with_name(task_file.stem + ".answer.json")
                    if answer_file.exists() or task_file.name in answered:
                        continue

                    payload = {"answer": _noop_diff()}
                    answer_file.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
                    answered.add(task_file.name)

            time.sleep(0.5)
    finally:
        return_code = proc.wait()

    print(f"manual smoke run exit_code={return_code}, answered_tasks={len(answered)}")
    return return_code


if __name__ == "__main__":
    raise SystemExit(main())
