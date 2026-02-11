import heapq
from typing import Dict, Tuple, List, Set
from collections import defaultdict
from core.env import Env
from core.gridmap import GridMap
from core.ordermanager import OrderManager
from core.fault_manager import FaultManager
from core.agvmanager import AGVManager
from planner.base_planner import BasePlanner

MAX_ASTAR_NODES = 800

class AStarPlanner(BasePlanner):
    def __init__(
        self, 
        env: Env,
        agv_manager: AGVManager,
        order_manager: OrderManager, 
        map: GridMap,
        fault_manager: FaultManager
    ):
        super().__init__(env, agv_manager, order_manager, map, fault_manager)
        self.max_time = 100
        env_info = self.env.get_env_info()
        self.agv_sizes = env_info['agv_sizes']

    def plan(self, targets: Dict[int, Tuple[Tuple[int, int], Tuple[int, int]]], scheduler) -> Dict[int, List[Tuple[int, int]]]:
        """
        对需要重规划路径的 AGV 进行集中式路径规划，返回路径列表
        参数:
            targets: dict {agv_id: (start_pos, target_pos)}
        返回:
            paths: dict {agv_id: List[path]}
        """
        if(not targets):
            return {}
        # 获取当前已有路径，避免冲突
        env_info = self.env.get_env_info()
        current_paths = env_info['action_queues']
        carrying_status = env_info['carrying_status']

        # 构建 reservation table 时考虑不同 AGV 的大小
        reservation_table = self._build_reservation_table(current_paths)

        paths = {}
        for agv_id, (start, goal) in targets.items():
            carrying = carrying_status.get(agv_id, False)
            path = self._a_star_with_reservation(
                agv_id, start, goal, carrying, reservation_table
            )
            if path:
                paths[agv_id] = path[1:] if len(path) > 1 else []
                self._add_to_reservation_table(agv_id, reservation_table, path)
            else:
                paths[agv_id] = [start]
        return paths

    # 在构建 reservation table 时展开不同 size 的格点占用
    def _build_reservation_table(
        self, current_paths: Dict[int, List[Tuple[int, int]]],
    ) -> Dict[int, Set[Tuple[int, int]]]:
        """构造 reservation table：时间步 -> 坐标集合，考虑不同 AGV 尺寸"""
        table = defaultdict(set)
        for agv_id, path in current_paths.items():
            for t, pos in enumerate(path):
                occupied = self._get_occupied_cells(agv_id, pos)
                for cell in occupied:
                    table[t].add(cell)
        return table

    # 在加入新路径时考虑 size
    def _add_to_reservation_table(
        self, agv_id: int,
        table: Dict[int, Set[Tuple[int, int]]],
        path: List[Tuple[int, int]]
    ):
        """将新路径加入 reservation table（考虑 AGV 尺寸）"""
        for t, pos in enumerate(path):
            occupied = self._get_occupied_cells(agv_id, pos)
            for cell in occupied:
                table[t].add(cell)

    def _a_star_with_reservation(self, agv_id: int, start: Tuple[int, int], goal: Tuple[int, int],
                                 carrying: bool, reservation_table: Dict[int, Set[Tuple[int, int]]]
                                 ) -> List[Tuple[int, int]]:
        """基于 reservation_table 的 A* 算法，避免顶点冲突与交换冲突"""
        open_set = []
        heapq.heappush(open_set, (0 + self._heuristic(start, goal), 0, start, [start]))
        closed_set = set()
        expanded_nodes = 0
        while open_set:
            expanded_nodes += 1
            if expanded_nodes >= MAX_ASTAR_NODES:
                break
            f, g, current, path = heapq.heappop(open_set)
            if (current, g) in closed_set:
                continue
            closed_set.add((current, g))

            # 到达目标并可安全等待
            if current == goal and self._is_free(agv_id, current, g + 1, reservation_table) and self._is_free(agv_id, current, g + 2, reservation_table):
                return path + [goal] * 2

            for neighbor in self.env.get_walkable_neighbors(agv_id, current, carrying):
                if not self._is_free(agv_id, neighbor, g + 1, reservation_table):
                    continue
                if self._is_edge_conflict(agv_id, current, neighbor, g + 1, reservation_table):
                    continue

                new_path = path + [neighbor]
                heapq.heappush(open_set, (g + 1 + self._heuristic(neighbor, goal), g + 1, neighbor, new_path))

            if g > self.max_time:
                break
        return None

    def _heuristic(self, a: Tuple[int, int], b: Tuple[int, int]) -> int:
        """曼哈顿距离启发函数"""
        return abs(a[0] - b[0]) + abs(a[1] - b[1])

    def _is_free(self, agv_id: int, pos: Tuple[int, int], 
                 t: int, reservation_table: Dict[int, Set[Tuple[int, int]]]
                 ) -> bool:
        """判断时间 t 下 AGV 在 pos（左上角）及其占用区域是否全部空闲且可走"""
        for cell in self._get_occupied_cells(agv_id, pos):
            if cell in reservation_table.get(t, set()):
                return False
        return True

    def _is_edge_conflict(self, agv_id: int, from_pos: Tuple[int, int], to_pos: Tuple[int, int], t: int,
                      reservation_table: Dict[int, Set[Tuple[int, int]]]
                      ) -> bool:
        """
        边冲突检测（扩展到多格 AGV）：
        如果 at time t 有任一格属于 from_pos 的占用集合 与 reservation_table[t] 重合，
        且 at time t-1 有任一格属于 to_pos 的占用集合 与 reservation_table[t-1] 重合，
        则认为存在交换/边冲突（简化判定）。
        """
        occ_from_t = self._get_occupied_cells(agv_id, from_pos)
        occ_to_tminus1 = self._get_occupied_cells(agv_id, to_pos)
        conflict_now = any(cell in reservation_table.get(t, set()) for cell in occ_from_t)
        conflict_prev = any(cell in reservation_table.get(t - 1, set()) for cell in occ_to_tminus1)
        return conflict_now and conflict_prev

    # 新增辅助函数
    def _get_occupied_cells(self, agv_id: int, top_left: Tuple[int, int]) -> set[Tuple[int, int]]:
        """
        根据 AGV top-left与大小计算占用格点集合
        """
        size = self.agv_sizes.get(agv_id, 1)
        x, y = top_left
        return {(x + dx, y + dy) for dx in range(size) for dy in range(size)}

