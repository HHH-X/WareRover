from typing import Dict, Tuple, Set
from core.gridmap import GridMap
from core.agvmanager import AGVManager


class Env:
    def __init__(self, agv_manager: AGVManager, map_inst: GridMap):
        self.agv_manager = agv_manager
        self.map = map_inst

    def step(self):
        next_positions = self.resolve_conflicts()
        self.agv_manager.step_all(next_positions)

    def resolve_conflicts(self) -> Dict[int, Tuple[int, int]]:
        current_pos: Dict[int, Tuple[int, int]] = self.agv_manager.get_all_current_pos()
        next_pos: Dict[int, Tuple[int, int]] = self.agv_manager.get_all_next_pos()
        carrying_status: Dict[int, bool] = self.agv_manager.get_carrying_status()

        final_next_pos: Dict[int, Tuple[int, int]] = {}

        # 初始化冲突检测用的结构
        occupied_vertices: Set[Tuple[int, int]] = set()  # 顶点冲突
        occupied_edges: Set[Tuple[Tuple[int, int], Tuple[int, int]]] = set()  # 边冲突

        # 遍历 AGV，按顺序处理（你也可以实现优先级或路径长度排序）
        for agv_id in sorted(next_pos.keys()):
            cur = current_pos[agv_id]
            tgt = next_pos[agv_id]
            carrying = carrying_status.get(agv_id, False)
            # 排除跳跃式或非四联通的移动
            if abs(cur[0] - tgt[0]) + abs(cur[1] - tgt[1]) > 1:
                raise ValueError(f"Illegal move from {cur} to {tgt}: not adjacent")

            walkable = self.map.is_walkable(tgt, cur, carrying)

            vertex_conflict = tgt in occupied_vertices
            edge_conflict = (tgt, cur) in occupied_edges

            if cur == tgt or not walkable or vertex_conflict or edge_conflict:
                # 停留原地
                final_next_pos[agv_id] = cur
                occupied_vertices.add(cur)
                self.agv_manager.increment_block_count(agv_id)
            else:
                # 允许移动
                final_next_pos[agv_id] = tgt
                occupied_vertices.add(tgt)
                occupied_edges.add((cur, tgt))

        return final_next_pos

    def reset(self):
        # TODO: 可按需扩展重置逻辑
        pass
