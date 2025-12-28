from dataclasses import dataclass
from typing import Optional
import json
@dataclass
class SimConfig:
    order_mode:str = ""  # 订单生成模式
    size2_ratio: float = 0.0
    # size2 订单占总订单的比例，取值 0.0 ~ 1.0

    map_file: str = "config/map_20_15_32.json"  # 默认地图路径
    max_steps: int = 1000

    time_step: float = 1.0  # 每个仿真步长的时间，单位秒
    agv_max_speed: float = 0.2  # AGV 最大速度，单位格/STEP
    agv_turn_time_90: float = 5  # AGV 转向所需时间，单位秒

    cell_size: int = 40
    panel_width: int = 300

    dhc_model_path:str = 'D:\\Project\\AGVSim\\algorithm\\DHC\\models\\74000.pth'

# ==================== 各种模式对应的配置 dataclass ====================
@dataclass
class OneShotConfig:
    """一次性生成所有订单模式（原有模式）"""
    total_orders: int = 500
    # 仿真开始前一次性生成这么多订单

@dataclass
class ContinuousConstantConfig:
    """连续平稳生成模式"""
    batch_size: int = 20
    # 每波生成的订单数量

    generation_interval_steps: int = 30
    # 每隔多少 step 生成一批订单（例如 30 表示每 30 step 来一波）
    # 如果你的 time_step=1.0 秒/step，则相当于每 30 秒一波

    total_orders_limit: Optional[int] = None
    # 总订单数量上限，达到后停止生成（None 表示不限制）

@dataclass
class ContinuousPeriodicConfig:
    """周期性波次模式（忙闲交替，不依赖真实钟点）"""
    base_batch_size: int = 20
    # 平均/低谷时的每波订单数量

    generation_interval_steps: int = 30
    # 基础波次间隔（step），实际批次大小会随周期波动

    cycle_duration_steps: int = 1800
    # 一个完整高峰-低谷周期的长度（单位：step）
    # 示例：如果 time_step=1.0，则 1800 step = 30 分钟一个周期

    peak_multiplier: float = 3.0
    # 高峰期订单量放大倍数（例如 3.0 → 每波 60 个订单）

    valley_multiplier: float = 0.3
    # 低谷期订单量缩小倍数（例如 0.3 → 每波 6 个订单）

    wave_type: str = "sine"  # 可选: "sine"（平滑正弦波） 或 "square"（方波）
    # "sine": 订单量平滑起伏，更真实
    # "square": 高峰和低谷各占一半周期，波动剧烈，便于压力测试

    total_orders_limit: Optional[int] = None

@dataclass
class ContinuousParetoConfig:
    """Pareto分布 + 热点SKU模式（80/20法则）"""
    batch_size: int = 20
    generation_interval_steps: int = 30

    hot_sku_percentage: float = 0.2
    # 热点SKU占总SKU的比例（例如 0.2 = 20%）

    hot_sku_multiplier: float = 5.0
    # 热点SKU被选中的概率放大倍数
    # 典型组合：0.2 + 5.0 ≈ 80% 订单来自 20% SKU

    hot_sku_list: List[int] = field(default_factory=list)
    # 手动指定热点SKU ID（整数列表），为空则随机选择

    total_orders_limit: Optional[int] = None

@dataclass
class ContinuousBurstConfig:
    """自动随机爆发式促销模式（模拟秒杀/突发高并发）"""
    base_batch_size: int = 10
    # 平时每波订单数量

    generation_interval_steps: int = 60
    # 平时的波次间隔（step）

    burst_probability_per_1000_steps: int = 50
    # 每 1000 step 内触发一次促销的概率（单位：千分率）
    # 示例：50 → 平均每 1000 step 有 5% 概率触发 → 约每 20,000 step（取决于你的 time_step）触发一次
    # 取值范围建议 1~200，便于控制频率

    burst_duration_steps: int = 1800
    # 一次促销持续的步数（例如 1800 step ≈ 30 分钟，如果 time_step=1）

    burst_peak_batch_size: int = 200
    # 促销期间每波最大订单数量

    burst_interval_steps: int = 5
    # 促销期间的波次间隔（非常密集，模拟高并发）

    total_orders_limit: Optional[int] = None