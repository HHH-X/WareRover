# core/fault_manager.py
from typing import Optional, Dict
import random

class FaultManager:
    def __init__(self, agv_manager):
        self.agv_manager = agv_manager
        self.faulty_agvs: Dict[int, str] = {}  # agv_id -> status: "fault", "repairing", "fixed"

    def trigger_fault(self, agv_id: Optional[int] = None):
        """随机或指定一个AGV损坏"""
        agv_id = agv_id or random.choice(list(self.agv_manager._agvs.keys()))
        self.faulty_agvs[agv_id] = "fault"
        self.agv_manager.set_fault_state(agv_id, True)
        log_info(f"AGV {agv_id} is now faulty.")

    def assign_replacement(self, faulty_agv_id: int, replacement_agv_id: int):
        """为损坏AGV分配替代AGV"""
        # 取出任务，重新调度
        faulty_agv = self.agv_manager.get_agv(faulty_agv_id)
        task = faulty_agv.current_task
        if task:
            self.agv_manager.assign_task(replacement_agv_id, task)
            log_info(f"Task {task.id} reassigned from AGV {faulty_agv_id} to AGV {replacement_agv_id}.")

    def plan_repair_path(self, planner, start_pos, fault_pos):
        """调用路径规划器，为维修人员生成路径"""
        return planner.plan(start_pos, fault_pos)

    def recover_agv(self, agv_id: int):
        """恢复AGV"""
        self.faulty_agvs[agv_id] = "fixed"
        self.agv_manager.set_fault_state(agv_id, False)
        log_info(f"AGV {agv_id} repaired.")
