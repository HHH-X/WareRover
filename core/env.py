from typing import Dict, Tuple, Set
from core.gridmap import GridMap
from core.agvmanager import AGVManager
epsilon = 1e-6  # 精度容差，可调

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
        real_pos = self.agv_manager.get_all_real_positions()
        carrying_status = self.agv_manager.get_carrying_status()

        final_next_pos: Dict[int, Tuple[int, int]] = dict(next_pos)

        # 1. 分类 AGV
        in_center, not_in_center = self.classify_by_grid_center(real_pos)

        # 2. 初始化顶点占用字典：位置 -> 占用该位置的 agv_id 集合
        vertex_conflict_dict: Dict[Tuple[int, int], Set[int]] = dict()

        # 3. 固定不在中心的 AGV，并构建初始冲突字典（静态阶段）
        for agv_id in not_in_center:
            cur = current_pos[agv_id]
            tgt = final_next_pos[agv_id]
            occ = self._get_next_occupied_positions(agv_id, cur, tgt)

            for pos in occ:
                if pos not in vertex_conflict_dict:
                    vertex_conflict_dict[pos] = set()
                if vertex_conflict_dict[pos]:
                    raise ValueError(f"Conflict in static phase for AGV {agv_id} at {pos}")
                vertex_conflict_dict[pos].add(agv_id)

        # 4. 将中心AGV初始设为原地不动
        for agv_id in in_center:
            final_next_pos[agv_id] = current_pos[agv_id]

        # 5. 多轮迭代解决中心AGV冲突
        while True:
            changed = False
            # 顶点冲突检测副本：深拷贝当前 vertex_conflict_dict
            cur_vertex_dict: Dict[Tuple[int, int], Set[int]] = {
                k: set(v) for k, v in vertex_conflict_dict.items()
            }

            edge_conflict_set: Set[Tuple[Tuple[int, int], Tuple[int, int]]] = set()

            # 初始化当前所有已决策的动作占用
            for agv_id in in_center:
                cur = current_pos[agv_id]
                tgt = final_next_pos[agv_id]
                occ = self._get_next_occupied_positions(agv_id, cur, tgt)
                for pos in occ:
                    if pos not in cur_vertex_dict:
                        cur_vertex_dict[pos] = set()
                    cur_vertex_dict[pos].add(agv_id)
                if cur != tgt:
                    edge_conflict_set.add((cur, tgt))

            # 遍历所有中心AGV
            for agv_id in in_center:
                cur = current_pos[agv_id]
                tgt = next_pos[agv_id]
                carrying = carrying_status.get(agv_id, False)

                if tgt == cur:
                    continue

                walkable = self.map.is_walkable(tgt, cur, carrying)
                occ = self._get_next_occupied_positions(agv_id, cur, tgt)

                # 顶点冲突判断：目标位置不能被他人占用（自己除外）
                vertex_occupied = cur_vertex_dict.get(tgt, set())
                has_vertex_conflict = len(vertex_occupied - {agv_id}) > 0

                # 交换冲突判断
                has_edge_conflict = (tgt, cur) in edge_conflict_set
                if walkable and not has_vertex_conflict and not has_edge_conflict:
                    if final_next_pos[agv_id] != tgt:
                        final_next_pos[agv_id] = tgt
                        changed = True
                    for pos in occ:
                        if pos not in cur_vertex_dict:
                            cur_vertex_dict[pos] = set()
                        cur_vertex_dict[pos].add(agv_id)
                    edge_conflict_set.add((cur, tgt))
                else:
                    final_next_pos[agv_id] = cur
                    edge_conflict_set.add((cur, cur))

            if not changed:
                for agv_id in in_center:
                    if final_next_pos[agv_id] != next_pos[agv_id]:
                        self.agv_manager.increment_block_count(agv_id)
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

    def classify_by_grid_center(self, real_positions: Dict[int, Tuple[float, float]]) -> Tuple[Set[int], Set[int]]:
        """
        根据 AGV 是否在网格中心将其划分为两个集合。
        网格中心定义为坐标的 x 和 y 均为 **.5。
        返回：
            in_center: 在中心的 AGV ID 集合
            not_in_center: 不在中心的 AGV ID 集合
        """
        in_center = set()
        not_in_center = set()

        for agv_id, (x, y) in real_positions.items():
            if abs(x % 1 - 0.5) < epsilon and abs(y % 1 - 0.5) < epsilon:
                in_center.add(agv_id)
            else:
                not_in_center.add(agv_id)

        return in_center, not_in_center

    def reset(self):
        # TODO: 可按需扩展重置逻辑
        pass
