# 文件名: dhc_wrapper.py
import numpy as np
from typing import Dict, Tuple, List, Optional
from collections import deque


# class DHCCompatibleWrapper:
#     """
#     把你的仓库 AGV 环境包装成 DHC 完全兼容的接口
#     使用方式：
#         wrapper = DHCCompatibleWrapper(obs_radius=4)
#         obs, pos = wrapper.update(static_grid, agv_pos, targets)
#     """
#     def __init__(self, obs_radius: int = 4):
#         self.obs_radius = obs_radius
#         self.local_size = 2 * obs_radius + 1
        
#         # 上、右、下、左 四个方向的偏移（DHC 的 heuristic 顺序）
#         self.dir_offset = np.array([
#             [-1,  0],  # 0: up
#             [ 1,  0],  # 1: down  
#             [ 0, -1],  # 2: left
#             [ 0,  1]   # 3: right
#         ], dtype=int)

#     def update(self,
#                static_grid: np.ndarray,
#                agv_pos: Dict[int, Tuple[int, int]],
#                targets: Dict[int, Tuple[Tuple[int, int], Tuple[int, int]]]
#                ) -> Tuple[np.ndarray, np.ndarray]:
#         """
#         主接口：把你当前一步的状态转成 DHC 完全一致的 obs 和 pos
#         返回：
#             obs: (N, 6, local_size, local_size)   bool
#             pos: (N, 2) int   → [x, y] 也就是 [col, row]，和 DHC 完全一致
#         """
#         height, width = static_grid.shape
#         active_ids = sorted(targets.keys())               # 只有需要决策的 AGV
#         N = len(active_ids)

#         # ==================== 1. 构建全局二值地图 ====================
#         # DHC 中: 0=可通行, 1=障碍
#         obstacle_map = np.zeros((height, width), dtype=bool)
#         # -2 和 >=0 都是障碍
#         obstacle_map[static_grid == -2] = True
#         obstacle_map[static_grid >= 0]  = True

#         # 构建其他 agent 位置图（所有在格子上的 AGV）
#         agent_map = np.zeros((height, width), dtype=bool)
#         for x, y in agv_pos.values():
#             agent_map[y, x] = True

#         # ==================== 2. 为每个 active agent 计算 4-channel heuristic ====================
#         heuri_global = np.zeros((N, 4, height, width), dtype=bool)

#         for local_idx, agv_id in enumerate(active_ids):
#             (_, goal_pos) = targets[agv_id]          # goal_pos = (gx, gy)
#             gx, gy = goal_pos

#             # BFS 计算到目标的最短曼哈顿距离（只走可通行格子）
#             dist = np.full((height, width), 2147483647, dtype=np.int32)
#             dist[gy, gx] = 0
#             q = deque([(gy, gx)])

#             while q:
#                 y, x = q.popleft()
#                 d = dist[y, x]
#                 for dy, dx in [(-1,0),(1,0),(0,-1),(0,1)]:
#                     ny, nx = y + dy, x + dx
#                     if (0 <= ny < height and 0 <= nx < width and
#                         not obstacle_map[ny, nx] and dist[ny, nx] > d + 1):
#                         dist[ny, nx] = d + 1
#                         q.append((ny, nx))

#             # 生成 4 个方向的 heuristic（和 DHC 一模一样）
#             for dir_idx in range(4):
#                 dy, dx = self.dir_offset[dir_idx]
#                 ny = np.clip(np.arange(height)[:, None] + dy, 0, height-1)
#                 nx = np.clip(np.arange(width)[None, :] + dx, 0, width-1)
#                 better = dist[ny, nx] < dist
#                 heuri_global[local_idx, dir_idx] = better

#         # padding（和 DHC 完全一致）
#         pad = self.obs_radius
#         obstacle_pad = np.pad(obstacle_map, pad, constant_values=0)
#         agent_pad    = np.pad(agent_map,    pad, constant_values=0)
#         heuri_pad    = np.pad(heuri_global, ((0,0),(0,0),(pad,pad),(pad,pad)), constant_values=0)

#         # ==================== 3. 裁剪局部观测 ====================
#         obs = np.zeros((N, 6, self.local_size, self.local_size), dtype=bool)
#         pos_array = np.zeros((N, 2), dtype=int)

#         for local_idx, agv_id in enumerate(active_ids):
#             (cur_pos, _) = targets[agv_id]
#             x, y = cur_pos                                     # x=列(col), y=行(row)
#             pos_array[local_idx] = [x, y]

#             slice_y = slice(y, y + self.local_size)
#             slice_x = slice(x, x + self.local_size)

#             # channel 0: 其他 agent（自己位置强制清零）
#             obs[local_idx, 0] = agent_pad[slice_y, slice_x]
#             obs[local_idx, 0, self.obs_radius, self.obs_radius] = 0

