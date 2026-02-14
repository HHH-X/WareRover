from typing import List, Dict, Any, Optional, Tuple, TYPE_CHECKING
import time
from contextlib import contextmanager
from config.settings import SimConfig
from core.order import Order
import os

if TYPE_CHECKING:
    from core.agvmanager import AGVManager

class GlobalLogger:
    """Global logger singleton for single-threaded simulation."""

    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._init()
        return cls._instance

    def _init(self):
        self.reset()

    # ================= Reset =================
    def reset(self):
        # ---------- Runtime Logs ----------
        self._runtime_logs: List[str] = []
        self._max_runtime_logs = 200
        self._log_to_console = SimConfig.log_to_console
        self._log_to_file = SimConfig.log_to_file

        self.total_agv_collisions = 0

        # ---------- Order Panel Logs (separate from runtime logs) ----------
        self._order_generation_logs: List[Dict[str, Any]] = []
        self._order_assignment_logs: List[Dict[str, Any]] = []
        self._order_completion_logs: List[Dict[str, Any]] = []
        self._max_order_logs = 50

        # ---------- Order Statistics ----------
        self.total_orders = SimConfig.total_orders_limit
        self.completed_orders = 0
        self.completed_task_time = 0.0  # sum(finished - created)

        # ---------- Computation Statistics ----------
        self._computation_stats = {
            "scheduler": {"total_time": 0.0, "calls": 0},
            "planner": {"total_time": 0.0, "calls": 0},
        }
        if self._log_to_console:
            print("[GlobalLogger] Logger has been reset.")

        # ---------- File Logger ----------
        self._log_file = None
        if self._log_to_file:
            os.makedirs(SimConfig.log_dir, exist_ok=True)
            self._log_file_path = os.path.join(
                SimConfig.log_dir,
                SimConfig.log_file_name
            )

            mode = "w" if SimConfig.log_overwrite else "a"
            self._log_file = open(self._log_file_path, mode, encoding="utf-8")


    # ================= Runtime Logs =================
    def add_runtime_log(self, msg: str):
        timestamp = time.strftime("[%H:%M:%S]")
        line = f"{timestamp} {msg}"

        self._runtime_logs.append(line)
        if len(self._runtime_logs) > self._max_runtime_logs:
            self._runtime_logs.pop(0)
        if self._log_to_console:
            print(line)
        if self._log_to_file and self._log_file:
            self._log_file.write(line + "\n")
            self._log_file.flush()

    def get_runtime_logs(self, n: int = 10) -> List[str]:
        return self._runtime_logs[-n:]

    # ================= Order Panel Logs (structured, for frontend) =================
    def add_order_generation_log(self, order_id: int, receiver_id: int, goods_id: Optional[int] = None, box_id: Optional[int] = None):
        """Record when an order is generated. box_id may be None until assignment."""
        entry = {"order_id": order_id, "receiver_id": receiver_id, "goods_id": goods_id, "box_id": box_id}
        self._order_generation_logs.append(entry)
        if len(self._order_generation_logs) > self._max_order_logs:
            self._order_generation_logs.pop(0)

    def add_order_assignment_log(self, order_id: int, agv_id: int, box_id: Optional[int] = None):
        """Record when an order is assigned to an AGV."""
        entry = {"order_id": order_id, "agv_id": agv_id, "box_id": box_id}
        self._order_assignment_logs.append(entry)
        if len(self._order_assignment_logs) > self._max_order_logs:
            self._order_assignment_logs.pop(0)

    def add_order_completion_log(self, order_id: int, agv_id: int):
        """Record when an order is completed by an AGV."""
        entry = {"order_id": order_id, "agv_id": agv_id}
        self._order_completion_logs.append(entry)
        if len(self._order_completion_logs) > self._max_order_logs:
            self._order_completion_logs.pop(0)

    def get_order_logs_for_panel(self) -> Dict[str, List[Dict[str, Any]]]:
        """Get recent order logs for the frontend panel."""
        return {
            "generation": self._order_generation_logs[-self._max_order_logs:],
            "assignment": self._order_assignment_logs[-self._max_order_logs:],
            "completion": self._order_completion_logs[-self._max_order_logs:],
        }

    def get_agv_order_progress(self, agv_manager: "AGVManager") -> List[Dict[str, Any]]:
        """
        Get each AGV's current task progress for the order panel.
        Returns list of {agv_id, task_type, order_id, progress} where progress is 0..1.
        For PICK: order_id from first HANDOVER in queue; for HANDOVER: order_id; for PLACE: None.
        """
        result = []
        for agv in agv_manager.all_agvs():
            if not agv.task_queue:
                result.append({
                    "agv_id": agv.id,
                    "task_type": None,
                    "order_id": None,
                    "progress": 0.0,
                })
                continue
            task_pos, action, extra = agv.task_queue[0]
            target_pos = task_pos
            last_pos = agv.last_completed_task_pos
            # Use grid_pos for Manhattan distance (simpler, consistent)
            def manhattan(p1: Tuple[int, int], p2: Tuple[int, int]) -> int:
                return abs(p1[0] - p2[0]) + abs(p1[1] - p2[1])
            total_dist = manhattan(last_pos, target_pos)
            if total_dist <= 0:
                progress = 1.0
            else:
                remain = manhattan(agv.grid_pos, target_pos)
                progress = 1.0 - (remain / total_dist)
                progress = max(0.0, min(1.0, progress))
            order_id = None
            from core.agv import AGVAction
            if action == AGVAction.HANDOVER:
                order_id = extra
            elif action == AGVAction.PICK:
                # Look for first HANDOVER in queue to get order_id
                for t in agv.task_queue:
                    if t[1] == AGVAction.HANDOVER:
                        order_id = t[2]
                        break
            result.append({
                "agv_id": agv.id,
                "task_type": action.value if action else None,
                "order_id": order_id,
                "progress": round(progress, 3),
            })
        return result
    
    def record_agv_collision(self, agv_id: int):
        """
        Record an AGV collision event.
        """
        self.total_agv_collisions += 1


    # ================= Order Metrics =================
    def record_order_completed(self, order: Order):
        """
        Called exactly once when an order is finished.
        """
        if order.created_step is None or order.finished_step is None:
            return

        self.completed_orders += 1
        self.completed_task_time += (
            order.finished_step - order.created_step
        )

    # ================= Computation Timer =================
    @contextmanager
    def computation_timer(self, category: str):
        start = time.perf_counter()
        try:
            yield
        finally:
            if category not in self._computation_stats:
                self._computation_stats[category] = {
                    "total_time": 0.0,
                    "calls": 0,
                }
            stats = self._computation_stats[category]
            stats["total_time"] += time.perf_counter() - start
            stats["calls"] += 1

    # ================= Runtime Metrics =================
    def get_runtime_metrics(self, current_step: int) -> Dict[str, float]:
        """
        Metrics that can be queried during simulation.
        """
        success_rate = (
            self.completed_orders / self.total_orders
            if self.total_orders > 0
            else 0.0
        )

        throughput = (
            self.completed_orders / current_step
            if current_step > 0
            else 0.0
        )

        return {
            "completed_orders": self.completed_orders,
            "success_rate": success_rate,
            "throughput": throughput,
        }

    # ================= Final Metrics =================
    def get_final_metrics(self, final_step: int) -> Dict[str, Any]:
        """
        Metrics collected after simulation ends.
        """
        avg_task_time = (
            self.completed_task_time / self.completed_orders
            if self.completed_orders > 0
            else 0.0
        )

        scheduler = self._computation_stats["scheduler"]
        planner = self._computation_stats["planner"]

        decision_total_time = (
            scheduler["total_time"] + planner["total_time"]
        )
        
        return {
            # ---------- Task ----------
            "Tasks Completed": self.completed_orders,
            "Task Success Rate": (
                self.completed_orders / self.total_orders
                if self.total_orders > 0
                else 0.0
            ),
            "Total Task Time": self.completed_task_time,
            "Avg Task Time": avg_task_time,

            # ---------- Throughput ----------
            "Throughput": (
                self.completed_orders / final_step
                if final_step > 0
                else 0.0
            ),
            # ---------- Collision ----------
            "Total AGV Collisions": self.total_agv_collisions,
            # ---------- Scheduler ----------
            "Scheduler Calls": scheduler["calls"],
            "Scheduler Total Time": scheduler["total_time"],
            "Scheduler Avg Time": (
                scheduler["total_time"] / scheduler["calls"]
                if scheduler["calls"] > 0
                else 0.0
            ),

            # ---------- Planner ----------
            "Planner Calls": planner["calls"],
            "Planner Total Time": planner["total_time"],
            "Planner Avg Time": (
                planner["total_time"] / planner["calls"]
                if planner["calls"] > 0
                else 0.0
            ),

            # ---------- Joint Decision ----------
            "Decision Total Time": decision_total_time,

            # ---------- Runtime ----------
            "Sim Steps": final_step,
        }
    
    def close(self):
        if self._log_file:
            self._log_file.close()
            self._log_file = None


# Global instance
global_logger = GlobalLogger()
