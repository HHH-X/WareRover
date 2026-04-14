"""File exploration tools: let the LLM browse project source code."""
from __future__ import annotations

import ast
from pathlib import Path
from typing import Optional

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent


def _validate_path(rel_path: str) -> Path:
    resolved = (_PROJECT_ROOT / rel_path).resolve()
    if not str(resolved).startswith(str(_PROJECT_ROOT)):
        raise ValueError(f"路径不在项目范围内: {rel_path}")
    return resolved


def list_directory(path: str) -> str:
    target = _validate_path(path)
    if not target.is_dir():
        return f"目录不存在: {path}"
    items = sorted(target.iterdir())
    lines = []
    for item in items:
        if item.name.startswith((".", "__pycache__")):
            continue
        prefix = "[DIR]  " if item.is_dir() else "[FILE] "
        lines.append(f"{prefix}{item.name}")
    return "\n".join(lines) if lines else "(空目录)"


def read_file(path: str, start_line: Optional[int] = None,
              end_line: Optional[int] = None) -> str:
    target = _validate_path(path)
    if not target.is_file():
        return f"文件不存在: {path}"
    content = target.read_text(encoding="utf-8")
    lines = content.splitlines()
    total = len(lines)
    start = (start_line or 1) - 1
    end = end_line or total
    lines = lines[start:end]
    if len(lines) > 200:
        lines = lines[:200]
        lines.append(f"... (文件共 {total} 行，已截断至 200 行)")
    numbered = [f"{start + i + 1:4d}| {l}" for i, l in enumerate(lines)]
    return "\n".join(numbered)


def get_class_signatures(path: str) -> str:
    target = _validate_path(path)
    if not target.is_file():
        return f"文件不存在: {path}"
    source = target.read_text(encoding="utf-8")
    try:
        tree = ast.parse(source)
    except SyntaxError as e:
        return f"语法解析失败: {e}"

    results: list[str] = []
    for node in ast.iter_child_nodes(tree):
        if not isinstance(node, ast.ClassDef):
            continue
        bases = ", ".join(ast.unparse(b) for b in node.bases)
        results.append(f"class {node.name}({bases}):")
        for item in node.body:
            if not isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            sig = f"    def {item.name}({ast.unparse(item.args)})"
            if item.returns:
                sig += f" -> {ast.unparse(item.returns)}"
            results.append(sig)
            doc = ast.get_docstring(item)
            if doc:
                first_line = doc.strip().split("\n")[0]
                results.append(f"        \"\"\"{first_line}\"\"\"")
        results.append("")
    return "\n".join(results) if results else "未找到类定义"


def _truncate(text: str, max_len: int = 120) -> str:
    text = text.replace("\n", " ").strip()
    return text if len(text) <= max_len else text[:max_len] + "..."


def execute(name: str, arguments: dict) -> str:
    try:
        if name == "list_directory":
            path = arguments["path"]
            print(f"  [工具调用] list_directory → 目录: {path}")
            result = list_directory(path)
            entries = [l for l in result.splitlines() if l.strip()]
            dirs = sum(1 for e in entries if e.startswith("[DIR]"))
            files = sum(1 for e in entries if e.startswith("[FILE]"))
            print(f"  [工具返回] 共 {dirs} 个子目录, {files} 个文件")
            return result
        if name == "read_file":
            path = arguments["path"]
            start = arguments.get("start_line")
            end = arguments.get("end_line")
            range_hint = f" (行 {start}-{end})" if start and end \
                else f" (从行 {start})" if start else ""
            print(f"  [工具调用] read_file → 文件: {path}{range_hint}")
            result = read_file(path, start, end)
            print(f"  [工具返回] 读取到 {len(result.splitlines())} 行内容")
            return result
        if name == "get_class_signatures":
            path = arguments["path"]
            print(f"  [工具调用] get_class_signatures → 文件: {path}")
            result = get_class_signatures(path)
            classes = [l for l in result.splitlines() if l.startswith("class ")]
            if classes:
                names = [c.split("(")[0].replace("class ", "") for c in classes]
                print(f"  [工具返回] 找到类: {', '.join(names)}")
            else:
                print(f"  [工具返回] {_truncate(result)}")
            return result
    except Exception as e:
        print(f"  [工具错误] {e}")
        return f"工具执行错误: {e}"
    return f"未知探索工具: {name}"
