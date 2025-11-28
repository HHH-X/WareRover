# run.py
import asyncio
import json
import os
import threading
import webbrowser
from http.server import SimpleHTTPRequestHandler
from socketserver import TCPServer
import random
import numpy as np

from config.settings import SimConfig
from core.agvmanager import AGVManager
from core.gridmap import GridMap
from core.order import OrderManager
from core.env import Env
from core.simulator import Simulator
from core.data_generator import generate_send_data
from core.fault_manager import FaultManager
from utils.logger import global_logger
from scheduler.random_scheduler import RandomScheduler
from scheduler.TA_scheduler import TAScheduler
from planner.astar_planner import AStarPlanner
from planner.cbs_fw_planner import FixedWindowCBSPlanner
from planner.dhc_planner import DHCPlanner
import websockets

# 控制状态
STATE = {
    "paused": False,
    "step_trigger": False,
}

# 是否继续运行主循环
RUNNING = True
# 重置标志
NEED_RESET = False

# ---------------- HTTP 服务 ----------------
def start_http_server(port=8000):
    """启动本地 HTTP 服务，解决 file:// CORS 问题"""
    os.chdir(os.path.abspath("."))  # 确保当前目录是项目根目录
    handler = SimpleHTTPRequestHandler
    with TCPServer(("", port), handler) as httpd:
        print(f"HTTP server running at http://localhost:{port}")
        httpd.serve_forever()


async def simulator_loop(websocket, message_queue):
    global RUNNING
    global NEED_RESET
    print("Simulation begin")

    cfg = SimConfig()
    global_logger.init_from_config(cfg)

    # --- 初始化各组件 ---
    grid_map = GridMap(cfg)
    ordermanager = OrderManager(cfg, grid_map)
    agv_manager = AGVManager(cfg, grid_map, ordermanager)
    env = Env(agv_manager, grid_map, ordermanager)
    # scheduler = RandomScheduler(ordermanager, grid_map, agv_manager)
    scheduler = TAScheduler(ordermanager, grid_map, agv_manager)
    # planner = AStarPlanner(env)
    # planner = FixedWindowCBSPlanner(env)
    planner = DHCPlanner(env, model_path=cfg.dhc_model_path, forward_steps=1, device="cuda")
    simulator = Simulator(cfg, grid_map, agv_manager, env, scheduler, planner)

    # 初始化 FaultManager
    fault_manager = FaultManager(agv_manager, env, grid_map)

    # --- 初始化前端状态 ---
    init_data = generate_send_data(grid_map, agv_manager, data_type="init")
    await websocket.send(json.dumps(init_data))

    while RUNNING:
        if NEED_RESET:
            print("Resetting simulation...")
            simulator.step_count = 0
            env.reset()
            NEED_RESET = False
            # 重新发送初始化数据
            # init_data = generate_send_data(grid_map, agv_manager, data_type="init")
            # await websocket.send(json.dumps(init_data))
            print("Reset complete.")
            continue
        # 正常仿真步进
        while (RUNNING
               and not NEED_RESET
               and not ordermanager.is_all_orders_completed()
               and simulator.step_count < cfg.max_steps):

            if not STATE["paused"] or STATE["step_trigger"]:
                simulator.step()
                STATE["step_trigger"] = False

                # 每步生成并发送状态
                step_data = generate_send_data(grid_map, agv_manager, data_type="update")
                await websocket.send(json.dumps(step_data))

            # 检查是否收到消息队列中的命令
            while not message_queue.empty():
                msg = await message_queue.get()
                fault_manager.handle_message(msg)
                print("处理完消息")

            await asyncio.sleep(0.1)

        # 仿真自然结束（所有订单完成或超步数）
        if not NEED_RESET:
            print("所有订单已完成，仿真结束，等待 reset 或 stop")
        # 卡在这里等 reset 或 stop
        while RUNNING and not NEED_RESET:
            await asyncio.sleep(0.1)

    print("Simulation loop ended.")


async def ws_handler(websocket):
    global RUNNING
    message_queue = asyncio.Queue()
    sim_task = asyncio.create_task(simulator_loop(websocket, message_queue))

    try:
        async for message in websocket:
            try:
                msg = json.loads(message)
                print("收到消息:", msg)
                cmd = msg.get("cmd")

                # 控制命令
                if cmd == "pause":
                    STATE["paused"] = True
                elif cmd == "resume":
                    STATE["paused"] = False
                elif cmd == "step":
                    STATE["step_trigger"] = True
                elif cmd == "stop":
                    print("收到停止命令，准备退出...")
                    RUNNING = False
                    STATE["paused"] = True  # 停止模拟步进
                    await websocket.send(json.dumps({"status": "stopping"}))
                    await websocket.close()
                    break  # 退出消息监听循环
                elif cmd == "reset":
                    print("收到 reset 命令")
                    global NEED_RESET
                    NEED_RESET = True
                    # await websocket.send(json.dumps({"status": "resetting"}))
                    # continue
                else:
                    # 非控制命令放入队列，让 FaultManager 处理
                    await message_queue.put(msg)

            except Exception as e:
                print("Invalid message:", message, e)

    except websockets.exceptions.ConnectionClosed:
        print("WebSocket 已关闭")

    finally:
        # 取消模拟任务
        if not sim_task.done():
            sim_task.cancel()
            try:
                await sim_task
            except asyncio.CancelledError:
                pass
        print("WebSocket handler 退出完成。")


async def main():
    """
    启动可视化模式：HTTP 服务 + WebSocket + 打开浏览器
    """
    global RUNNING
    # --- 启动 HTTP 服务线程 ---
    http_port = 8000
    threading.Thread(target=start_http_server, args=(http_port,), daemon=True).start()

    # --- 打开浏览器访问前端 ---
    frontend_url = f"http://localhost:{http_port}/frontend/index.html"
    webbrowser.open(frontend_url)
    print(f"Opening browser at {frontend_url}")

    # --- 启动 WebSocket 服务 ---
    ws_port = 8765
    async with websockets.serve(ws_handler, "localhost", ws_port):
        print(f"WebSocket server running at ws://localhost:{ws_port}")

        # 每 0.5 秒检测是否需要退出
        while RUNNING:
            await asyncio.sleep(0.5)

    print("主循环结束，准备退出程序。")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("程序被用户中断。")
    finally:
        print("退出完成。")
