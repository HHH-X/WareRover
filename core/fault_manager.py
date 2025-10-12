# core/fault_manager.py
from typing import Optional, Dict, Tuple, List
import random
from core.agvmanager import AGVManager
from core.env import Env
from core.gridmap import GridMap

class FaultManager:
    def __init__(self, agv_manager: AGVManager, env: Env, gridmap: GridMap):
        self.agv_manager = agv_manager
        self.gridmap = gridmap
        self.env = env
        env_info = env.get_env_info()
        self.static_grid = env_info['static_grid']

    def handle_message(self, msg: dict):
        """
        处理来自前端的命令消息
        msg 示例：
        {
            "cmd": "damage", "agv_id": 2
        }
        或
        {
            "cmd": "repair", "agv_id": 2
        }
        """
        cmd = msg.get("cmd")
        agv_id = msg.get("agv_id")
        print(f"[FaultManager] 处理命令: {msg}")
        if cmd == "damage":
            self.simulate_fault(agv_id)
        elif cmd == "repair":
            self.repair_agv(agv_id)
        # else:
        #     print(f"[FaultManager] 未知命令: {cmd}")

    def simulate_fault(self, agv_id: int):
        self.agv_manager.set_agv_status(agv_id, False)
        agv_grid_pos = self.agv_manager.get_agv(agv_id).grid_pos
        # 找到最近的边界点
        border_cell = self._find_nearest_border_free_cell(agv_grid_pos)
        path = self.plan_repair_path(agv_grid_pos, border_cell)
        self.gridmap.add_dynamic_occupancy(path)

    def repair_agv(self, agv_id: int):
        self.agv_manager.set_agv_status(agv_id, True)

    def assign_replacement(self, faulty_agv_id: int, replacement_agv_id: int):
        """为损坏AGV分配替代AGV"""
        # 取出任务，重新调度
        faulty_agv = self.agv_manager.get_agv(faulty_agv_id)
        task = faulty_agv.current_task
        if task:
            self.agv_manager.assign_task(replacement_agv_id, task)
            # log_info(f"Task {task.id} reassigned from AGV {faulty_agv_id} to AGV {replacement_agv_id}.")

    def plan_repair_path(self, planner, start_pos, fault_pos):
        """调用路径规划器，为维修人员生成路径"""
        return planner.plan(start_pos, fault_pos)

    
    def _find_nearest_border_free_cell(self, start: Tuple[int, int]) -> Optional[Tuple[int, int]]:
        """
        从起点出发，在 static_grid 中找到最近的可通行边界点（即 -1 位置）
        """
        h, w = self.static_grid.shape
        visited = set()
        queue = [start]

        while queue:
            x, y = queue.pop(0)
            if (x, y) in visited:
                continue
            visited.add((x, y))

            # 检查是否为可通行边界点
            if self.static_grid[y, x] == -1 and (x == 0 or y == 0 or x == w - 1 or y == h - 1):
                return (x, y)

            # 四方向搜索
            for dx, dy in [(1, 0), (-1, 0), (0, 1), (0, -1)]:
                nx, ny = x + dx, y + dy
                if 0 <= nx < w and 0 <= ny < h and self.static_grid[ny, nx] == -1:
                    queue.append((nx, ny))

        return None  # 没有找到

    def plan_repair_path(self, start: Tuple[int, int], goal: Tuple[int, int]) -> Optional[List[Tuple[int, int]]]:
        """
        在 static_grid 上规划从 start 到 goal 的可通行路径
        """
        h, w = self.static_grid.shape
        queue = [(start, [start])]
        visited = set()

        while queue:
            (x, y), path = queue.pop(0)
            if (x, y) == goal:
                return path

            if (x, y) in visited:
                continue
            visited.add((x, y))

            for dx, dy in [(1, 0), (-1, 0), (0, 1), (0, -1)]:
                nx, ny = x + dx, y + dy
                if 0 <= nx < w and 0 <= ny < h and self.static_grid[ny, nx] == -1 and (nx, ny) not in visited:
                    queue.append(((nx, ny), path + [(nx, ny)]))

        return None
