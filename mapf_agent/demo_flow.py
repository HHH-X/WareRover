"""录屏演示入口: python -m mapf_agent.demo_flow

三步演示:
1) 生成地图并保存到 output/maps/multi_floor_test.json
2) 真实启动 run.py (会尝试打开前端), 手动 Ctrl+C 结束
3) 模拟 OpenEvolve 优化日志约 10~15 秒
"""
from __future__ import annotations

import json
import queue
import subprocess
import sys
import threading
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional


REPO_ROOT = Path(__file__).resolve().parent.parent
MAP_OUTPUT = REPO_ROOT / "output" / "maps" / "multi_floor_test.json"


def _slow_print(text: str, delay: float = 1.6) -> None:
    print(text)
    time.sleep(delay)


def _contains_any(text: str, words: tuple[str, ...]) -> bool:
    lowered = text.lower()
    return any(word.lower() in lowered for word in words)


def _build_demo_map() -> dict:
    floor_count = 2
    agv_per_floor = 4
    receive_per_floor = 4
    box_per_floor = 6
    width = 12
    height = 10

    floors = []
    for floor in range(floor_count):
        agvs = []
        receives = []
        boxes = []
        for i in range(agv_per_floor):
            agvs.append(
                {
                    "id": f"agv_f{floor}_{i + 1}",
                    "position": [1 + i, 1],
                    "direction": "E",
                }
            )
        for i in range(receive_per_floor):
            receives.append(
                {
                    "id": f"recv_f{floor}_{i + 1}",
                    "position": [8 + (i % 2), 6 + (i // 2)],
                }
            )
        for i in range(box_per_floor):
            boxes.append(
                {
                    "id": f"box_f{floor}_{i + 1}",
                    "position": [2 + (i % 3), 4 + (i // 3)],
                }
            )
        floors.append(
            {
                "floor_id": floor,
                "agvs": agvs,
                "receiving_areas": receives,
                "boxes": boxes,
            }
        )

    return {
        "map": {"name": "multi_floor_test", "width": width, "height": height, "floors": floor_count},
        "floors": floors,
        "elevators": [
            {
                "id": "elevator_1",
                "connect_floors": [0, 1],
                "positions": {"0": [10, 2], "1": [10, 2]},
            }
        ],
        "meta": {
            "generated_by": "mapf_agent_demo",
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        },
    }


@dataclass
class DemoState:
    map_file_path: Optional[Path] = None
    optimize_demo_ran: bool = False


def _stream_process_output(proc: subprocess.Popen[str], stop_event: threading.Event, out_q: queue.Queue[str]) -> None:
    if proc.stdout is None:
        return
    for line in proc.stdout:
        out_q.put(line.rstrip("\n"))
        if stop_event.is_set():
            break


def _step1_generate_map(state: DemoState, user_input: str) -> None:
    _slow_print("[意图解析] 正在分析用户指令...", delay=3.2)
    if not _contains_any(user_input, ("地图", "map", "生成")):
        _slow_print("[意图解析] 已识别为地图生成任务。")
    _slow_print("[意图解析] 识别到任务: 生成地图。")
    _slow_print("[地图生成] 正在构建场景约束与实体布局...", delay=3.4)
    _slow_print("[地图生成] 目标: 12x10, 2层, 每层4AGV/4接收区/6箱子, 1台电梯", delay=2.6)
    MAP_OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    demo_map = _build_demo_map()
    MAP_OUTPUT.write_text(json.dumps(demo_map, indent=2, ensure_ascii=False), encoding="utf-8")
    state.map_file_path = MAP_OUTPUT
    _slow_print(f"[地图生成] 完成，地图已保存到: {MAP_OUTPUT.as_posix()}", delay=2.4)
    _slow_print("[地图生成] 统计: floor=2, agv=8, receiving_area=8, box=12, elevator=1", delay=2.1)
    _slow_print("[流程状态] 当前任务完成。可继续输入下一条需求。", delay=1.3)


def _step2_run_simulation(state: DemoState, user_input: str) -> None:
    if state.map_file_path is None or not state.map_file_path.exists():
        _slow_print("[仿真运行] 未找到可用地图，请先发送地图生成指令。", delay=1.7)
        return
    _slow_print("[意图解析] 正在分析用户指令...", delay=3.4)
    if not _contains_any(user_input, ("运行", "仿真", "run")):
        _slow_print("[意图解析] 已识别为仿真运行任务。")
    _slow_print("[意图解析] 识别到任务: 运行仿真。")
    _slow_print("[仿真运行] 正在组装运行配置...", delay=3.3)
    _slow_print(f"[仿真运行] 使用地图: {state.map_file_path.as_posix()}", delay=2.4)
    _slow_print("[仿真运行] 已配置算法: planner=CBS, scheduler=TA", delay=2.3)
    _slow_print("[仿真运行] 正在启动 run.py（将触发前端页面打开）...", delay=2.8)

    proc = subprocess.Popen(
        [sys.executable, "run.py"],
        cwd=str(REPO_ROOT),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
        bufsize=1,
    )

    output_q: queue.Queue[str] = queue.Queue()
    stop_event = threading.Event()
    reader = threading.Thread(target=_stream_process_output, args=(proc, stop_event, output_q), daemon=True)
    reader.start()

    _slow_print("[仿真运行] run.py 已启动。现在可以录制前端交互。", delay=1.4)
    _slow_print("[仿真运行] 结束演示请按 Ctrl+C（仅停止当前运行，不退出 Demo）。", delay=1.2)

    try:
        while proc.poll() is None:
            try:
                line = output_q.get(timeout=0.25)
                if line.strip():
                    print(line)
            except queue.Empty:
                continue
    except KeyboardInterrupt:
        print("\n[仿真运行] 检测到 Ctrl+C，正在优雅停止 run.py ...")
        stop_event.set()
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=5)
    finally:
        stop_event.set()
        # 排空剩余输出，保留真实日志观感
        drained = 0
        while not output_q.empty() and drained < 200:
            line = output_q.get_nowait()
            if line.strip():
                print(line)
            drained += 1
        _slow_print("[仿真运行] 本次运行演示结束。", delay=1.3)
        _slow_print("[流程状态] 当前任务完成。可继续输入下一条需求。", delay=1.2)


def _step3_optimize_demo(state: DemoState, user_input: str) -> None:
    _slow_print("[意图解析] 正在分析用户指令...", delay=2.0)
    if not _contains_any(user_input, ("优化", "evolve", "迭代", "cbs")):
        _slow_print("[意图解析] 已识别为算法优化任务。")
    _slow_print("[意图解析] 识别到任务: 优化算法。")
    _slow_print("[算法优化] 正在准备 OpenEvolve 运行上下文...", delay=2.2)
    _slow_print("[算法优化] 扫描优化目标: planner=CBS", delay=1.8)
    _slow_print("[算法优化] 读取基线配置: iterations=100, scheduler=TA", delay=1.8)
    _slow_print("[算法优化] 初始化 evaluator 与运行目录...", delay=2.0)

    run_tag = datetime.now().strftime("%Y%m%d_%H%M%S")
    run_dir = REPO_ROOT / "output" / "evolve" / f"evolve_planner_{run_tag}_demo"
    _slow_print(f"[算法优化] Run directory: {run_dir.as_posix()}", delay=1.6)
    _slow_print("[算法优化] 开始进化优化，这可能需要较长时间...", delay=1.7)

    base_score = 142.300
    candidate = 139.870
    _slow_print("[OpenEvolve] warmup: loading prompts / templates / sandbox...", delay=2.1)
    _slow_print("[OpenEvolve] warmup: baseline evaluator ready.", delay=1.8)
    # print(f"[OpenEvolve] iter=001/100 score={candidate:.3f} improved -> best={candidate:.3f} (base={base_score:.3f})")
    # _slow_print("[OpenEvolve] checkpoint saved: checkpoint_1", delay=1.6)
    # _slow_print("[算法优化] 演示已停在第1轮迭代，等待人工中断 (Ctrl+C)...", delay=1.4)
    try:
        while True:
            time.sleep(1.0)
    except KeyboardInterrupt:
        print("\n[算法优化] 检测到 Ctrl+C，已停止在第1轮迭代演示。")

    _slow_print("[流程状态] 当前任务完成。可继续输入下一条需求。", delay=1.3)
    state.optimize_demo_ran = True


def _route_and_execute(state: DemoState, user_input: str) -> None:
    _slow_print("[Agent] 接收到新请求，进入意图识别流程...", delay=1.5)
    if _contains_any(user_input, ("地图", "map", "生成")):
        _step1_generate_map(state, user_input)
        return
    if _contains_any(user_input, ("运行", "仿真", "run")):
        _step2_run_simulation(state, user_input)
        return
    if _contains_any(user_input, ("优化", "evolve", "迭代", "cbs")):
        _step3_optimize_demo(state, user_input)
        return

    _slow_print("[意图解析] 未命中预设任务类型。", delay=1.7)
    _slow_print("[建议] 可尝试包含关键词：生成地图 / 运行仿真 / 优化CBS。", delay=1.5)


def main() -> None:
    state = DemoState()
    print("MAPF Agent Demo Ready.")
    print("请输入任意轮次任务请求，Demo 会循环进行“解析意图 -> 执行任务”。输入 quit 退出。\n")

    while True:
        try:
            user_input = input("> ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n[系统] Demo 已结束。")
            break

        if not user_input:
            continue
        if user_input.lower() in {"quit", "exit", "q"}:
            print("[系统] Demo 已退出。")
            break

        _route_and_execute(state, user_input)


if __name__ == "__main__":
    main()
