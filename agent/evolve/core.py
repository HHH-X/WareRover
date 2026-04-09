"""Core evolution pipeline: build artifacts and invoke OpenEvolve."""
from __future__ import annotations

import re
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Dict, Optional, Sequence, Tuple, Union

CodeSource = Union[str, Path]
_PKG_DIR = Path(__file__).resolve().parent
_REPO_ROOT = _PKG_DIR.parent.parent


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
    system_config_json: Optional[str] = None


@dataclass
class EvolveResult:
    run_dir: str
    output_dir: Optional[str]
    best_score: float
    best_metrics: Dict[str, Any]
    best_code: str


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

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


def _split_scaffold(code: str) -> Tuple[str, str]:
    """Split algorithm source into (scaffold, body).

    *scaffold* = imports + module-level constants + class definition + ``__init__``
    *body*     = remaining methods that should be placed inside EVOLVE-BLOCK

    Falls back to ("", full_code) when the structure cannot be parsed reliably.
    """
    clean = _strip_markers(code)
    lines = clean.split("\n")

    # Locate the class definition
    class_idx: Optional[int] = None
    for i, line in enumerate(lines):
        if re.match(r"^class\s+\w+", line):
            class_idx = i
            break
    if class_idx is None:
        return "", clean

    # Walk past __init__ to find the first non-__init__ method
    seen_init = False
    split_idx: Optional[int] = None
    for i in range(class_idx + 1, len(lines)):
        if re.match(r"^\s{4}def\s+__init__\s*\(", lines[i]):
            seen_init = True
            continue
        if seen_init and re.match(r"^\s{4}def\s+(?!__init__)\w+", lines[i]):
            split_idx = i
            break

    if split_idx is None:
        return "", clean

    scaffold = "\n".join(lines[:split_idx])
    body = "\n".join(lines[split_idx:])
    return scaffold, body


def _build_initial_program(
    target: OptimizationTarget,
    planner_code: str,
    scheduler_code: str,
) -> str:
    """Build the initial_program.py that OpenEvolve will evolve.

    Imports and class scaffolding (including ``__init__``) are placed **outside**
    the EVOLVE-BLOCK so the LLM cannot accidentally break them.  Only the core
    algorithm methods live inside the block.
    """
    sources = []
    if target in (OptimizationTarget.PLANNER, OptimizationTarget.BOTH):
        sources.append(("Planner", planner_code))
    if target in (OptimizationTarget.SCHEDULER, OptimizationTarget.BOTH):
        sources.append(("Scheduler", scheduler_code))

    scaffolds = []
    bodies = []
    for label, code in sources:
        scaffold, body = _split_scaffold(code)
        if scaffold:
            scaffolds.append(f"# -------- {label} scaffold --------\n{scaffold}")
            bodies.append(f"    # -------- {label} methods --------\n{body}")
        else:
            bodies.append(f"# -------- {label} Candidate --------\n{_strip_markers(code)}")

    parts = []
    if scaffolds:
        parts.append("\n\n".join(scaffolds))
    parts.append("")
    parts.append("    # EVOLVE-BLOCK-START")
    parts.extend(bodies)
    parts.append("    # EVOLVE-BLOCK-END")
    return "\n\n".join(parts) + "\n"


def _load_default_config(target: OptimizationTarget) -> str:
    tpl_path = _PKG_DIR / "default_config.yaml"
    tpl = tpl_path.read_text(encoding="utf-8")
    return tpl.replace("{target}", target.value)


# ---------------------------------------------------------------------------
# Public entry
# ---------------------------------------------------------------------------

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

    init_path.write_text(
        _build_initial_program(target, planner_code, scheduler_code),
        encoding="utf-8",
    )

    from agent.evolve.evaluator_template import build_evaluator_code
    eval_path.write_text(build_evaluator_code(request, target), encoding="utf-8")

    if request.config_path:
        cfg_text = _read_source(request.config_path, "config")
    else:
        cfg_text = _load_default_config(target)
    cfg_path.write_text(cfg_text, encoding="utf-8")

    import os
    import sys

    from utils.api_key import load_api_key
    os.environ["OPENAI_API_KEY"] = load_api_key()

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
