"""Core evolution pipeline: build artifacts and invoke OpenEvolve."""
from __future__ import annotations

import ast
import json
import os
import shlex
import subprocess
import sys
import uuid
from collections import deque
from dataclasses import asdict, dataclass
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Dict, Optional, Sequence, Union

from mapf_agent.paths import output_dir

CodeSource = Union[str, Path]
_PKG_DIR = Path(__file__).resolve().parent
_REPO_ROOT = _PKG_DIR.parent.parent


class OptimizationTarget(str, Enum):
    PLANNER = "planner"
    SCHEDULER = "scheduler"
    BOTH = "both"
    LAYOUT = "layout"


@dataclass
class EvolveRequest:
    target: OptimizationTarget
    planner_source: Optional[CodeSource] = None
    scheduler_source: Optional[CodeSource] = None
    layout_source: Optional[CodeSource] = None
    layout_constraints: Optional[CodeSource] = None
    config_path: Optional[CodeSource] = None
    iterations: Optional[int] = None
    output_root: Optional[CodeSource] = None
    seeds: Sequence[int] = (42, 43, 44)
    system_config_json: Optional[str] = None
    layout_constraints_json: Optional[str] = None
    # CLI entry: ``sys.argv``; programmatic callers leave None (manifest marks non-cli)
    launch_argv: Optional[Sequence[str]] = None


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


def _base_name(base: ast.expr) -> str:
    if isinstance(base, ast.Name):
        return base.id
    if isinstance(base, ast.Attribute):
        return base.attr
    if isinstance(base, ast.Subscript):
        return _base_name(base.value)
    return ""


def _node_start_lineno(node: ast.AST) -> int:
    decorators = getattr(node, "decorator_list", None) or []
    if decorators:
        return min(getattr(d, "lineno", getattr(node, "lineno", 1)) for d in decorators)
    return getattr(node, "lineno", 1)


def _find_candidate_class(tree: ast.Module, expected_base: str) -> Optional[ast.ClassDef]:
    classes = [n for n in tree.body if isinstance(n, ast.ClassDef)]
    for cls in classes:
        if any(_base_name(base) == expected_base for base in cls.bases):
            return cls
    return classes[0] if classes else None


def _first_method_after_init(cls: ast.ClassDef) -> Optional[ast.AST]:
    init_node: Optional[ast.AST] = None
    for node in cls.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == "__init__":
            init_node = node
            break

    if init_node is not None:
        init_end = getattr(init_node, "end_lineno", init_node.lineno)
        candidates = [
            node
            for node in cls.body
            if _node_start_lineno(node) > init_end
        ]
        return min(candidates, key=_node_start_lineno) if candidates else None

    methods = [
        node
        for node in cls.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name != "__init__"
    ]
    return min(methods, key=_node_start_lineno) if methods else None


def _render_evolvable_source(label: str, code: str, expected_base: str) -> str:
    """Render one algorithm source with a class-local EVOLVE-BLOCK.

    Imports, constants, class declaration, and ``__init__`` stay outside the
    block.  The remaining class body is evolved in place.  If parsing fails,
    the whole source is still made evolvable, but as an isolated top-level
    block so multiple components cannot collapse into the same class scope.
    """
    clean = _strip_markers(code)
    try:
        tree = ast.parse(clean)
    except SyntaxError:
        return f"# -------- {label} Candidate --------\n# EVOLVE-BLOCK-START\n{clean}\n# EVOLVE-BLOCK-END"

    cls = _find_candidate_class(tree, expected_base)
    if cls is None or getattr(cls, "end_lineno", None) is None:
        return f"# -------- {label} Candidate --------\n# EVOLVE-BLOCK-START\n{clean}\n# EVOLVE-BLOCK-END"

    lines = clean.splitlines()
    split_node = _first_method_after_init(cls)
    split_idx = (_node_start_lineno(split_node) - 1) if split_node is not None else cls.end_lineno
    class_end_idx = cls.end_lineno

    before = "\n".join(lines[:split_idx]).rstrip()
    evolvable = "\n".join(lines[split_idx:class_end_idx]).rstrip()
    after = "\n".join(lines[class_end_idx:]).strip()

    rendered = [f"# -------- {label} candidate --------", before]
    rendered.append("    # EVOLVE-BLOCK-START")
    if evolvable:
        rendered.append(evolvable)
    else:
        rendered.append("    pass")
    rendered.append("    # EVOLVE-BLOCK-END")
    if after:
        rendered.append(after)
    return "\n".join(part for part in rendered if part != "")


