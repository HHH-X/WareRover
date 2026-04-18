import numpy as np
from typing import Dict, Tuple, List, Optional
from collections import deque
from core.env import Env
from core.gridmap import GridMap, CellType
from core.agvmanager import AGVManager
from . import configs


class DHCCompatibleConverter:
    """Convert real warehouse AGV env output to DHC/PRIMAL2 local observations.

    All positions use (row, col) convention, which directly maps to numpy
    array indexing — no coordinate flipping needed.
    """

    def __init__(self, num_agvs: int, gridmap: GridMap, agvmanager: AGVManager):
        self.obs_radius = configs.obs_radius
        self.padding = self.obs_radius
        self.N = num_agvs
        self.gridmap = gridmap
        self.agvmanager = agvmanager

    def convert(
        self,
        type_grid: np.ndarray,                                # (H, W) int8
        agv_positions: Dict[int, Tuple[int, int]],             # {agv_id: (row, col)}
        targets: Dict[int, Tuple[Tuple[int, int], Tuple[int, int]]],  # {agv_id: (curr, goal)}
    ) -> Tuple[np.ndarray, np.ndarray]:
        """
        Returns:
            obs   : (N, 6, 2*r+1, 2*r+1) bool
            pos   : (N, 2) int  — AGV positions as (row, col)
        """
        height, width = type_grid.shape
        active_ids = list(targets.keys())
        if active_ids == 0:
            return (np.zeros((0, 6, 2*self.obs_radius+1, 2*self.obs_radius+1), dtype=bool),
                    np.zeros((0, 2), dtype=int))

        # 1. Global other-agent map
        global_agent_map = np.zeros((height, width), dtype=bool)
        for agv_id, (row, col) in agv_positions.items():
            agv = self.agvmanager.get_agv(agv_id)
            size = agv.size
            for dr in range(size):
                for dc in range(size):
                    r, c = row + dr, col + dc
                    if 0 <= r < height and 0 <= c < width:
                        global_agent_map[r, c] = True

        # 2. Personalized obstacle maps per active AGV
        personalized_obstacle_maps = np.zeros((self.N, height, width), dtype=bool)
        goal_positions = np.zeros((self.N, 2), dtype=int)

        for agv_id in active_ids:
            _, goal_pos = targets[agv_id]
            goal_row, goal_col = goal_pos
            goal_positions[agv_id] = [goal_row, goal_col]

            obs = (type_grid == CellType.OBSTACLE) | (type_grid == CellType.SHELF)

            if type_grid[goal_row, goal_col] == CellType.SHELF:
                obs[goal_row, goal_col] = False

            personalized_obstacle_maps[agv_id] = obs

        # 3. Compute 4-direction heuristic maps (BFS from goal)
        heuri_maps = self._compute_heuristic_maps(
            personalized_obstacle_maps, goal_positions, height, width, active_ids
        )

        # 4. Build local observations
        obs = np.zeros((self.N, 6, 2*self.obs_radius+1, 2*self.obs_radius+1), dtype=bool)
        padded_agent_map = np.pad(global_agent_map, self.padding, constant_values=False)
        padded_obs_maps = np.pad(personalized_obstacle_maps,
                                ((0, 0), (self.padding, self.padding), (self.padding, self.padding)),
                                constant_values=True)

        padded_heuri = np.pad(heuri_maps,
                              ((0, 0), (0, 0), (self.padding, self.padding), (self.padding, self.padding)),
                              constant_values=False)

        positions = np.zeros((self.N, 2), dtype=int)

        for agv_id in active_ids:
            row, col = agv_positions[agv_id]
            positions[agv_id] = [row, col]

            r1 = row
            r2 = row + 2*self.obs_radius + 1
            c1 = col
            c2 = col + 2*self.obs_radius + 1

            # channel 0: other AGVs (self footprint removed)
            agent_slice = padded_agent_map[r1:r2, c1:c2].copy()
            agv = self.agvmanager.get_agv(agv_id)
            size = agv.size
            center = self.obs_radius
            for dr in range(size):
                for dc in range(size):
                    lr = center + dr
                    lc = center + dc
                    if 0 <= lr < agent_slice.shape[0] and 0 <= lc < agent_slice.shape[1]:
                        agent_slice[lr, lc] = False
            obs[agv_id, 0] = agent_slice

            # channel 1: personalized obstacles + unwalkable direction injection
            obstacle_slice = padded_obs_maps[agv_id, r1:r2, c1:c2]
            obstacle_slice = self._inject_unwalkable_as_obstacle(
                agv_id=agv_id,
                row=row,
                col=col,
                obstacle_slice=obstacle_slice
            )
            obs[agv_id, 1] = obstacle_slice

            # channels 2~5: 4-direction heuristic
            obs[agv_id, 2:6] = padded_heuri[agv_id, :, r1:r2, c1:c2]

        return obs, positions

    def _compute_heuristic_maps(
        self,
        obstacle_maps: np.ndarray,   # (N, H, W) bool
        goal_positions: np.ndarray,  # (N, 2)
        height: int,
        width: int,
        active_ids: list[int]
    ) -> np.ndarray:   # (N, 4, H, W) bool
        dist_maps = np.full((self.N, height, width), 2147483647, dtype=np.int32)
        heuri = np.zeros((self.N, 4, height, width), dtype=bool)

        for i in active_ids:
            gr, gc = goal_positions[i]
            if obstacle_maps[i, gr, gc]:
                continue

            dist_maps[i, gr, gc] = 0
            queue = deque([(gr, gc)])

            while queue:
                r, c = queue.popleft()
                d = dist_maps[i, r, c]

                for dr, dc in [(-1, 0), (1, 0), (0, -1), (0, 1)]:
                    nr = r + dr
                    nc = c + dc
                    if 0 <= nr < height and 0 <= nc < width and not obstacle_maps[i, nr, nc]:
                        if dist_maps[i, nr, nc] > d + 1:
                            dist_maps[i, nr, nc] = d + 1
                            queue.append((nr, nc))

            # 4-direction heuristic: up/down/left/right
            for r in range(height):
                for c in range(width):
                    if obstacle_maps[i, r, c]:
                        continue
                    d = dist_maps[i, r, c]
                    if d == 2147483647:
                        continue

                    # up (row - 1)
                    if r > 0 and not obstacle_maps[i, r-1, c] and dist_maps[i, r-1, c] == d - 1:
                        heuri[i, 0, r, c] = True
                    # down (row + 1)
                    if r < height-1 and not obstacle_maps[i, r+1, c] and dist_maps[i, r+1, c] == d - 1:
                        heuri[i, 1, r, c] = True
                    # left (col - 1)
                    if c > 0 and not obstacle_maps[i, r, c-1] and dist_maps[i, r, c-1] == d - 1:
                        heuri[i, 2, r, c] = True
                    # right (col + 1)
                    if c < width-1 and not obstacle_maps[i, r, c+1] and dist_maps[i, r, c+1] == d - 1:
                        heuri[i, 3, r, c] = True

        return heuri

    def _inject_unwalkable_as_obstacle(
        self,
        agv_id: int,
        row: int,
        col: int,
        obstacle_slice: np.ndarray
    ) -> np.ndarray:
        """Mark unwalkable directions as obstacles in the local observation."""
        patched = obstacle_slice.copy()

        agv = self.agvmanager.get_agv(agv_id)
        agv_size = agv.size
        carrying = agv.carried_box_id is not None
        center = self.obs_radius

        # (drow, dcol): up, down, left, right
        directions = [(-1, 0), (1, 0), (0, -1), (0, 1)]

        for dr, dc in directions:
            next_row = row + dr
            next_col = col + dc

            can_walk = self.gridmap.is_walkable(
                agv_id=agv_id,
                agv_size=agv_size,
                from_pos=(row, col),
                to_pos=(next_row, next_col),
                carrying_goods=carrying,
            )

            if not can_walk:
                local_row = center + dr
                local_col = center + dc
                if 0 <= local_row < patched.shape[0] and 0 <= local_col < patched.shape[1]:
                    patched[local_row, local_col] = True

        return patched
