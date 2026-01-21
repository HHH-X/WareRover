from typing import List, Dict, Any
import time
from contextlib import contextmanager
from config.settings import SimConfig
from core.order import Order

class GlobalLogger:
    """单线程仿真环境下的全局 Logger（单例）"""

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
        self.total_agv_collisions = 0

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

    # ================= Runtime Logs =================
    def add_runtime_log(self, msg: str):
        self._runtime_logs.append(msg)
        if self._log_to_console:
            print(msg)

        if len(self._runtime_logs) > self._max_runtime_logs:
            self._runtime_logs.pop(0)

    def get_runtime_logs(self, n: int = 10) -> List[str]:
        return self._runtime_logs[-n:]
    
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

            # ---------- Runtime ----------
            "Sim Steps": final_step,
        }


# Global instance
global_logger = GlobalLogger()
