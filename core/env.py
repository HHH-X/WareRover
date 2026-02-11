from typing import Dict, Tuple, Set, List
from core.gridmap import GridMap
from core.agvmanager import AGVManager
from core.agv import StepInfo
from core.ordermanager import OrderManager
epsilon = 1e-4

class Env:
    def __init__(self, agv_manager: AGVManager, map_inst: GridMap, order_manager: OrderManager):
        self.agv_manager = agv_manager
        self.map = map_inst
        self.order_manager = order_manager

    def get_env_info(self):
        static_grid = self.map.static_grid
        carrying_status = self.agv_manager.get_carrying_status()
        action_queues = self.agv_manager.get_all_action_queues()
        current_grid_pos = self.agv_manager.get_all_current_pos()
        agv_sizes = self.agv_manager.agv_sizes

        return {
            'static_grid': static_grid,
            'carrying_status': carrying_status,
            'action_queues': action_queues,
            'current_grid_pos': current_grid_pos,
            'agv_sizes': agv_sizes
        }
    
    def get_walkable_neighbors(self, agv_id: int, pos: Tuple[int, int], carrying_goods: bool) -> List[Tuple[int, int]]:
        return self.map.get_walkable_neighbors(self.agv_manager.get_agv_size(agv_id), pos, carrying_goods)
    
    def is_walkable(self, agv_id: int, to_pos: Tuple[int, int], from_pos: Tuple[int, int], carrying_goods: bool) -> bool:
        return self.map.is_walkable(self.agv_manager.get_agv_size(agv_id), to_pos, from_pos, carrying_goods)

    def step(self) -> Dict[int, StepInfo]:
        next_positions, block_agvs = self.resolve_conflicts()
        step_info_dict = self.agv_manager.step_all(next_positions)
        for agv_id in block_agvs:
            step_info_dict[agv_id] = StepInfo.COLLISION
        return step_info_dict

    def resolve_conflicts(self) -> Tuple[Dict[int, Tuple[int, int]], Set[int]]:
        current_pos = self.agv_manager.get_all_current_pos()
        next_pos = self.agv_manager.get_all_next_pos()
        real_pos = self.agv_manager.get_all_real_positions()
        carrying_status = self.agv_manager.get_carrying_status()

        final_next_pos: Dict[int, Tuple[int, int]] = dict(next_pos)
        block_agvs: Set[int] = set()

        for agv_id, tgt in next_pos.items():
            cur = current_pos[agv_id]
            dx = abs(tgt[0] - cur[0])
            dy = abs(tgt[1] - cur[1])
            if dx + dy > 1:
                print(f"[Warning] AGV {agv_id} invalid move {cur} -> {tgt}, forced to stay.")
                next_pos[agv_id] = cur

        in_center, not_in_center = self.classify_by_grid_center(real_pos)
        vertex_conflict_dict: Dict[Tuple[int, int], Set[int]] = dict()

        for agv_id in not_in_center:
            cur = current_pos[agv_id]
            tgt = final_next_pos[agv_id]
            occ = self._get_next_occupied_positions(agv_id, cur, tgt)

            for pos in occ:
                if pos not in vertex_conflict_dict:
                    vertex_conflict_dict[pos] = set()
                if vertex_conflict_dict[pos]:
                    print("current_pos:", current_pos)
                    print("next_pos:", next_pos)
                    print("real_pos:", real_pos)
                    print("conflict at:", pos, "by agv:", agv_id, "and agv(s):", vertex_conflict_dict[pos])
                    raise ValueError(f"Conflict in static phase for AGV {agv_id} at {pos}")
                vertex_conflict_dict[pos].add(agv_id)

        for agv_id in in_center:
            final_next_pos[agv_id] = current_pos[agv_id]

        while True:
            changed = False
            cur_vertex_dict: Dict[Tuple[int, int], Set[int]] = {
                k: set(v) for k, v in vertex_conflict_dict.items()
            }
            edge_conflict_set: Set[Tuple[Tuple[int, int], Tuple[int, int]]] = set()

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

            for agv_id in in_center:
                cur = current_pos[agv_id]
                tgt = next_pos[agv_id]
                carrying = carrying_status.get(agv_id, False)

                if tgt == cur:
                    continue

                walkable = self.map.is_walkable(self.agv_manager.get_agv_size(agv_id), tgt, cur, carrying)
                occ = self._get_next_occupied_positions(agv_id, cur, tgt)
                has_vertex_conflict = any(
                    (cell in cur_vertex_dict and len(cur_vertex_dict[cell] - {agv_id}) > 0)
                    for cell in occ
                )
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
                        block_agvs.add(agv_id)
                break

        return final_next_pos, block_agvs

    def _get_next_occupied_positions(
        self, agv_id: int, cur: Tuple[int, int], tgt: Tuple[int, int]
    ) -> Set[Tuple[int, int]]:
        """Return all cells occupied by this AGV during move from cur to tgt (size-aware)."""
        size = self.agv_manager.get_agv_size(agv_id)

        def footprint(pos: Tuple[int, int]) -> Set[Tuple[int, int]]:
            x, y = pos
            return {(x + dx, y + dy) for dx in range(size) for dy in range(size)}

        if cur == tgt:
            return footprint(cur)

        real_pos = self.agv_manager.get_real_position(agv_id)
        speed = self.agv_manager.get_agv_speed(agv_id)
        time_step = 1
        offset = speed * time_step
        x, y = real_pos
        dx = tgt[0] - cur[0]
        dy = tgt[1] - cur[1]
        cur_fp = footprint(cur)
        tgt_fp = footprint(tgt)

        occupied: Set[Tuple[int, int]] = set()

        if dx != 0:
            target_x = tgt[0] + 0.5
            if abs(target_x - x) <= offset + epsilon:
                occupied |= tgt_fp
            else:
                occupied |= (cur_fp | tgt_fp)
        elif dy != 0:
            target_y = tgt[1] + 0.5
            if abs(target_y - y) <= offset + epsilon:
                occupied |= tgt_fp
            else:
                occupied |= (cur_fp | tgt_fp)
        else:
            occupied |= cur_fp

        return occupied

    def classify_by_grid_center(self, real_positions: Dict[int, Tuple[float, float]]) -> Tuple[Set[int], Set[int]]:
        """Split AGV IDs into in_center (x,y both *.5) and not_in_center."""
        in_center = set()
        not_in_center = set()

        for agv_id, (x, y) in real_positions.items():
            if abs(x % 1 - 0.5) < epsilon and abs(y % 1 - 0.5) < epsilon:
                in_center.add(agv_id)
            else:
                not_in_center.add(agv_id)

        return in_center, not_in_center

    def reset(self):
        self.agv_manager.reset_agvs()
        self.map.reset_map()
        self.order_manager.reset_order()