#             # channel 1: 障碍物
#             obs[local_idx, 1] = obstacle_pad[slice_y, slice_x]

#             # channel 2~5: heuristic
#             obs[local_idx, 2:6] = heuri_pad[local_idx, :, slice_y, slice_x]

#         return obs, pos_array
    

# class Env2DHC:
#     """
#     Convert your AGV env output into DHC-style local observations.
#     """

#     def __init__(self, height, width, obs_radius):
#         self.H = height
#         self.W = width
#         self.obs_radius = obs_radius
#         self.local_size = 2 * obs_radius + 1

#     def _crop_local(self, grid, x, y):
#         """
#         使用 numpy.pad, 直接从 padded grid 截取 local 区域。
#         grid shape: (H, W)
#         输出 shape: (local_size, local_size)
#         """
#         R = self.obs_radius

#         # PAD: 上下左右都 pad R
#         padded = np.pad(grid, ((R, R), (R, R)), mode="constant", constant_values=0)

#         # 在 pad 后的坐标中，AGV 的中心位置变为 (x + R, y + R)
#         px, py = x + R, y + R

#         # 直接裁剪，无越界风险
#         return padded[px - R:px + R + 1, py - R:py + R + 1]


#     def convert(self, static_grid, agv_positions, targets):
#         """
#         Convert env info to DHC-style:
#             obs: (N, 6, local_size, local_size) float/bool
#             pos: (N, 2) int [x, y]
#         """

#         agv_ids = list(agv_positions.keys())
#         N = len(agv_ids)

#         # -------------------- 全局障碍物地图 --------------------
#         obstacle_map = np.zeros((self.H, self.W), dtype=np.float32)
#         obstacle_map[static_grid == -2] = 1
#         obstacle_map[static_grid >= 0] = 1

#         # -------------------- 全局 AGV 地图 --------------------
#         agv_global = np.zeros((self.H, self.W), dtype=np.float32)
#         for aid, (x, y) in agv_positions.items():
#             agv_global[x, y] = 1

#         # -------------------- 输出 --------------------
#         obs_all = np.zeros((N, 6, self.local_size, self.local_size), dtype=np.float32)
#         pos_all = np.zeros((N, 2), dtype=np.int32)

#         # -------------------- 为每个 AGV 构造 obs --------------------
#         for idx, aid in enumerate(agv_ids):
#             ax, ay = agv_positions[aid]     # center
#             pos_all[idx] = [ax, ay]

#             # -------- Channel 0：其他 AGV --------
#             ch0 = agv_global.copy()
#             ch0[ax, ay] = 0
#             obs_all[idx, 0] = self._crop_local(ch0, ax, ay)

#             # -------- Channel 1：障碍物（target 除外） --------
#             ch1 = obstacle_map.copy()
#             if aid in targets:
#                 (_, _), (tx, ty) = targets[aid]
#                 ch1[tx, ty] = 0
#             obs_all[idx, 1] = self._crop_local(ch1, ax, ay)

#             # -------- Channels 2~5：启发式 --------
#             ch2 = np.zeros_like(ch1)
#             ch3 = np.zeros_like(ch1)
#             ch4 = np.zeros_like(ch1)
#             ch5 = np.zeros_like(ch1)

#             if aid in targets:
#                 (_, _), (tx, ty) = targets[aid]

#                 # Manhattan heuristic
#                 # 利用广播避免双层 for 循环
#                 i_coords = np.arange(self.H)[:, None]
#                 j_coords = np.arange(self.W)[None, :]

#                 ch2 = np.abs(i_coords - tx)
#                 ch3 = np.abs(j_coords - ty)

#                 # direction sign
#                 ch4[:, :] = np.sign(tx - ax)
#                 ch5[:, :] = np.sign(ty - ay)

#             # 裁剪
#             obs_all[idx, 2] = self._crop_local(ch2, ax, ay)
#             obs_all[idx, 3] = self._crop_local(ch3, ax, ay)
#             obs_all[idx, 4] = self._crop_local(ch4, ax, ay)
#             obs_all[idx, 5] = self._crop_local(ch5, ax, ay)

#         # bool 化前两个通道
#         obs_all[:, 0] = obs_all[:, 0].astype(bool)
#         obs_all[:, 1] = obs_all[:, 1].astype(bool)

#         return obs_all, pos_all


