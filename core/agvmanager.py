from typing import Deque, List, Tuple, Optional, Dict, Set, Generator
from core.agv import AGV,AGVAction, StepInfo
from core.gridmap import GridMap
from core.ordermanager import OrderManager
from config.settings import SimConfig
import json
from utils.logger import global_logger


class AGVManager:
    def __init__(self, map_inst: GridMap, order_manager:OrderManager):
        with open(SimConfig.map_file, "r") as f:
            data = json.load(f)

        agv_data = data.get("agvs", [])
        wait_zones = {w["wait_zone_id"]: tuple(w["position"]) for w in data.get("wait_zones", [])}
        agv_list = []
        for agv_entry in agv_data:
            agv_id = agv_entry["agv_id"]
            wait_id = agv_id
            agv_size = agv_entry.get("size", 1)
            init_grid = wait_zones[wait_id]
            agv = AGV(agv_id=agv_id, size=agv_size, init_grid_pos=init_grid, map_inst=map_inst, order_manager=order_manager)
            agv_list.append(agv)
        self._agvs: Dict[int, AGV] = {agv.id: agv for agv in agv_list}
        self.idle_agvs: Set[int] = {agv.id for agv in agv_list}
        self.need_rest_agvs: Set[int] = set(self.idle_agvs)
        self.need_replan_agvs: Set[int] = set(self.idle_agvs)
        self.block_counts: Dict[int, int] = {agv.id: 0 for agv in agv_list}
        self.agvs_by_size: Dict[int, Set[int]] = {}
        for agv in agv_list:
            self.agvs_by_size.setdefault(agv.size, set()).add(agv.id)
        self.agv_sizes: Dict[int, int] = {agv.id: agv.size for agv in agv_list}
        self.num_agvs = len(agv_list)
        self.all_agv_ids = set(self._agvs.keys())

    def get_agv(self, agv_id: int) -> AGV:
        return self._agvs[agv_id]
    
    def get_agv_speed(self, agv_id: int) -> float:
        agv = self._agvs.get(agv_id)
        return agv.max_speed
    
    def get_grid_position(self, agv_id:int) -> Tuple[int, int]:
        agv = self._agvs.get(agv_id)
        return agv.grid_pos
    
    def get_real_position(self, agv_id:int) -> Tuple[float, float]:
        agv = self._agvs.get(agv_id)
        return agv.real_pos
    
    def get_agv_size(self, agv_id:int)-> int:
        return self.agv_sizes.get(agv_id,1)
    
    def get_agv_ids_by_size(self, size: int) -> Set[int]:
        """Return set of AGV IDs with the given size."""
        return self.agvs_by_size.get(size, set())

    def all_agvs(self) -> Generator[AGV, None, None]:
        yield from self._agvs.values()

    def get_idle_agv_ids(self) -> List[int]:
        return list(self.idle_agvs)
    
    def get_need_rest_agv_ids(self) -> List[int]:
        return list(self.need_rest_agvs)
    
    def get_need_replan_agv_ids(self) -> List[int]:
        return list(self.need_replan_agvs)

    def get_carrying_status(self) -> Dict[int, bool]:
        return {
            agv_id: agv.carried_box_id is not None
            for agv_id, agv in self._agvs.items()
        }
    
    def get_carried_box_ids(self) -> Dict[int, Optional[int]]:
        return {
            agv_id: agv.carried_box_id
            for agv_id, agv in self._agvs.items()
        }

    def get_all_current_pos(self) -> Dict[int, Tuple[int, int]]:
        return {agv_id: agv.grid_pos for agv_id, agv in self._agvs.items()}

    def get_all_next_pos(self) -> Dict[int, Tuple[int, int]]:
        return {agv_id: agv.get_next_pos() for agv_id, agv in self._agvs.items()}
    
    def get_all_real_positions(self) -> Dict[int, Tuple[float, float]]:
        return {agv_id: agv.real_pos for agv_id, agv in self._agvs.items()}
    
    def get_all_speeds(self) -> Dict[int, float]:
        return {agv_id: agv.max_speed for agv_id, agv in self._agvs.items()}

    def get_all_action_queues(self) -> Dict[int, List[Tuple[int, int]]]:
        result = {}
        for agv_id, agv in self._agvs.items():
            if agv.is_resting:
                result[agv_id] = [agv.rest_target] * 10  # type: ignore
            else:
                result[agv_id] = list(agv.action_queue)
        return result
    
    def get_aligned_agv_ids(self) -> Set[int]:
        """Return set of AGV IDs whose real_pos is aligned with grid_pos."""
        return {agv_id for agv_id, agv in self._agvs.items() if agv.is_aligned()}

    def increment_block_count(self, agv_id: int):
        agv = self._agvs[agv_id]
        if agv.rest_target is None or agv.grid_pos != agv.rest_target:
            self.block_counts[agv_id] += 1
            global_logger.record_agv_collision(agv_id)

    def reset_block_count(self, agv_id: int):
        self.block_counts[agv_id] = 0

    def step_all(self, next_positions: Dict[int, Tuple[int, int]]) -> Dict[int, StepInfo]:
        step_info_dict: Dict[int, StepInfo] = {}
        for agv_id, next_pos in next_positions.items():
            agv = self._agvs[agv_id]
            need_replan, step_info = agv.step(next_pos)
            step_info_dict[agv_id] = step_info

            if agv.is_idle:
                self.idle_agvs.add(agv_id)
                if agv.rest_target is None:
                    self.need_rest_agvs.add(agv_id)

            if need_replan or self.block_counts[agv_id] >= 3:
                self.need_replan_agvs.add(agv_id)
                self.reset_block_count(agv_id)
        return step_info_dict

    def assign_tasks(self, task_dict: Dict[int, List[Tuple[Tuple[int, int], AGVAction, int]]]):
        for agv_id, task_list in task_dict.items():
            agv = self._agvs[agv_id]
            agv.assign_task(task_list)
            self.idle_agvs.discard(agv_id)
            self.need_rest_agvs.discard(agv_id)

    def assign_rest_zones(self, rest_dict: Dict[int, Tuple[int, int]]):
        for agv_id, rest_pos in rest_dict.items():
            agv = self._agvs[agv_id]
            agv.assign_rest_zone(rest_pos)
            self.need_rest_agvs.discard(agv_id)
            self.need_replan_agvs.add(agv_id)

    def get_replan_targets(self) -> Dict[int, Tuple[Tuple[int, int], Tuple[int, int]]]:
        result = {}
        if SimConfig.force_replan_every_step:
            replan_agvs = self.all_agv_ids
        else:
            replan_agvs = set(self.need_replan_agvs)
        for agv_id in replan_agvs:
            agv = self._agvs[agv_id]
            current = agv.grid_pos
            if agv.task_queue:
                target = agv.task_queue[0][0]
            else:
                target = agv.rest_target
            result[agv_id] = (current, target)
        return result

    def replan_paths(self, path_dict: Dict[int, List[Tuple[int, int]]]):
        for agv_id, path in path_dict.items():
            agv = self._agvs[agv_id]
            agv.set_new_plan(path)
            self.need_replan_agvs.discard(agv_id)

    def set_agv_status(self, agv_id, is_working):
        agv = self._agvs.get(agv_id)
        if agv:
            agv.is_working = is_working
    
    def reset_agvs(self):
        """Reset all AGVs to initial state and positions."""
        for agv in self._agvs.values():
            agv.reset()
        all_agv_ids = set(self._agvs.keys())
        self.idle_agvs = all_agv_ids.copy()
        self.need_rest_agvs = all_agv_ids.copy()
        self.need_replan_agvs = all_agv_ids.copy()
        self.block_counts = {agv_id: 0 for agv_id in all_agv_ids}
        global_logger.add_runtime_log("[AGVManager] All AGVs have been reset to initial states.")

