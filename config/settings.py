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
    """All supported order generation modes"""
    ONESHOT = "oneshot"                          # Generate all orders at once (original mode)
    CONTINUOUS_CONSTANT = "continuous_constant"  # Continuous steady generation
    CONTINUOUS_PERIODIC = "continuous_periodic"  # Periodic busy-idle waves
    CONTINUOUS_PARETO = "continuous_pareto"      # Pareto-distributed hot SKU pattern
    CONTINUOUS_BURST = "continuous_burst"        # Random burst promotion pattern


@dataclass
class SimConfig:
    """Simulation configuration parameters"""

    # ==================== Algorithm selection ====================
    scheduler_type: SchedulerType = SchedulerType.RANDOM
    planner_type: PlannerType = PlannerType.ASTAR
    force_replan_every_step: bool = False
    # Whether to force each decision-making AGV to replan its path at every step.
    # Automatically coupled with DHC when enabled.

    dhc_model_path: str = '.\\algorithm\\DHC\\models\\36000.pth'

    # ==================== Simulation parameters ====================
    order_mode: OrderMode = OrderMode.CONTINUOUS_CONSTANT  # Order generation mode
    total_orders_limit = 150

    size2_ratio: float = 0.2
    # Proportion of size-2 orders among all orders, range: 0.0 ~ 1.0

    order_processing_timeout: int = 30
    # Order processing timeout in seconds.
    # Orders not completed within this time will be returned to the pending queue.

    order_seed: Optional[int] = None
    # Random seed for order generation; None means non-deterministic

    # Map and simulation step configuration
    map_file: str = "config/maps/map_25_20_het.json"  # Default map file path
    max_steps: int = 1000

    time_step: float = 1.0        # Duration of each simulation step (seconds)
    agv_max_speed: float = 1      # Maximum AGV speed (cells per step)
    agv_turn_time_90: float = 0   # Time required for a 90-degree turn (seconds)

    # ==================== Frontend visualization ====================
    cell_size: int = 40
    panel_width: int = 300

    # ==================== Logging ====================
    log_to_file: bool = True
    log_dir: str = "logs"
    log_file_name: str = "simulation.log"

    # Whether to overwrite existing log files on reset; False means append
    log_overwrite: bool = True
    log_to_console: bool = False


# ==================== Fault management configuration ====================
@dataclass
class FaultConfig:
    enable_faults: bool = True

    # Fault probability per AGV per step
    fault_prob: float = 0.01

    # Mean repair time (in steps)
    mean_repair_time: int = 40

    # Whether multiple AGVs are allowed to fail simultaneously
    allow_multiple_faults: bool = False

    fault_seed: Optional[int] = 42
    # Random seed for fault generation; None means non-deterministic


# ==================== Mode-specific configuration dataclasses ====================
@dataclass
class OneShotConfig:
    """One-shot order generation mode (original mode)"""
    # All orders are generated once before the simulation starts


@dataclass
class ContinuousConstantConfig:
    """Continuous steady order generation mode"""

    batch_size: int = 10
    # Number of orders generated per batch

    generation_interval_steps: int = 50
    # Number of steps between batches
    # For example, if time_step = 1.0 second, this corresponds to one batch every 50 seconds


@dataclass
class ContinuousPeriodicConfig:
    """Periodic wave-based generation mode (alternating busy and idle periods)"""

    base_batch_size: int = 10
    # Average / low-demand batch size

    generation_interval_steps: int = 20
    # Base interval between waves (in steps);
    # actual batch size fluctuates over the cycle

    cycle_duration_steps: int = 80
    # Duration of a full peak-to-valley cycle (in steps)
    # Example: if time_step = 1.0, then 1800 steps = 30 minutes per cycle

    peak_multiplier: float = 3.0
    # Order volume multiplier during peak periods
    # (e.g., 3.0 → 60 orders per wave)

    valley_multiplier: float = 0.3
    # Order volume multiplier during valley periods
    # (e.g., 0.3 → 6 orders per wave)

    wave_type: str = "sine"  # Options: "sine" (smooth sinusoidal) or "square" (square wave)
    # "sine": smooth and realistic demand fluctuation
    # "square": sharp alternation between peak and valley, suitable for stress testing


@dataclass
class ContinuousParetoConfig:
    alpha: float = 2.0
    # Shape parameter of the Pareto distribution (typical range: 1.5–3.0).
    # Smaller values result in higher variance.

    scale: float = 10.0
    # Scaling factor controlling the average batch size ≈ scale / (alpha - 1)

    generation_interval_steps: int = 30

    hot_sku_percentage: float = 0.2
    # Proportion of hot SKUs (e.g., 20%)

    hot_sku_multiplier: float = 5.0
    # Currently used in a simplified manner,
    # retained for future fine-grained control


@dataclass
class ContinuousBurstConfig:
    base_batch_size: int = 10
    generation_interval_steps: int = 60

    burst_probability_per_1000_steps: int = 50
    # Probability of triggering a burst per 1000 steps (per-mille)

    burst_duration_steps: int = 1800
    # Duration of a promotion burst

    burst_peak_batch_size: int = 50
    burst_interval_steps: int = 5
    # Interval between batches during a burst (very dense)

    total_orders_limit: Optional[int] = None
