"""Subprocess entry point for running OpenEvolve from the web agent.

OpenEvolve registers process signal handlers, which must happen on a Python
main thread.  The web UI runs agent work in a background thread, so the actual
evolution is isolated here in a fresh process.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import traceback
from pathlib import Path
from typing import Any


_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
_OPENEOLVE_SRC = _REPO_ROOT / "openevolve"


def _ensure_import_paths() -> None:
    for path in (_REPO_ROOT, _OPENEOLVE_SRC):
        path_str = str(path)
        if path_str not in sys.path:
            sys.path.insert(0, path_str)


def _write_result(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run OpenEvolve in an isolated subprocess.")
    parser.add_argument("--initial-program", required=True)
    parser.add_argument("--evaluator", required=True)
    parser.add_argument("--config", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--result-json", required=True)
    parser.add_argument("--iterations", type=int)
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    result_path = Path(args.result_json)

    try:
        _ensure_import_paths()
        from openevolve.api import run_evolution as oe_run

        evo = oe_run(
            initial_program=args.initial_program,
            evaluator=args.evaluator,
            config=args.config,
            iterations=args.iterations,
            output_dir=args.output_dir,
            cleanup=False,
        )

        _write_result(
            result_path,
            {
                "output_dir": evo.output_dir,
                "best_score": float(evo.best_score),
                "best_metrics": dict(evo.metrics or {}),
                "best_code": evo.best_code or "",
            },
        )
        return 0
    except Exception as exc:
        traceback.print_exc()
        _write_result(
            result_path,
            {
                "error": str(exc),
                "traceback": traceback.format_exc(),
            },
        )
        return 1


if __name__ == "__main__":
    os.environ.setdefault("PYTHONUTF8", "1")
    raise SystemExit(main())
