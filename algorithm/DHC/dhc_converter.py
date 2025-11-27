# 文件名: dhc_wrapper.py
import numpy as np
from typing import Dict, Tuple, List, Optional
from collections import deque
from core.env import Env
from . import configs

class DHCCompatibleConverter:
    """
    将你的真实仓库 AGV env 输出 实时转换成 DHC/PRIMAL2 标准局部观测
    输出格式完全兼容你贴的那个 environment.py 中的 observe() 返回值
    """
    
    def __init__(self, num_agvs:int):
        self.obs_radius = configs.obs_radius
        self.padding = self.obs_radius
        self.N = num_agvs

    def convert(
        self,
        static_grid: np.ndarray,                          # (H, W) 你的原始地图
        agv_positions_xy: Dict[int, Tuple[int, int]],         # {agv_id: (x, y)}
        targets: Dict[int, Tuple[Tuple[int, int], Tuple[int, int]]],  # {agv_id: (curr, goal)}
    ) -> Tuple[np.ndarray, np.ndarray]:
        """
        返回值完全等价于 DHC env 的 env.observe()
        
        Returns:
            obs   : (N, 6, 2*r+1, 2*r+1) bool     → 可直接喂给 DHC 训练的网络
            pos   : (N, 2) int                   → AGV 当前坐标（和 DHC 一致）
        """
        #在这里反转输入的agv的位置坐标(x,y) -> (y,x)
        agv_positions = {agv_id: (y, x) for agv_id, (x, y) in agv_positions_xy.items()}
        height, width = static_grid.shape
        active_ids = list(targets.keys())                    # 只有这些 AGV 需要规划
        if active_ids == 0:
            # 极端情况：当前没有需要规划的 AGV 为 0
            return np.zeros((0, 6, 2*self.obs_radius+1, 2*self.obs_radius+1), dtype=bool), np.zeros((0, 2), dtype=int)

        # 1. 构建全局 other-agent 地图（所有 AGV 位置，包含非活跃的，因为别人能看到你）
        global_agent_map = np.zeros((height, width), dtype=bool)
        for pos in agv_positions.values():
            x, y = pos
            if 0 <= x < height and 0 <= y < width:
                global_agent_map[x, y] = True

        # 2. 为每个 active AGV 单独构建个性化 obstacle map
        personalized_obstacle_maps = np.zeros((self.N, height, width), dtype=bool)
        goal_positions = np.zeros((self.N, 2), dtype=int)

        for agv_id in active_ids:
            _, goal_pos = targets[agv_id]
            gy, gx = goal_pos
            goal_positions[agv_id] = [gx, gy]

            # 基础障碍：墙(-2) + 所有货架(>=0)
            obs = (static_grid == -2) | (static_grid >= 0)

            # 关键：只有自己才能进入自己的目标货架
            if static_grid[gx, gy] >= 0:  # 目标确实是一个货架
                obs[gx, gy] = False      # 给自己留一个洞

            personalized_obstacle_maps[agv_id] = obs

        # 3. 计算每个 active AGV 的 4 方向 heuristic map（和 DHC 完全一致的 BFS）
        heuri_maps = self._compute_heuristic_maps(
            personalized_obstacle_maps, goal_positions, height, width, active_ids
        )

        # 4. 构建局部观测
        obs = np.zeros((self.N, 6, 2*self.obs_radius+1, 2*self.obs_radius+1), dtype=bool)
        padded_agent_map = np.pad(global_agent_map, self.padding, constant_values=False)
        padded_obs_maps = np.pad(personalized_obstacle_maps, 
                                ((0,0), (self.padding, self.padding), (self.padding, self.padding)), 
                                constant_values=True)   # 边界外视为障碍

        padded_heuri = np.pad(heuri_maps, 
                              ((0,0),(0,0),(self.padding, self.padding),(self.padding, self.padding)), 
                              constant_values=False)

        positions = np.zeros((self.N, 2), dtype=int)

        for agv_id in active_ids:
            cx, cy = agv_positions[agv_id]
            positions[agv_id] = [cx, cy]

            x1 = cx
            x2 = cx + 2*self.obs_radius + 1
            y1 = cy
            y2 = cy + 2*self.obs_radius + 1

            # channel 0: 其他 AGV（自己位置挖空）
            agent_slice = padded_agent_map[x1:x2, y1:y2].copy()
            agent_slice[self.obs_radius, self.obs_radius] = False
            obs[agv_id, 0] = agent_slice

            # channel 1: 个性化障碍物
            obs[agv_id, 1] = padded_obs_maps[agv_id, x1:x2, y1:y2]

            # channel 2~5: 四个方向 heuristic
            obs[agv_id, 2:6] = padded_heuri[agv_id, :, x1:x2, y1:y2]

        return obs, positions

    def _compute_heuristic_maps(
        self,
        obstacle_maps: np.ndarray,   # (N, H, W) bool
        goal_positions: np.ndarray,  # (N, 2)
        height: int,
        width: int,
        active_ids: list[int]
    ) -> np.ndarray:   # (N, 4, H, W) bool
        """
        计算和 DHC 论文里完全一致的 4 方向 heuristic：
        如果往这个方向走一步，距离目标的 Manhattan 距离严格-1，则为 True
        """
        dist_maps = np.full((self.N, height, width), 2147483647, dtype=np.int32)
        heuri = np.zeros((self.N, 4, height, width), dtype=bool)

        directions = [(-1, 0), (1, 0), (0, -1), (0, 1)]  # 上 下 左 右

        for i in active_ids:
            gx, gy = goal_positions[i]
            if obstacle_maps[i, gx, gy]:
                # 理论上不会发生（我们已经把自己的货架挖空了）
                continue

            dist_maps[i, gx, gy] = 0
            queue = deque([(gx, gy)])

            while queue:
                x, y = queue.popleft()
                d = dist_maps[i, x, y]

                for dx, dy in [( -1,0), (1,0), (0,-1), (0,1)]:
                    nx = x + dx
                    ny = y + dy
                    if 0 <= nx < height and 0 <= ny < width and not obstacle_maps[i, nx, ny]:
                        if dist_maps[i, nx, ny] > d + 1:
                            dist_maps[i, nx, ny] = d + 1
                            queue.append((nx, ny))

            # 生成 4 方向 heuristic
            for x in range(height):
                for y in range(width):
                    if obstacle_maps[i, x, y]:
                        continue
                    d = dist_maps[i, x, y]
                    if d == 2147483647:
                        continue

                    # 上
                    if x > 0 and not obstacle_maps[i, x-1, y] and dist_maps[i, x-1, y] == d - 1:
                        heuri[i, 0, x, y] = True
                    # 下
                    if x < height-1 and not obstacle_maps[i, x+1, y] and dist_maps[i, x+1, y] == d - 1:
                        heuri[i, 1, x, y] = True
                    # 左
                    if y > 0 and not obstacle_maps[i, x, y-1] and dist_maps[i, x, y-1] == d - 1:
                        heuri[i, 2, x, y] = True
                    # 右
                    if y < width-1 and not obstacle_maps[i, x, y+1] and dist_maps[i, x, y+1] == d - 1:
                        heuri[i, 3, x, y] = True

        return heuri