# WareRover

WareRover is an **AGV (Automated Guided Vehicle) warehouse simulation** project. It simulates multi-AGV order picking and delivery on a grid map with configurable schedulers, path planners, and order generation strategies.

## Features

- **Multi-AGV simulation**: Heterogeneous AGVs (different sizes), wait zones, boxes, receivers, and obstacles.
- **Schedulers**: Assign tasks to idle AGVs (e.g. random matching, cost-based Hungarian assignment).
- **Planners**: Centralized path planning with conflict avoidance (A* with reservation table, fixed-window CBS, or learned DHC policy).
- **Order generation**: One-shot or continuous modes (constant, periodic, Pareto, burst) with configurable size ratios.
- **Fault handling**: Optional AGV faults and repair; dynamic occupancy for repair paths.
- **Visualization**: Web frontend over HTTP + WebSocket for real-time view and control (pause, step, reset, stop).

## Project structure

```
WareRover/
├── run.py                 # Entry: starts HTTP server + WebSocket + simulator loop
├── config/
│   ├── settings.py       # SimConfig, FaultConfig, algorithm/map/order options
│   └── maps/             # JSON map files (grid, boxes, receivers, wait_zones, obstacles, agvs)
├── core/
│   ├── agv.py            # AGV model (grid/real pos, task queue, actions: PICK/PLACE/HANDOVER)
│   ├── agvmanager.py     # AGV pool, idle/rest/replan sets, task and path assignment
│   ├── env.py            # Step logic: conflict resolution, movement, action execution
│   ├── gridmap.py        # Static/dynamic map, walkability, box/receiver/wait zones
│   ├── order.py          # Order dataclass
│   ├── ordermanager.py   # Unprocessed / processing / finished orders; timeouts
│   ├── simulator.py      # Main loop: order step, assign tasks, assign rest, replan, env step
│   ├── fault_manager.py  # Fault injection, repair, repair path planning
│   └── data_generator.py # Builds frontend payload (init/update) in real coordinates
├── scheduler/
│   ├── base_scheduler.py   # Abstract: assign_tasks(idle_agv_ids, planner), assign_rest_areas, reset
│   ├── random_scheduler.py # Random matching by size
│   └── TA_scheduler.py     # Cost-based (Hungarian) assignment per size/goods group
├── planner/
│   ├── base_planner.py      # Abstract: plan(targets, scheduler) -> paths (exclude start)
│   ├── astar_planner.py     # A* with reservation table (vertex/edge conflict avoidance)
│   ├── cbs_fw_planner.py    # Fixed-window CBS
│   └── dhc_planner.py       # DHC learned policy (requires trained model)
├── order_strategies/        # OrderGenerationStrategy: update(step) -> new orders
├── algorithm/DHC/           # DHC training and model (optional)
├── frontend/                # HTML/CSS/JS + WebSocket client
├── utils/                   # Logger, simulation clock, algorithm_factory, base_utils
└── test/                    # single_run.py (batch runs), auto_experiment_runner.py (full grid)
```

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
   python -m test.single_run --runs 10 --seed 42 --out_dir test
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
