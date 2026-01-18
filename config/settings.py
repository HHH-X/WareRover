from dataclasses import dataclass
from typing import Optional
import json
from enum import Enum


class SchedulerType(Enum):
    RANDOM = "random"
    TA = "ta"

class PlannerType(Enum):
    ASTAR = "astar"
    CBS_FW = "cbs_fw"
    DHC = "dhc"

class OrderMode(Enum):
    """所有支持的订单生成模式"""
    ONESHOT = "oneshot"                  # 一次性生成所有订单（原有模式）
    CONTINUOUS_CONSTANT = "continuous_constant"   # 连续平稳生成
    CONTINUOUS_PERIODIC = "continuous_periodic"   # 周期性忙闲波次
    CONTINUOUS_PARETO = "continuous_pareto"       # Pareto 热点SKU模式
    CONTINUOUS_BURST = "continuous_burst"         # 随机爆发促销模式

@dataclass
class SimConfig:
    """仿真配置参数"""

    # ==================== 算法选择配置 ====================
    scheduler_type: SchedulerType = SchedulerType.RANDOM
    planner_type: PlannerType = PlannerType.DHC
    force_replan_every_step: bool = False# 是否强制每个需要决策的 AGV 每步都重新规划路径，自动联动 DHC 使用
    dhc_model_path:str = 'D:\\Project\\AGVSim\\algorithm\\DHC\\models\\36000.pth'

    #=================== 仿真参数配置 ====================
    order_mode: OrderMode = OrderMode.ONESHOT  # 订单生成模式
    total_orders_limit = 100
    size2_ratio: float = 0.0 # size2 订单占总订单的比例，取值 0.0 ~ 1.0
    order_processing_timeout:int = 30 # 订单处理超时时间，单位秒，超过该时间未完成的订单会被重新放回未处理队列
    order_seed: Optional[int] = None  # 订单生成随机种子，None 则不固定

    # 地图和仿真步长配置
    map_file: str = "config/map_20_15_32.json"  # 默认地图路径
    max_steps: int = 1000

    time_step: float = 1.0  # 每个仿真步长的时间，单位秒
    agv_max_speed: float = 1  # AGV 最大速度，单位格/STEP
    agv_turn_time_90: float = 0  # AGV 转向所需时间，单位秒

    #=================== 前端显示配置 ====================
    cell_size: int = 40
    panel_width: int = 300
    log_to_console: bool = True

# ==================== 各种模式对应的配置 dataclass ====================
@dataclass
class OneShotConfig:
    """一次性生成所有订单模式（原有模式）"""
    # 仿真开始前一次性生成这么多订单

@dataclass
class ContinuousConstantConfig:
    """连续平稳生成模式"""
    batch_size: int = 10
    # 每波生成的订单数量

    generation_interval_steps: int = 50
    # 每隔多少 step 生成一批订单（例如 30 表示每 30 step 来一波）
    # 如果你的 time_step=1.0 秒/step，则相当于每 30 秒一波

@dataclass
class ContinuousPeriodicConfig:
    """周期性波次模式（忙闲交替，不依赖真实钟点）"""
    base_batch_size: int = 10
    # 平均/低谷时的每波订单数量

    generation_interval_steps: int = 20
    # 基础波次间隔（step），实际批次大小会随周期波动

    cycle_duration_steps: int = 80
    # 一个完整高峰-低谷周期的长度（单位：step）
    # 示例：如果 time_step=1.0，则 1800 step = 30 分钟一个周期

    peak_multiplier: float = 3.0
    # 高峰期订单量放大倍数（例如 3.0 → 每波 60 个订单）

    valley_multiplier: float = 0.3
    # 低谷期订单量缩小倍数（例如 0.3 → 每波 6 个订单）

    wave_type: str = "sine"  # 可选: "sine"（平滑正弦波） 或 "square"（方波）
    # "sine": 订单量平滑起伏，更真实
    # "square": 高峰和低谷各占一半周期，波动剧烈，便于压力测试

@dataclass
class ContinuousParetoConfig:
    alpha: float = 2.0          # Pareto 分布形状参数，典型值 1.5~3.0，越小波动越大
    scale: float = 10.0         # 缩放因子，控制平均批次大小 ≈ scale / (alpha - 1)
    generation_interval_steps: int = 30

    hot_sku_percentage: float = 0.2    # 热点 SKU 占比（如 20%）
    hot_sku_multiplier: float = 5.0    # 虽然代码中用了简化实现，但保留字段便于后续精细控制


@dataclass
class ContinuousBurstConfig:
    base_batch_size: int = 10
    generation_interval_steps: int = 60

    burst_probability_per_1000_steps: int = 50   # 每1000步触发概率（千分比）
    burst_duration_steps: int = 1800            # 促销持续时间
    burst_peak_batch_size: int = 200
    burst_interval_steps: int = 5               # 促销期间波次间隔（非常密集）

    total_orders_limit: Optional[int] = None