## LLM 环境配置 JSON 格式（运行时覆盖用）

本文件定义 MAPF Agent 在对话中生成和保存的 **环境配置 JSON** 结构，用于在不修改 `config/settings.py` 的前提下，覆盖默认仿真配置。

### 顶层结构

```json
{
  "meta": {
    "version": 1,
    "description": "optional human summary",
    "created_at": "2026-03-17T12:00:00Z",
    "created_by": "llm"
  },
  "config": {
    "sim": { /* 对应 SimConfig 字段（可选覆盖） */ },
    "fault": { /* 对应 FaultConfig 字段（可选覆盖） */ },
    "order_modes": {
      "oneshot": { /* 对应 OneShotConfig 字段（通常为空） */ },
      "continuous_constant": { /* 对应 ContinuousConstantConfig 字段 */ },
      "continuous_periodic": { /* 对应 ContinuousPeriodicConfig 字段 */ },
      "continuous_pareto": { /* 对应 ContinuousParetoConfig 字段 */ },
      "continuous_burst": { /* 对应 ContinuousBurstConfig 字段 */ }
    }
  }
}
```

### 字段与 `config/settings.py` 的映射

- `config.sim` → `SimConfig` 中的字段，字段名保持一致，例如：
  - `scheduler_type`: `"random"` / `"ta"`
  - `planner_type`: `"astar"` / `"cbs_fw"` / `"dhc"`
  - `order_mode`: `"oneshot"` / `"continuous_constant"` / `"continuous_periodic"` / `"continuous_pareto"` / `"continuous_burst"`
  - 以及 `map_file`, `max_steps`, `time_step`, `agv_max_speed`, `agv_turn_time_90`, `log_*` 等。
- `config.fault` → `FaultConfig` 中的字段：
  - `enable_faults`, `fault_prob`, `mean_repair_time`, `allow_multiple_faults`, `fault_seed`。
- `config.order_modes` → 各模式专用 dataclass：
  - `oneshot` → `OneShotConfig`（目前无字段，可留空 `{}`）。
  - `continuous_constant` → `ContinuousConstantConfig`（如 `batch_size`, `generation_interval_steps`）。
  - `continuous_periodic` → `ContinuousPeriodicConfig`。
  - `continuous_pareto` → `ContinuousParetoConfig`。
  - `continuous_burst` → `ContinuousBurstConfig`。

### 可选字段与默认值

- JSON 中 **只需要填写希望覆盖的字段**。
- 未出现在 JSON 中的字段，运行时会使用 `config/settings.py` 中 dataclass 的默认值。
- `null` 会被解释为 `None`（对应 Python 的 `Optional[...]` 字段）。

### 枚举与类型规则

- 枚举字段统一使用 **枚举的 `.value` 字符串**：
  - `SchedulerType`: `"random"`, `"ta"`。
  - `PlannerType`: `"astar"`, `"cbs_fw"`, `"dhc"`。
  - `OrderMode`: `"oneshot"`, `"continuous_constant"`, `"continuous_periodic"`, `"continuous_pareto"`, `"continuous_burst"`。
- 运行时会把这些字符串安全地转换回枚举类型，非法值会导致错误。
- 其他类型：
  - `int`, `float`, `bool`, `str` 使用正常 JSON 类型。
  - `Optional[...]` 字段可以省略（使用默认值）或显式给 `null`。

### 地图文件与配置文件的关系

- 地图 JSON 与环境配置 JSON 分离存储：
  - 地图文件示例：`config/maps/generated/map_user_001.json`。
  - 配置文件示例：`config/envs/runtime/user_001_config.json`。
- 关联通过 `config.sim.map_file` 完成，例如：

```json
{
  "meta": { "version": 1 },
  "config": {
    "sim": {
      "map_file": "config/maps/generated/map_user_001.json",
      "planner_type": "cbs_fw",
      "scheduler_type": "ta",
      "order_mode": "continuous_pareto",
      "max_steps": 2000
    }
  }
}
```

### 合并与优先级（供实现参考）

运行时合并顺序（高优先级在上）：

1. **会话内的即时覆盖**（如 workflow 中的 `sim_config_delta`）。
2. **环境配置 JSON（本格式）里的字段**。
3. **`config/settings.py` 中各 dataclass 的默认值**。

LLM 在生成配置文件时，只需要遵守本文件的字段命名和取值约定，其余字段将由默认配置补全。

