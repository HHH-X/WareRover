"""Resolve an algorithm source from user description to a concrete file path.

Supports three resolution modes:
1. "generated" — use the code generated in the current agent session
2. Exact file path — use directly if the file exists
3. Fuzzy description — scan available implementations, ask LLM to pick the best match
"""
from __future__ import annotations

import ast
import json
from pathlib import Path
from typing import Any, Dict, List, Optional

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
_PLANNER_DIR = _REPO_ROOT / "planner"
_SCHEDULER_DIR = _REPO_ROOT / "scheduler"
_PROMPT_PATH = Path(__file__).resolve().parent.parent / "prompts" / "optimize_resolve.txt"


def scan_implementations(algo_type: str) -> List[Dict[str, str]]:
    """Scan planner/ or scheduler/ directory and return metadata for each
    concrete implementation (skipping base classes)."""
    base_dir = _PLANNER_DIR if algo_type == "planner" else _SCHEDULER_DIR
    base_class_name = "BasePlanner" if algo_type == "planner" else "BaseScheduler"
    results: List[Dict[str, str]] = []

    for py_file in sorted(base_dir.glob("*.py")):
        if py_file.name.startswith("base_") or py_file.name.startswith("__"):
            continue
        try:
            tree = ast.parse(py_file.read_text(encoding="utf-8"))
        except SyntaxError:
            continue

        for node in ast.walk(tree):
            if not isinstance(node, ast.ClassDef):
                continue
            inherits_base = any(
                (isinstance(b, ast.Name) and b.id == base_class_name)
                or (isinstance(b, ast.Attribute) and b.attr == base_class_name)
                for b in node.bases
            )
            if not inherits_base:
                continue
            docstring = ast.get_docstring(node) or ""
            results.append({
                "class_name": node.name,
                "file": str(py_file.relative_to(_REPO_ROOT)),
                "abs_path": str(py_file),
                "description": docstring.split("\n")[0] if docstring else node.name,
            })
    return results


def _format_impl_list(implementations: List[Dict[str, str]]) -> str:
    lines = []
    for i, impl in enumerate(implementations, 1):
        lines.append(
            f"{i}. class={impl['class_name']}, "
            f"file={impl['file']}, "
            f"desc={impl['description']}"
        )
    return "\n".join(lines)


def resolve_algorithm_source(
    algo_type: str,
    user_detail: str,
    state: Optional[Dict[str, Any]] = None,
    optimize_source_hint: str = "",
) -> str:
    """Return the absolute file path of the algorithm to optimize.

    Resolution order:
    1. hint == "generated"  → look up state["generated_code"][algo_type]
    2. hint is a valid path → use directly
    3. Otherwise            → LLM-based fuzzy match against available implementations
    """
    state = state or {}
    hint = optimize_source_hint.strip().lower()

    if hint == "generated":
        gen = state.get("generated_code") or {}
        path = gen.get(algo_type)
        if path and Path(path).exists():
            return path
        raise ValueError(f"没有找到已生成的 {algo_type} 代码")

    if optimize_source_hint and Path(optimize_source_hint).exists():
        return str(Path(optimize_source_hint).resolve())

    base_dir = _PLANNER_DIR if algo_type == "planner" else _SCHEDULER_DIR
    candidate = base_dir / optimize_source_hint
    if candidate.exists():
        return str(candidate.resolve())

    implementations = scan_implementations(algo_type)
    if not implementations:
        raise ValueError(f"在 {base_dir} 下未找到任何 {algo_type} 实现")

    if len(implementations) == 1:
        return implementations[0]["abs_path"]

    return _llm_resolve(algo_type, user_detail, optimize_source_hint, implementations)


def _llm_resolve(
    algo_type: str,
    user_detail: str,
    hint: str,
    implementations: List[Dict[str, str]],
) -> str:
    from mapf_agent.llm import chat_json

    prompt_tpl = _PROMPT_PATH.read_text(encoding="utf-8")
    impl_list = _format_impl_list(implementations)
    prompt = prompt_tpl.format(
        algo_type=algo_type,
        impl_list=impl_list,
        user_detail=user_detail,
        hint=hint,
    )

    result = chat_json([
        {"role": "system", "content": prompt},
        {"role": "user", "content": user_detail or hint or f"优化 {algo_type}"},
    ])

    chosen_file = result.get("file", "")
    valid_paths = {impl["abs_path"] for impl in implementations}
    valid_files = {impl["file"] for impl in implementations}

    if chosen_file in valid_paths:
        return chosen_file
    for impl in implementations:
        if chosen_file == impl["file"] or chosen_file == impl["class_name"]:
            return impl["abs_path"]

    return implementations[0]["abs_path"]
