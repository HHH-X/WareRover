"""CLI entry-point: ``python -m agent.evolve``

Examples
--------
  python -m mapf_agent.evolve --target planner --source planner/astar_planner.py
  python -m mapf_agent.evolve --target scheduler --source scheduler/TA_scheduler.py --iterations 100
  python -m mapf_agent.evolve --target both --planner-source planner/cbs_fw_planner.py --scheduler-source scheduler\TA_scheduler.py --iterations 100
  python -m mapf_agent.evolve --target layout --layout-constraints config/layout_constraints/example.yaml --iterations 100
  python -m mapf_agent.evolve --list planner   # list available implementations
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))


def _list_implementations(algo_type: str) -> None:
    from mapf_agent.evolve.resolver import scan_implementations
    impls = scan_implementations(algo_type)
    if not impls:
        print(f"未找到任何 {algo_type} 实现。")
        return
    print(f"已有的 {algo_type} 实现：")
    for impl in impls:
        print(f"  - {impl['class_name']}  ({impl['file']})")
        if impl["description"] != impl["class_name"]:
            print(f"    {impl['description']}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="直接运行 OpenEvolve 优化 MAPF 算法",
    )
    parser.add_argument(
        "--list",
        metavar="TYPE",
        choices=["planner", "scheduler"],
        help="列出指定类型的已有实现并退出",
    )
    parser.add_argument(
        "--target", "-t",
        choices=["planner", "scheduler", "both", "layout"],
        default="planner",
        help="优化目标类型 (默认: planner)",
    )
    parser.add_argument(
        "--source", "-s",
        help="算法源文件路径（当 target 为 planner 或 scheduler 时使用）",
    )
    parser.add_argument("--planner-source", help="Planner 源文件（target=both 时使用）")
    parser.add_argument("--scheduler-source", help="Scheduler 源文件（target=both 时使用）")
    parser.add_argument("--layout-constraints", help="地图布局优化约束 YAML/JSON 文件（target=layout 时使用）")
    parser.add_argument("--config", "-c", help="OpenEvolve 配置 YAML 路径")
    parser.add_argument("--iterations", "-n", type=int, help="迭代次数")
    parser.add_argument("--output", "-o", default=None, help="输出根目录 (默认: output/evolve/)")

    args = parser.parse_args()

    if args.list:
        _list_implementations(args.list)
        return

    from mapf_agent.evolve.core import EvolveRequest, OptimizationTarget, run_evolution

    target = OptimizationTarget(args.target)

    planner_src = None
    scheduler_src = None
    layout_src = None
    if target == OptimizationTarget.BOTH:
        planner_src = args.planner_source
        scheduler_src = args.scheduler_source
        if not planner_src or not scheduler_src:
            parser.error("target=both 时需要同时提供 --planner-source 和 --scheduler-source")
    elif target == OptimizationTarget.PLANNER:
        planner_src = args.source
        if not planner_src:
            parser.error("请通过 --source 指定 planner 源文件")
    elif target == OptimizationTarget.SCHEDULER:
        scheduler_src = args.source
        if not scheduler_src:
            parser.error("请通过 --source 指定 scheduler 源文件")
    else:
        layout_src = args.source
        if not args.layout_constraints:
            parser.error("target=layout 时需要提供 --layout-constraints")

    req = EvolveRequest(
        target=target,
        planner_source=planner_src,
        scheduler_source=scheduler_src,
        layout_source=layout_src,
        layout_constraints=args.layout_constraints,
        config_path=args.config,
        iterations=args.iterations,
        output_root=args.output,
    )

    print(f"开始优化: target={target.value}")
    result = run_evolution(req)
    print(f"优化完成:")
    print(f"  运行目录: {result.run_dir}")
    print(f"  最佳分数: {result.best_score:.4f}")
    print(f"  最佳指标: {result.best_metrics}")


if __name__ == "__main__":
    main()
