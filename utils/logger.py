from typing import List, Dict
import threading


class GlobalLogger:
    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        """单例模式"""
        with cls._lock:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
                cls._instance._init()
        return cls._instance

    def _init(self):

        # 运行日志
        self._runtime_logs: List[str] = []
        self._max_runtime_logs = 100  # 保存最近100条

        # 指标日志
        self._metrics: Dict[str, float] = {
            "Throughput": 0.0,
            "Total Distance": 0.0,
            "Task Completion Rate": 0.0,
        }

        # 线程安全锁
        self._log_lock = threading.Lock()
    # ================= 配置注入 =================
    def init_from_config(self, cfg):
        """根据配置初始化指标参数（后置依赖注入）"""
        with self._log_lock:
            self._completed_tasks = 0
            total_orders = getattr(cfg, "num_orders_size1", 0) + getattr(cfg, "num_orders_size2", 0)
            self._total_tasks = total_orders
            # self.config_info["map_file"] = getattr(cfg, "map_file", "unknown")
            # self.config_info["total_orders"] = str(total_orders)
            # self.add_runtime_log(f"Initialized logger with {total_orders} total orders.")

    # ================= 配置日志 =================
    def set_config(self, key: str, value: str):
        """设置配置信息"""
        with self._log_lock:
            self.config_info[key] = value

    def get_config(self) -> Dict[str, str]:
        """获取所有配置信息"""
        with self._log_lock:
            return dict(self.config_info)

    # ================= 运行日志 =================
    def add_runtime_log(self, msg: str):
        """添加运行日志"""
        # timestamp = time.strftime("%H:%M:%S", time.localtime())
        with self._log_lock:
            # self._runtime_logs.append(f"[{timestamp}] {msg}")
            self._runtime_logs.append(msg)
            if len(self._runtime_logs) > self._max_runtime_logs:
                self._runtime_logs.pop(0)

    def get_runtime_logs(self, n: int = 10) -> List[str]:
        """获取最近 n 条运行日志"""
        with self._log_lock:
            return self._runtime_logs[-n:]

    # ================= 指标日志 =================
    def task_completed(self):
        """每当一个任务完成时调用"""
        with self._log_lock:
            self._completed_tasks += 1
            if self._total_tasks:
                rate = self._completed_tasks / self._total_tasks
                self._metrics["Task Completion Rate"] = rate
            self._metrics["Throughput"] = self._completed_tasks  # 可根据时间再计算
            self._metrics["Tasks Completed"] = self._completed_tasks

    def set_metric(self, key: str, value: float):
        """设置指标值"""
        with self._log_lock:
            self._metrics[key] = value

    def update_metric(self, key: str, delta: float):
        """累加指标"""
        with self._log_lock:
            if key not in self._metrics:
                self._metrics[key] = 0
            self._metrics[key] += delta

    def get_metrics(self) -> Dict[str, float]:
        """获取所有指标"""
        return dict(self._metrics)

# 全局唯一 logger
global_logger = GlobalLogger()