def _build_initial_program(
    target: OptimizationTarget,
    planner_code: str,
    scheduler_code: str,
    layout_code: str = "",
) -> str:
    """Build the initial_program.py that OpenEvolve will evolve.

    Imports and class scaffolding (including ``__init__``) are placed **outside**
    the EVOLVE-BLOCK so the LLM cannot accidentally break them.  Only the core
    algorithm methods live inside the block.
    """
    if target == OptimizationTarget.LAYOUT:
        from mapf_agent.evolve.layout import build_layout_initial_program

        return build_layout_initial_program(layout_code)

    sources = []
    if target in (OptimizationTarget.PLANNER, OptimizationTarget.BOTH):
        sources.append(("Planner", planner_code, "BasePlanner"))
    if target in (OptimizationTarget.SCHEDULER, OptimizationTarget.BOTH):
        sources.append(("Scheduler", scheduler_code, "BaseScheduler"))

    program = "\n\n".join(
        _render_evolvable_source(label, code, expected_base)
        for label, code, expected_base in sources
    ) + "\n"
    compile(program, "initial_program.py", "exec")
    return program


def _read_repo_file(relative_path: str) -> str:
    return (_REPO_ROOT / relative_path).read_text(encoding="utf-8").strip()


def _interface_contracts(target: OptimizationTarget) -> str:
    if target == OptimizationTarget.LAYOUT:
        return (
            "### Layout generator interface\n"
            "```python\n"
            "def generate_map(constraints: dict) -> dict:\n"
            "    \"\"\"Return a WareRover map JSON-compatible dictionary.\"\"\"\n"
            "```\n\n"
            "The evaluator calls only `generate_map(constraints)`. Keep this function name and "
            "signature stable. Helper functions are allowed, but the returned object must satisfy "
            "`mapf_agent/schema/map_schema.json` and the normalized layout constraints."
        )

    parts = []
    if target in (OptimizationTarget.PLANNER, OptimizationTarget.BOTH):
        parts.append(
            "### Planner base interface\n"
            "```python\n"
            f"{_read_repo_file('planner/base_planner.py')}\n"
            "```"
        )
    if target in (OptimizationTarget.SCHEDULER, OptimizationTarget.BOTH):
        parts.append(
            "### Scheduler base interface\n"
            "```python\n"
            f"{_read_repo_file('scheduler/base_scheduler.py')}\n"
            "```"
        )
    return "\n\n".join(parts)


def _target_guidance(target: OptimizationTarget) -> str:
    if target == OptimizationTarget.PLANNER:
        return (
            "Optimize the planner implementation only. Keep exactly one concrete BasePlanner "
            "subclass in the program and focus on path quality, conflict avoidance, deadlock "
            "reduction, and planner runtime."
        )
    if target == OptimizationTarget.SCHEDULER:
        return (
            "Optimize the scheduler implementation only. Keep exactly one concrete BaseScheduler "
            "subclass in the program and focus on assigning feasible orders to idle AGVs, reducing "
            "travel, improving completion rate, and handling cross-floor tasks."
        )
    if target == OptimizationTarget.LAYOUT:
        return (
            "Optimize a Python map layout generator. The candidate program must expose "
            "`generate_map(constraints: dict) -> dict`. Use loops and helper functions to place "
            "boxes, receivers, wait zones, AGVs, elevators, and obstacles so the generated map "
            "satisfies all hard constraints and improves simulation metrics with the fixed planner "
            "and scheduler configured by the evaluator."
        )
    return (
        "Optimize the planner and scheduler together. Keep one concrete BasePlanner subclass and "
        "one concrete BaseScheduler subclass as separate classes. Improve their interaction without "
        "merging classes or changing either public method signature."
    )


def _simulation_context_notes() -> str:
    notes_path = _PKG_DIR / "simulation_context_notes.md"
    notes = notes_path.read_text(encoding="utf-8").strip()
    if not notes:
        raise ValueError(f"Simulation context notes file is empty: {notes_path}")
    return notes


def _indent_block(text: str, spaces: int = 4) -> str:
    prefix = " " * spaces
    return "\n".join(prefix + line if line else prefix for line in text.splitlines())


def _load_default_config(target: OptimizationTarget) -> str:
    tpl_path = _PKG_DIR / "default_config.yaml"
    tpl = tpl_path.read_text(encoding="utf-8")
    tpl = tpl.replace("{target}", target.value)
    tpl = tpl.replace("    {target_guidance}", _indent_block(_target_guidance(target)))
    tpl = tpl.replace("    {interface_contracts}", _indent_block(_interface_contracts(target)))
    tpl = tpl.replace(
        "    {simulation_context_notes}",
        _indent_block(_simulation_context_notes()),
    )
    return tpl


