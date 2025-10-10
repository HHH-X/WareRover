import heapq
from typing import Dict, Tuple, List, Set
from collections import defaultdict
from core.env import Env
from planner.base_planner import BasePlanner

class AStarPlanner(BasePlanner):
    def __init__(self, env_instance:Env):
        self.env = env_instance
        self.max_time = 100

    def plan(self, targets: Dict[int, Tuple[Tuple[int, int], Tuple[int, int]]]) -> Dict[int, List[Tuple[int, int]]]:
        """
        对需要重规划路径的 AGV 进行集中式路径规划，返回路径列表
        参数:
            targets: dict {agv_id: (start_pos, target_pos)}
        返回:
            paths: dict {agv_id: List[path]}
        """
        # 获取当前已有路径，避免冲突
        env_info = self.env.get_env_info()
        current_paths = env_info['action_queues']
        carrying_status = env_info['carrying_status']

        # 构建其他AGV的空间-时间占用表
        reservation_table = self._build_reservation_table(current_paths)

        paths = {}
        for agv_id, (start, goal) in targets.items():
            carrying = carrying_status.get(agv_id, False)
            path = self._a_star_with_reservation(agv_id, start, goal, carrying, reservation_table)
            if path:
                # paths[agv_id] = path
                paths[agv_id] = path[1:] if len(path) > 1 else []
                self._add_to_reservation_table(reservation_table, path)
            else:
                paths[agv_id] = [start]  # 无法找到路径，原地等待

        return paths

    def _build_reservation_table(self, current_paths: Dict[int, List[Tuple[int, int]]]) -> Dict[int, Set[Tuple[int, int]]]:
        """构造 reservation table：时间步 -> 坐标集合"""
        table = defaultdict(set)
        max_time = 0
        for path in current_paths.values():
            for t, pos in enumerate(path):
                table[t].add(pos)
                max_time = max(max_time, t)
        return table

    def _add_to_reservation_table(self, table: Dict[int, Set[Tuple[int, int]]], path: List[Tuple[int, int]]):
        """将新路径加入 reservation table"""
        for t, pos in enumerate(path):
            table[t].add(pos)

    def _a_star_with_reservation(self, agv_id: int, start: Tuple[int, int], goal: Tuple[int, int], carrying: bool,
                                 reservation_table: Dict[int, Set[Tuple[int, int]]]) -> List[Tuple[int, int]]:
        """基于 reservation_table 的 A* 算法，避免顶点冲突与交换冲突"""
        open_set = []
        heapq.heappush(open_set, (0 + self._heuristic(start, goal), 0, start, [start]))
        closed_set = set()

        while open_set:
            f, g, current, path = heapq.heappop(open_set)

            if (current, g) in closed_set:
                continue
            closed_set.add((current, g))

            # 到达目标，且等待两步以防交换冲突
            if current == goal and self._is_free(current, g + 1, reservation_table) and self._is_free(current, g + 2, reservation_table):
                return path + [goal] * 2

            for neighbor in self.env.get_walkable_neighbors(agv_id, current, carrying):
                if not self._is_free(neighbor, g + 1, reservation_table):
                    continue

                # 避免交换冲突：自己去 neighbor，别人从 neighbor 来 current
                if self._is_edge_conflict(current, neighbor, g + 1, reservation_table):
                    continue

                new_path = path + [neighbor]
                heapq.heappush(open_set, (g + 1 + self._heuristic(neighbor, goal), g + 1, neighbor, new_path))
            if g > self.max_time:
                break
        return None

    def _heuristic(self, a: Tuple[int, int], b: Tuple[int, int]) -> int:
        """曼哈顿距离启发函数"""
        return abs(a[0] - b[0]) + abs(a[1] - b[1])

    def _is_free(self, pos: Tuple[int, int], t: int, reservation_table: Dict[int, Set[Tuple[int, int]]]) -> bool:
        """判断时间 t 的位置 pos 是否可用"""
        return pos not in reservation_table.get(t, set())

    def _is_edge_conflict(self, from_pos: Tuple[int, int], to_pos: Tuple[int, int], t: int,
                          reservation_table: Dict[int, Set[Tuple[int, int]]]) -> bool:
        """交换冲突检测（Edge Conflict）：避免两个 AGV 对换位置"""
        return (from_pos in reservation_table.get(t, set())) and (to_pos in reservation_table.get(t - 1, set()))
