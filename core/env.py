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
        current_pos = self.agv_manager.get_all_current_pos()
        next_pos = self.agv_manager.get_all_next_pos()
        carrying_status = self.agv_manager.get_carrying_status()

        # 初始假设所有 AGV 都能执行下一步动作
        final_next_pos: Dict[int, Tuple[int, int]] = dict(next_pos)

        while True:
            changed = False
            target_count: Dict[Tuple[int, int], Set[int]] = {}
            occupied_edges: Set[Tuple[Tuple[int, int], Tuple[int, int]]] = set()

            # 收集所有当前移动决策产生的占用
            for agv_id, tgt in final_next_pos.items():
                cur = current_pos[agv_id]
                occ = self._get_next_occupied_positions(agv_id, cur, tgt)
                for pos in occ:
                    target_count.setdefault(pos, set()).add(agv_id)
                if cur != tgt:
                    occupied_edges.add((cur, tgt))

            # 一次遍历检查所有 AGV 是否因冲突而需要停止
            for agv_id in sorted(final_next_pos.keys()):
                cur = current_pos[agv_id]
                tgt = final_next_pos[agv_id]
                carrying = carrying_status.get(agv_id, False)

                if abs(cur[0] - tgt[0]) + abs(cur[1] - tgt[1]) > 1:
                    raise ValueError(f"Illegal move from {cur} to {tgt}: not adjacent")

                walkable = self.map.is_walkable(tgt, cur, carrying)
                vertex_conflict = len(target_count[tgt]) > 1
                edge_conflict = (tgt, cur) in occupied_edges

                if tgt != cur and (not walkable or vertex_conflict or edge_conflict):
                    final_next_pos[agv_id] = cur
                    self.agv_manager.increment_block_count(agv_id)
                    changed = True

            if not changed:
                break

        return final_next_pos

    def _get_next_occupied_positions(
        self, agv_id: int, cur: Tuple[int, int], tgt: Tuple[int, int]
    ) -> Set[Tuple[int, int]]:
        if cur == tgt:
            return {cur}

        real_pos = self.agv_manager.get_real_position(agv_id)
        speed = self.agv_manager.get_agv_speed(agv_id)
        time_step = 1
        epsilon = 1e-6  # 精度容差，可调

        offset = speed * time_step
        x, y = real_pos
        dx = tgt[0] - cur[0]
        dy = tgt[1] - cur[1]

        occupied: Set[Tuple[int, int]] = set()

        if dx != 0:
            target_x = tgt[0] + 0.5  # 格子中心
            if abs(target_x - x) <= offset + epsilon:
                occupied.add(tgt)
            else:
                occupied.update([cur, tgt])
        elif dy != 0:
            target_y = tgt[1] + 0.5
            if abs(target_y - y) <= offset + epsilon:
                occupied.add(tgt)
            else:
                occupied.update([cur, tgt])
        else:
            # 不移动，原地等待
            occupied.add(cur)

        return occupied

    def reset(self):
        # TODO: 可按需扩展重置逻辑
        pass
