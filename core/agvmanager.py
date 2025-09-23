from typing import Deque, List, Tuple, Optional, Dict, Set, Generator
from core.agv import AGV,AGVAction
from core.gridmap import GridMap
from core.order import OrderManager
from config.settings import SimConfig
import json


class AGVManager:
    def __init__(self, agv_list: List[AGV]):
        # 所有 AGV 实例，按 ID 索引
        self._agvs: Dict[int, AGV] = {agv.id: agv for agv in agv_list}
        # 当前处于空闲状态的 AGV ID（刚完成任务、去休息区途中、或在休息区）
        self.idle_agvs: Set[int] = {agv.id for agv in agv_list}
        # 空闲状态且尚未分配休息区的 AGV ID
        self.need_rest_agvs: Set[int] = set(self.idle_agvs)
        # 需要重新规划路径的 AGV ID
        self.need_replan_agvs: Set[int] = set(self.idle_agvs)
        # AGV的阻塞次数统计
        self.block_counts: Dict[int, int] = {agv.id: 0 for agv in agv_list}

    # 获取指定 ID 的 AGV 实例
    def get_agv(self, agv_id: int) -> AGV:
        return self._agvs[agv_id]
    
    def get_agv_speed(self, agv_id: int) -> float:
        agv = self._agvs.get(agv_id)
        return agv.max_speed
    
    # 获取指定 ID 的 AGV 当前网格位置
    def get_grid_position(self, agv_id:int) -> Tuple[int, int]:
        agv = self._agvs.get(agv_id)
        return agv.grid_pos
    
    def get_real_position(self, agv_id:int) -> Tuple[float, float]:
        agv = self._agvs.get(agv_id)
        return agv.real_pos
    
    def get_agv_size(self, agv_id:int)-> int:
        agv = self._agvs.get(agv_id)
        return agv.size
    
    # 获取所有 AGV 实例（生成器）
    def all_agvs(self) -> Generator[AGV, None, None]:
        yield from self._agvs.values()

    # 获取所有空闲 AGV 的 ID 列表
    def get_idle_agv_ids(self) -> List[int]:
        return list(self.idle_agvs)
    
    def get_need_rest_agv_ids(self) -> List[int]:
        return list(self.need_rest_agvs)
    
    def get_need_replan_agv_ids(self) -> List[int]:
        return list(self.need_replan_agvs)

    # 获取所有 AGV 的载货状态（True 表示正在携带货箱）
    def get_carrying_status(self) -> Dict[int, bool]:
        return {
            agv_id: agv.carried_box_id is not None
            for agv_id, agv in self._agvs.items()
        }
    
    # 获取所有 AGV 携带的货箱 ID（如果未携带货箱则为 None）
    def get_carried_box_ids(self) -> Dict[int, Optional[int]]:
        return {
            agv_id: agv.carried_box_id
            for agv_id, agv in self._agvs.items()
        }

    # 获取所有 AGV 当前的网格坐标
    def get_all_current_pos(self) -> Dict[int, Tuple[int, int]]:
        return {agv_id: agv.grid_pos for agv_id, agv in self._agvs.items()}

    # 获取所有 AGV 下一步的目标坐标（行动计划的首个点）
    def get_all_next_pos(self) -> Dict[int, Tuple[int, int]]:
        return {agv_id: agv.get_next_pos() for agv_id, agv in self._agvs.items()}
    
    # 获取所有 AGV 的真实位置（浮点坐标）
    def get_all_real_positions(self) -> Dict[int, Tuple[float, float]]:
        return {agv_id: agv.real_pos for agv_id, agv in self._agvs.items()}
    
    # 获取所有 AGV 的最大速度
    def get_all_speeds(self) -> Dict[int, float]:
        return {agv_id: agv.max_speed for agv_id, agv in self._agvs.items()}

    # 获取所有 AGV 的 action queue（路径队列），用于 Planner 使用
    def get_all_action_queues(self) -> Dict[int, List[Tuple[int, int]]]:
        result = {}
        for agv_id, agv in self._agvs.items():
            if agv.is_resting:
                # 静止休息的agv返回一个包含 10 个 rest_target 的列表
                result[agv_id] = [agv.rest_target] * 10  # type: ignore
            else:
                result[agv_id] = list(agv.action_queue)
        return result
    
    # 获取所有真实位置和网格位置中心对齐的 AGV ID 集合
    def get_aligned_agv_ids(self) -> Set[int]:
        """
        返回所有 real_pos 与 grid_pos 对齐的 AGV ID 集合。
        """
        return {agv_id for agv_id, agv in self._agvs.items() if agv.is_aligned()}


    def increment_block_count(self, agv_id: int):
        agv = self._agvs[agv_id]
        # 只有当 AGV 没有休息目标，或者有目标但没到达时，才算被阻塞
        if agv.rest_target is None or agv.grid_pos != agv.rest_target:
            self.block_counts[agv_id] += 1
    def reset_block_count(self, agv_id: int):
        self.block_counts[agv_id] = 0

    # 执行所有 AGV 的一步移动，更新其状态集合
    def step_all(self, next_positions: Dict[int, Tuple[int, int]]):
        for agv_id, next_pos in next_positions.items():
            agv = self._agvs[agv_id]
            need_replan = agv.step(next_pos)

            if agv.is_idle:
                self.idle_agvs.add(agv_id)
                if agv.rest_target is None:
                    self.need_rest_agvs.add(agv_id)

            if need_replan or self.block_counts[agv_id] >= 3:
                self.need_replan_agvs.add(agv_id)
                self.reset_block_count(agv_id)

    # 分配任务给指定 AGV
    def assign_tasks(self, task_dict: Dict[int, List[Tuple[Tuple[int, int], AGVAction, int]]]):
        for agv_id, task_list in task_dict.items():
            agv = self._agvs[agv_id]
            agv.assign_task(task_list)
            self.idle_agvs.discard(agv_id)
            self.need_rest_agvs.discard(agv_id)

    # 为空闲 AGV 分配休息区目标位置
    def assign_rest_zones(self, rest_dict: Dict[int, Tuple[int, int]]):
        for agv_id, rest_pos in rest_dict.items():
            agv = self._agvs[agv_id]
            agv.assign_rest_zone(rest_pos)
            self.need_rest_agvs.discard(agv_id)
            self.need_replan_agvs.add(agv_id)

    # 获取需要重规划的 AGV 的当前位置和目标位置
    def get_replan_targets(self) -> Dict[int, Tuple[Tuple[int, int], Tuple[int, int]]]:
        result = {}
        for agv_id in self.need_replan_agvs:
            agv = self._agvs[agv_id]
            current = agv.grid_pos
            if agv.task_queue:
                target = agv.task_queue[0][0]  # 首个任务的坐标
            else:
                target = agv.rest_target
            result[agv_id] = (current, target)
        return result

    # 为需要重规划的 AGV 设置新路径
    def replan_paths(self, path_dict: Dict[int, List[Tuple[int, int]]]):
        for agv_id, path in path_dict.items():
            agv = self._agvs[agv_id]
            agv.set_new_plan(path)
            self.need_replan_agvs.discard(agv_id)

def load_agvs_from_config(cfg: SimConfig, map_inst: GridMap, order_manager:OrderManager) -> AGVManager:
    """
    从配置文件中读取AGV信息，初始化所有AGV实例，并创建AGVManager实例。
    参数：
        cfg: SimConfig 实例，包含 map_file 路径。
    返回：
        agv_manager: AGVManager 管理器实例
    """
    with open(cfg.map_file, "r") as f:
        data = json.load(f)

    agv_data = data.get("agvs", [])
    wait_zones = {w["wait_zone_id"]: tuple(w["position"]) for w in data.get("wait_zones", [])}

    agv_list = []
    for agv_entry in agv_data:
        agv_id = agv_entry["agv_id"]
        wait_id = agv_entry["init_wait_zone_id"]
        agv_size = agv_entry["size"]
        init_grid = wait_zones[wait_id]
        agv = AGV(agv_id=agv_id, size=agv_size, init_grid_pos=init_grid, map_inst=map_inst, order_manager=order_manager)
        agv_list.append(agv)

    return AGVManager(agv_list)