# run.py
import asyncio
import json
import os
import threading
import webbrowser
from http.server import SimpleHTTPRequestHandler
from socketserver import TCPServer

from config.settings import init_sim_config
from core.agvmanager import load_agvs_from_config
from core.gridmap import load_map_from_config
from core.order import OrderManager
from core.env import Env
from core.simulator import Simulator
from core.data_generator import generate_send_data
from scheduler.random_scheduler import RandomScheduler
from planner.astar_planner import AStarPlanner
import websockets

# 控制状态
STATE = {
    "paused": False,
    "step_trigger": False,
}

# ---------------- HTTP 服务 ----------------
def start_http_server(port=8000):
    """启动本地 HTTP 服务，解决 file:// CORS 问题"""
    os.chdir(os.path.abspath("."))  # 确保当前目录是项目根目录
    handler = SimpleHTTPRequestHandler
    with TCPServer(("", port), handler) as httpd:
        print(f"HTTP server running at http://localhost:{port}")
        httpd.serve_forever()


async def simulator_loop(websocket):
    """
    仿真主循环：初始化环境 -> 循环 step -> 每步发送数据
    """
    # --- 初始化仿真环境 ---
    cfg = init_sim_config("config/test_map.json")
    grid_map = load_map_from_config(cfg)
    ordermanager = OrderManager(cfg, grid_map)
    agv_manager = load_agvs_from_config(cfg, grid_map, ordermanager)
    env = Env(agv_manager, grid_map)
    scheduler = RandomScheduler(ordermanager, grid_map)
    planner = AStarPlanner(env)
    simulator = Simulator(cfg, grid_map, agv_manager, env, scheduler, planner)

    # 初始化发送一次状态给前端
    init_data = generate_send_data(grid_map, agv_manager, data_type="init")
    await websocket.send(json.dumps(init_data))

    # --- 主循环 ---
    while not ordermanager.is_all_orders_completed() and simulator.step_count < cfg.max_steps:
        if not STATE["paused"] or STATE["step_trigger"]:
            simulator.step()  # 仿真一步
            STATE["step_trigger"] = False

            # 每步生成并发送状态
            step_data = generate_send_data(grid_map, agv_manager, data_type="update")
            print('发送数据',step_data)
            await websocket.send(json.dumps(step_data))

        await asyncio.sleep(0.1)    # 控制循环频率


async def ws_handler(websocket):
    """
    处理前端消息并启动仿真循环
    """
    sim_task = asyncio.create_task(simulator_loop(websocket))

    try:
        async for message in websocket:
            try:
                msg = json.loads(message)
                print("收到消息:", msg)
                cmd = msg.get("cmd")
                if cmd == "pause":
                    STATE["paused"] = True
                elif cmd == "resume":
                    STATE["paused"] = False
                elif cmd == "step":
                    STATE["step_trigger"] = True
            except Exception as e:
                print("Invalid message:", message, e)
    except websockets.exceptions.ConnectionClosed:
        pass
    finally:
        sim_task.cancel()


async def main():
    """
    启动可视化模式：HTTP 服务 + WebSocket + 打开浏览器
    """
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
        await asyncio.Future()  # 保持服务运行


if __name__ == "__main__":
    asyncio.run(main())
