from __future__ import annotations

from typing import Dict, Tuple, Set, List, TYPE_CHECKING
from core.agv import StepInfo

if TYPE_CHECKING:
    from utils.simulation_context import SimulationContext

epsilon = 1e-4


class Env:
    """Environment for conflict resolution and AGV stepping.

    All positions use (row, col) convention.
    """

    def __init__(self, ctx: SimulationContext):
        assert (
            ctx.agv_manager is not None
            and ctx.warehouse_map is not None
            and ctx.order_manager is not None
        )
        self.agv_manager = ctx.agv_manager
        self.warehouse_map = ctx.warehouse_map
        self.order_manager = ctx.order_manager
        self.elevator_manager = ctx.elevator_manager

    def _floor_map(self, agv_id: int):
        """Get the GridMap for this AGV's floor."""
        fid = self.agv_manager.get_agv_floor(agv_id)
        return self.warehouse_map.get_floor(fid)

    def get_env_info(self):
        """Global env info across all floors (backward-compatible)."""
        carrying_status = self.agv_manager.get_carrying_status()
        action_queues = self.agv_manager.get_all_action_queues()
        current_grid_pos = self.agv_manager.get_all_current_pos()
        agv_sizes = self.agv_manager.agv_sizes
        agv_floors = self.agv_manager.agv_floors

        return {
            'carrying_status': carrying_status,
            'action_queues': action_queues,
            'current_grid_pos': current_grid_pos,
            'agv_sizes': agv_sizes,
            'agv_floors': agv_floors,
        }

    def get_env_info_for_floor(self, floor_id: int):
        """Per-floor env info for planner / scheduler."""
        floor_grid = self.warehouse_map.get_floor(floor_id)
        floor_agvs = self.agv_manager.get_agvs_on_floor(floor_id)
        carrying_status = {aid: self.agv_manager.get_agv(aid).carried_box_id is not None
                           for aid in floor_agvs}
        action_queues = self.agv_manager.get_action_queues_on_floor(floor_id)
        current_grid_pos = self.agv_manager.get_current_pos_on_floor(floor_id)
        agv_sizes = {aid: self.agv_manager.agv_sizes[aid] for aid in floor_agvs}

        return {
            'type_grid': floor_grid.type_grid,
            'shelf_id_grid': floor_grid.shelf_id_grid,
            'elevator_id_grid': floor_grid.elevator_id_grid,
            'carrying_status': carrying_status,
            'action_queues': action_queues,
            'current_grid_pos': current_grid_pos,
            'agv_sizes': agv_sizes,
        }

    def _can_enter_elevator(self, agv_id: int, elevator_id: int, floor_id: int) -> bool:
        if self.elevator_manager is None:
            return False
        return self.elevator_manager.can_agv_enter(agv_id, elevator_id, floor_id)

    def get_walkable_neighbors(self, agv_id: int, pos: Tuple[int, int],
                               carrying_goods: bool) -> List[Tuple[int, int]]:
        fmap = self._floor_map(agv_id)
        return fmap.get_walkable_neighbors(
            agv_id=agv_id,
            agv_size=self.agv_manager.get_agv_size(agv_id),
            pos=pos,
            carrying_goods=carrying_goods,
            can_enter_elevator=self._can_enter_elevator,
        )

    def is_walkable(self, agv_id: int, to_pos: Tuple[int, int],
                    from_pos: Tuple[int, int], carrying_goods: bool) -> bool:
        fmap = self._floor_map(agv_id)
        return fmap.is_walkable(
            agv_id=agv_id,
            agv_size=self.agv_manager.get_agv_size(agv_id),
            to_pos=to_pos,
            from_pos=from_pos,
            carrying_goods=carrying_goods,
            can_enter_elevator=self._can_enter_elevator,
        )

    def step(self) -> Dict[int, StepInfo]:
        """Resolve conflicts per floor, then step all AGVs."""
        all_final: Dict[int, Tuple[int, int]] = {}
        all_blocked: Set[int] = set()

        for fid in self.warehouse_map.all_floor_ids():
            floor_agvs = self.agv_manager.get_agvs_on_floor(fid)
            if not floor_agvs:
                continue
            floor_grid = self.warehouse_map.get_floor(fid)
            final, blocked = self._resolve_conflicts_for_floor(fid, floor_agvs, floor_grid)
            all_final.update(final)
            all_blocked |= blocked

        step_info_dict = self.agv_manager.step_all(all_final)
        for agv_id in all_blocked:
            step_info_dict[agv_id] = StepInfo.COLLISION
        return step_info_dict

    def _resolve_conflicts_for_floor(
        self, floor_id: int, floor_agvs: Set[int], floor_grid
    ) -> Tuple[Dict[int, Tuple[int, int]], Set[int]]:
        current_pos = {aid: self.agv_manager.get_agv(aid).grid_pos for aid in floor_agvs}
        next_pos = {aid: self.agv_manager.get_agv(aid).get_next_pos() for aid in floor_agvs}
        real_pos = {aid: self.agv_manager.get_agv(aid).real_pos for aid in floor_agvs}
        carrying_status = {aid: self.agv_manager.get_agv(aid).carried_box_id is not None
                           for aid in floor_agvs}

        final_next_pos: Dict[int, Tuple[int, int]] = dict(next_pos)
        block_agvs: Set[int] = set()

        for agv_id, tgt in next_pos.items():
            cur = current_pos[agv_id]
            dr = abs(tgt[0] - cur[0])
            dc = abs(tgt[1] - cur[1])
            if dr + dc > 1:
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

                walkable = floor_grid.is_walkable(
                    agv_id=agv_id,
                    agv_size=self.agv_manager.get_agv_size(agv_id),
                    to_pos=tgt,
                    from_pos=cur,
                    carrying_goods=carrying,
                    can_enter_elevator=self._can_enter_elevator,
                )
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
        size = self.agv_manager.get_agv_size(agv_id)

        def footprint(pos: Tuple[int, int]) -> Set[Tuple[int, int]]:
            row, col = pos
            return {(row + dr, col + dc) for dr in range(size) for dc in range(size)}

        if cur == tgt:
            return footprint(cur)

        real_pos = self.agv_manager.get_real_position(agv_id)
        speed = self.agv_manager.get_agv_speed(agv_id)
        move_offset = speed * 1
        r, c = real_pos
        dr = tgt[0] - cur[0]
        dc = tgt[1] - cur[1]
        cur_fp = footprint(cur)
        tgt_fp = footprint(tgt)

        occupied: Set[Tuple[int, int]] = set()

        if dr != 0:
            target_r = tgt[0] + 0.5
            if abs(target_r - r) <= move_offset + epsilon:
                occupied |= tgt_fp
            else:
                occupied |= (cur_fp | tgt_fp)
        elif dc != 0:
            target_c = tgt[1] + 0.5
            if abs(target_c - c) <= move_offset + epsilon:
                occupied |= tgt_fp
            else:
                occupied |= (cur_fp | tgt_fp)
        else:
            occupied |= cur_fp

        return occupied

    def classify_by_grid_center(self, real_positions: Dict[int, Tuple[float, float]]) -> Tuple[Set[int], Set[int]]:
        in_center = set()
        not_in_center = set()
        for agv_id, (r, c) in real_positions.items():
            if abs(r % 1 - 0.5) < epsilon and abs(c % 1 - 0.5) < epsilon:
                in_center.add(agv_id)
            else:
                not_in_center.add(agv_id)
        return in_center, not_in_center

    def reset(self):
        self.agv_manager.reset_agvs()
        self.warehouse_map.reset()
        self.order_manager.reset_order()
