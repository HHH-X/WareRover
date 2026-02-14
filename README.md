# WareRover

WareRover is an **AGV (Automated Guided Vehicle) warehouse simulation** project. It simulates multi-AGV order picking and delivery on a grid map with configurable schedulers, path planners, and order generation strategies.

## Features

- **Closed-Loop Joint Optimization**: A unified interface coupling order scheduling with MAPF, enabling the study of scheduling strategies that explicitly account for traffic and routing costs.
- **High-Fidelity Warehouse Modeling**: A topology-agnostic framework supporting customizable layouts, heterogeneous fleets, and realistic order streams
- **Resilience Evaluation**: Native support for simulating stochastic failures (e.g., breakdowns, delays), allowing researchers to benchmark algorithmic robustness against execution uncertainty.


## Requirements

- Python 3.10+
- Dependencies: see `config/settings.py` and imports (e.g. `numpy`, `scipy`, `websockets`, `torch` for DHC).

## Quick start

1. **Configure**  
   Edit `config/settings.py`: set `map_file`, `scheduler_type`, `planner_type`, `order_mode`, `total_orders_limit`, etc.

2. **Run with visualization**  
   ```bash
   python run.py
   ```  
   This starts an HTTP server (port 8000), opens the frontend in the browser, and runs the WebSocket server (port 8765) for the simulator. Use the UI to pause, step, reset, or stop.

3. **Batch experiments (no UI)**  
   ```bash
   python -m test.auto_experiment_runner
   ```  
   Or run the full grid of algorithm/scene combinations via `test/auto_experiment_runner.py` (adjust `NUM_RUNS`, `BASE_SEED`, `OUT_DIR`, and scene/algorithm lists as needed).

## Configuration summary

- **Scheduler**: `RANDOM` or `TA` (cost-based assignment).
- **Planner**: `ASTAR`, `CBS_FW`, or `DHC` (DHC needs `dhc_model_path` and enables `force_replan_every_step`).
- **Order mode**: `ONESHOT`, `CONTINUOUS_CONSTANT`, `CONTINUOUS_PERIODIC`, `CONTINUOUS_PARETO`, `CONTINUOUS_BURST`.
- **Map**: JSON under `config/maps/` with `map`, `boxes`, `receivers`, `wait_zones`, `obstacles`, `agvs`.

## Base interfaces

- **BaseScheduler**  
  - `assign_tasks(idle_agv_ids, planner)` → `{agv_id: [(position, action, extra), ...]}`  
  - `assign_rest_areas(agv_ids)` (default: wait zone per AGV)  
  - `reset()` (call after `order_manager.reset_order()`)

- **BasePlanner**  
  - `plan(targets, scheduler)` → `{agv_id: [path]}`  
  - `targets`: `{agv_id: (start_pos, goal_pos)}`  
  - Path must not include start; first element is the next cell. Use `env.get_env_info()` for `action_queues` and `current_grid_pos`.

## License

See repository for license information.