def _run_openevolve_worker(
    init_path: Path,
    eval_path: Path,
    cfg_path: Path,
    out_dir: Path,
    result_path: Path,
    iterations: Optional[int],
) -> Dict[str, Any]:
    env = os.environ.copy()
    pythonpath = [str(_REPO_ROOT), str(_REPO_ROOT / "openevolve")]
    if env.get("PYTHONPATH"):
        pythonpath.append(env["PYTHONPATH"])
    env["PYTHONPATH"] = os.pathsep.join(pythonpath)
    env.setdefault("PYTHONUTF8", "1")

    cmd = [
        sys.executable,
        "-m",
        "mapf_agent.evolve.worker",
        "--initial-program",
        str(init_path),
        "--evaluator",
        str(eval_path),
        "--config",
        str(cfg_path),
        "--output-dir",
        str(out_dir),
        "--result-json",
        str(result_path),
    ]
    if iterations is not None:
        cmd.extend(["--iterations", str(iterations)])

    print("[算法优化] OpenEvolve 子进程已启动")
    process = subprocess.Popen(
        cmd,
        cwd=str(_REPO_ROOT),
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
        bufsize=1,
    )

    last_lines: deque[str] = deque(maxlen=40)
    if process.stdout is not None:
        for raw_line in process.stdout:
            line = raw_line.rstrip("\r\n")
            if line:
                print(line)
                last_lines.append(line)

    return_code = process.wait()
    if not result_path.exists():
        details = "\n".join(last_lines)
        raise RuntimeError(
            f"OpenEvolve 子进程未生成结果文件，退出码: {return_code}"
            + (f"\n最近日志:\n{details}" if details else "")
        )

    payload = json.loads(result_path.read_text(encoding="utf-8"))
    if return_code != 0 or payload.get("error"):
        message = payload.get("error") or f"退出码: {return_code}"
        traceback_text = payload.get("traceback", "")
        raise RuntimeError(
            f"OpenEvolve 子进程失败: {message}"
            + (f"\n{traceback_text}" if traceback_text else "")
        )

    return payload


def _write_run_manifest(run_dir: Path, launch_argv: Optional[Sequence[str]]) -> None:
    from config.settings import SystemConfig

    invocation: Dict[str, Any]
    if launch_argv is None:
        invocation = {"source": "non_cli"}
    else:
        argv_list = list(launch_argv)
        invocation = {
            "argv": argv_list,
            "command_line": shlex.join(argv_list),
            "python_executable": sys.executable,
        }
    payload = {"invocation": invocation, "settings": asdict(SystemConfig())}
    (run_dir / "run_manifest.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, default=str) + "\n",
        encoding="utf-8",
    )


# ---------------------------------------------------------------------------
# Public entry
# ---------------------------------------------------------------------------

def run_evolution(request: EvolveRequest) -> EvolveResult:
    target = request.target

    if target in (OptimizationTarget.PLANNER, OptimizationTarget.BOTH) and not request.planner_source:
        raise ValueError("planner_source is required for planner/both optimization")
    if target in (OptimizationTarget.SCHEDULER, OptimizationTarget.BOTH) and not request.scheduler_source:
        raise ValueError("scheduler_source is required for scheduler/both optimization")
    if target == OptimizationTarget.LAYOUT and not request.layout_constraints:
        raise ValueError("layout_constraints is required for layout optimization")

    planner_code = _read_source(request.planner_source, "planner") if request.planner_source else ""
    scheduler_code = _read_source(request.scheduler_source, "scheduler") if request.scheduler_source else ""
    layout_code = _read_source(request.layout_source, "layout") if request.layout_source else ""

    if target == OptimizationTarget.LAYOUT:
        from mapf_agent.evolve.layout import load_layout_constraints

        request.layout_constraints_json = json.dumps(
            load_layout_constraints(request.layout_constraints),
            ensure_ascii=False,
            sort_keys=True,
        )

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    run_id = f"evolve_{target.value}_{ts}_{uuid.uuid4().hex[:6]}"
    root = Path(request.output_root) if request.output_root else output_dir("evolve")
    run_dir = root / run_id
    run_dir.mkdir(parents=True, exist_ok=True)

    init_path = run_dir / "initial_program.py"
    eval_path = run_dir / "evaluator.py"
    cfg_path = run_dir / "config.yaml"
    out_dir = run_dir / "openevolve_output"
    result_path = run_dir / "openevolve_result.json"

    init_path.write_text(
        _build_initial_program(target, planner_code, scheduler_code, layout_code),
        encoding="utf-8",
    )

    from mapf_agent.evolve.evaluator_template import build_evaluator_code
    eval_path.write_text(build_evaluator_code(request, target), encoding="utf-8")

    if request.config_path:
        cfg_text = _read_source(request.config_path, "config")
    else:
        cfg_text = _load_default_config(target)
    cfg_path.write_text(cfg_text, encoding="utf-8")
    _write_run_manifest(run_dir, request.launch_argv)

    from utils.api_key import load_api_key
    os.environ["OPENAI_API_KEY"] = load_api_key()

    oe_src = _REPO_ROOT / "openevolve"
    if str(_REPO_ROOT) not in sys.path:
        sys.path.insert(0, str(_REPO_ROOT))
    if str(oe_src) not in sys.path:
        sys.path.insert(0, str(oe_src))

    evo = _run_openevolve_worker(
        init_path=init_path,
        eval_path=eval_path,
        cfg_path=cfg_path,
        out_dir=out_dir,
        result_path=result_path,
        iterations=request.iterations,
    )

    return EvolveResult(
        run_dir=str(run_dir),
        output_dir=evo.get("output_dir"),
        best_score=float(evo.get("best_score", 0.0)),
        best_metrics=dict(evo.get("best_metrics") or {}),
        best_code=evo.get("best_code") or "",
    )