class DHCCompatibleConverter:
    """
    将你的真实仓库 AGV env 输出 实时转换成 DHC/PRIMAL2 标准局部观测
    输出格式完全兼容你贴的那个 environment.py 中的 observe() 返回值
    """
    
    def __init__(self, obs_radius: int = 5):
        self.obs_radius = obs_radius
        self.padding = obs_radius
        self.action_list = np.array([[0, 0], [-1, 0], [1, 0], [0, -1], [0, 1]], dtype=np.int32)

    def convert(
        self,
        static_grid: np.ndarray,                          # (H, W) 你的原始地图
        agv_positions: Dict[int, Tuple[int, int]],         # {agv_id: (x, y)}
        targets: Dict[int, Tuple[Tuple[int, int], Tuple[int, int]]],  # {agv_id: (curr, goal)}
    ) -> Tuple[np.ndarray, np.ndarray]:
        """
        返回值完全等价于 DHC env 的 env.observe()
        
        Returns:
            obs   : (N, 6, 2*r+1, 2*r+1) bool     → 可直接喂给 DHC 训练的网络
            pos   : (N, 2) int                   → AGV 当前坐标（和 DHC 一致）
        """
        height, width = static_grid.shape
        active_ids = list(targets.keys())                    # 只有这些 AGV 需要规划
        N = len(active_ids)
        if N == 0:
            # 极端情况：当前没有需要规划的 AGV 为 0
            return np.zeros((0, 6, 2*self.obs_radius+1, 2*self.obs_radius+1), dtype=bool), np.zeros((0, 2), dtype=int)

        # 1. 构建全局 other-agent 地图（所有 AGV 位置，包含非活跃的，因为别人能看到你）
        global_agent_map = np.zeros((height, width), dtype=bool)
        for pos in agv_positions.values():
            x, y = pos
            if 0 <= x < height and 0 <= y < width:
                global_agent_map[x, y] = True

        # 2. 为每个 active AGV 单独构建个性化 obstacle map
        personalized_obstacle_maps = np.zeros((N, height, width), dtype=bool)
        goal_positions = np.zeros((N, 2), dtype=int)

        for idx, agv_id in enumerate(active_ids):
            _, goal_pos = targets[agv_id]
            gx, gy = goal_pos
            goal_positions[idx] = [gx, gy]

            # 基础障碍：墙(-2) + 所有货架(>=0)
            obs = (static_grid == -2) | (static_grid >= 0)

            # 关键：只有自己才能进入自己的目标货架
            if static_grid[gx, gy] >= 0:  # 目标确实是一个货架
                obs[gx, gy] = False      # 给自己留一个洞

            personalized_obstacle_maps[idx] = obs

        # 3. 计算每个 active AGV 的 4 方向 heuristic map（和 DHC 完全一致的 BFS）
        heuri_maps = self._compute_heuristic_maps(
            personalized_obstacle_maps, goal_positions, height, width, N
        )

        # 4. 构建局部观测
        obs = np.zeros((N, 6, 2*self.obs_radius+1, 2*self.obs_radius+1), dtype=bool)
        padded_agent_map = np.pad(global_agent_map, self.padding, constant_values=False)
        padded_obs_maps = np.pad(personalized_obstacle_maps, 
                                ((0,0), (self.padding, self.padding), (self.padding, self.padding)), 
                                constant_values=True)   # 边界外视为障碍

        padded_heuri = np.pad(heuri_maps, 
                              ((0,0),(0,0),(self.padding, self.padding),(self.padding, self.padding)), 
                              constant_values=False)

        positions = np.zeros((N, 2), dtype=int)

        for idx, agv_id in enumerate(active_ids):
            cx, cy = agv_positions[agv_id]
            positions[idx] = [cx, cy]

            x1 = cx
            x2 = cx + 2*self.obs_radius + 1
            y1 = cy
            y2 = cy + 2*self.obs_radius + 1

            # channel 0: 其他 AGV（自己位置挖空）
            agent_slice = padded_agent_map[x1:x2, y1:y2].copy()
            agent_slice[self.obs_radius, self.obs_radius] = False
            obs[idx, 0] = agent_slice

            # channel 1: 个性化障碍物
            obs[idx, 1] = padded_obs_maps[idx, x1:x2, y1:y2]

            # channel 2~5: 四个方向 heuristic
            obs[idx, 2:6] = padded_heuri[idx, :, x1:x2, y1:y2]

        return obs, positions

    def _compute_heuristic_maps(
        self,
        obstacle_maps: np.ndarray,   # (N, H, W) bool
        goal_positions: np.ndarray,  # (N, 2)
        height: int,
        width: int,
        N: int
    ) -> np.ndarray:   # (N, 4, H, W) bool
        """
        计算和 DHC 论文里完全一致的 4 方向 heuristic：
        如果往这个方向走一步，距离目标的 Manhattan 距离严格-1，则为 True
        """
        dist_maps = np.full((N, height, width), 2147483647, dtype=np.int32)
        heuri = np.zeros((N, 4, height, width), dtype=bool)

        directions = [(-1, 0), (1, 0), (0, -1), (0, 1)]  # 上 下 左 右

        for i in range(N):
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