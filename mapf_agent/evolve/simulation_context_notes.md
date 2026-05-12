# Simulation Context Notes

Candidate planner and scheduler classes receive `self.ctx`, a populated `SimulationContext`.
Use these objects to inspect the current simulation state and to build feasible paths or task
sequences. All grid positions use `(row, col)` tuples.

## Context objects

- `ctx.system_config`: simulation and scoring configuration.
- `ctx.logger`: runtime logs and final metrics.
- `ctx.clock`: simulation clock; `ctx.clock.now()` returns the current step.
- `ctx.warehouse_map`: multi-floor map, boxes, receivers, wait zones, and elevators.
- `ctx.order_manager`: generated orders and order lifecycle state.
- `ctx.agv_manager`: all AGV instances, positions, sizes, tasks, and replan state.
- `ctx.env`: walkability queries, environment snapshots, and conflict-resolved stepping.
- `ctx.elevator_manager`: elevator lookup, queues, and cross-floor state.
- `ctx.fault_manager`: AGV fault state; faults can make AGVs unavailable and occupy cells.
- `ctx.scheduler`, `ctx.planner`, `ctx.simulator`: current algorithm and simulator objects.

Planner and scheduler constructors assert that the key dependencies above are available.
Prefer public manager/query methods, and avoid mutating subsystem internals unless the base
interface explicitly expects it.

## Coordinates and map structure

`ctx.warehouse_map` is a `WarehouseMap` containing one `GridMap` per floor:

- `width`, `height`, `num_floors`: map dimensions.
- `floors: Dict[int, GridMap]`: floor id to `GridMap`.
- `elevator_defs: Dict[int, ElevatorDef]`: static elevator definitions.
- `get_floor(floor_id) -> GridMap`.
- `all_floor_ids() -> List[int]`.
- `get_box_floor(box_id) -> Optional[int]`.
- `get_receiver_floor(receiver_id) -> Optional[int]`.
- `get_box_position(box_id) -> Optional[Tuple[int, int]]`.
- `get_receiver_position(receiver_id) -> Optional[Tuple[int, int]]`.
- `get_goods_by_box(box_id) -> List[int]`.
- `get_boxes_by_goods(goods_id) -> List[int]`.
- `get_all_goods_ids() -> Set[int]`.
- `get_all_receiver_zone_ids() -> Set[int]`.
- `get_elevator_position(elevator_id) -> Optional[Tuple[int, int]]`.

Use `WarehouseMap` for cross-floor queries. Use `GridMap` when you already know the floor and
need per-floor details.

## GridMap details

Each `GridMap` represents one floor. Grid arrays have shape `(height, width)`.

Important fields:

- `floor_id`, `width`, `height`.
- `type_grid`: numpy grid of `CellType.FREE`, `OBSTACLE`, `SHELF`, or `ELEVATOR`.
- `shelf_id_grid`: shelf/box id for shelf cells, otherwise `-1`.
- `elevator_id_grid`: elevator id for elevator cells, otherwise `-1`.
- `box_positions: Dict[int, Tuple[int, int]]`.
- `box_sizes: Dict[int, int]`.
- `box_to_goods: Dict[int, List[int]]`.
- `box_status: Dict[int, bool]`; `True` means the box is currently on its shelf.
- `goods_to_boxes: Dict[int, List[int]]`.
- `receiver_zones: Dict[int, Tuple[int, int]]`.
- `wait_zones: Dict[int, Tuple[int, int]]`.
- `elevator_positions: Dict[int, Tuple[int, int]]`.
- `dynamic_occupied`: cells temporarily blocked by faults or other dynamic effects.

Useful methods:

- `is_walkable(agv_id, to_pos, from_pos, carrying_goods) -> bool`: validates a single
  four-neighbor move for the AGV size, map bounds, obstacles, shelf/elevator rules, and
  dynamic occupancy. Entering an elevator cell is only walkable when the AGV next task is
  `AGVAction.ENTER_ELEVATOR` for that same elevator.
- `get_walkable_neighbors(agv_id, pos, carrying_goods) -> List[Tuple[int, int]]`.
- `pick_box_at(pos) -> Optional[int]`: marks a present box as picked and returns its id.
- `place_box_at(pos, box_id) -> bool`: puts the carried box back at its original shelf.
- `get_all_box_status() -> Dict[int, bool]`.
- `get_box_position(box_id)`, `get_goods_by_box(box_id)`, `get_boxes_by_goods(goods_id)`.
- `get_receiver_position(receiver_id)`, `get_wait_zone_position(zone_id)`.
- `get_elevator_position(elevator_id)`, `get_elevator_cells(elevator_id)`.

AGV size matters. A size-2 AGV occupies a `2x2` footprint whose top-left cell is its `grid_pos`.
The walkability helpers already account for this footprint.

## Environment queries

`ctx.env` is the safest entry point for planner walkability:

- `get_env_info() -> dict`: global snapshot with `carrying_status`, `action_queues`,
  `current_grid_pos`, `agv_sizes`, and `agv_floors`.
- `get_env_info_for_floor(floor_id) -> dict`: per-floor snapshot with `type_grid`,
  `shelf_id_grid`, `elevator_id_grid`, `carrying_status`, `action_queues`,
  `current_grid_pos`, and `agv_sizes`.
- `get_walkable_neighbors(agv_id, pos, carrying_goods) -> List[Tuple[int, int]]`.
- `is_walkable(agv_id, to_pos, from_pos, carrying_goods) -> bool`.

The simulator later calls `env.step()`, which resolves vertex/edge conflicts per floor and then
steps AGVs. Candidate algorithms normally should not call `env.step()` directly.

## AGV manager and AGV state

`ctx.agv_manager` owns all AGVs:

- `_agvs: Dict[int, AGV]`: runtime AGV objects. Prefer `get_agv(agv_id)` for access.
- `idle_agvs`, `need_rest_agvs`, `need_replan_agvs`: sets of AGV ids.
- `agv_sizes: Dict[int, int]`, `agv_floors: Dict[int, int]`.
- `num_agvs`, `all_agv_ids`.

Useful query methods:

- `get_agv(agv_id) -> AGV`.
- `get_agv_floor(agv_id) -> int`.
- `get_agvs_on_floor(floor_id) -> Set[int]`.
- `get_grid_position(agv_id) -> Tuple[int, int]`.
- `get_real_position(agv_id) -> Tuple[float, float]`.
- `get_agv_size(agv_id) -> int`.
- `get_agv_ids_by_size(size) -> Set[int]`.
- `get_agv_footprint_cells(agv_id) -> Set[Tuple[int, int]]`.
- `get_idle_agv_ids()`, `get_idle_agv_ids_on_floor(floor_id)`.
- `get_need_replan_agv_ids()`, `get_need_rest_agv_ids()`.
- `get_carrying_status() -> Dict[int, bool]`.
- `get_carried_box_ids() -> Dict[int, Optional[int]]`.
- `get_all_current_pos()`, `get_all_next_pos()`, `get_all_action_queues()`.
- `get_current_pos_on_floor(floor_id)`, `get_next_pos_on_floor(floor_id)`,
  `get_action_queues_on_floor(floor_id)`.
- `get_replan_targets() -> Dict[int, Tuple[Tuple[int, int], Tuple[int, int]]]`: maps each
  AGV needing replanning to `(current_pos, target_pos)`. The target is the next task position
  or the rest target. AGVs inside elevators are skipped.

`AGV` objects expose useful state:

- `id`, `size`, `floor_id`, `init_floor_id`.
- `grid_pos`: current discrete top-left grid cell.
- `real_pos`: continuous center position used by movement and alignment checks.
- `task_queue`: deque of `(pos, AGVAction, extra)` tasks.
- `action_queue`: deque of future grid cells from the planner.
- `rest_target`: optional waiting-zone target.
- `carried_box_id`: current carried box id, or `None`.
- `is_working`: false when a fault disables the AGV.
- `in_elevator`, `elevator_phase`: elevator transition state.
- `is_idle`, `is_resting`, `is_aligned`: convenience properties.
- `get_next_pos() -> Tuple[int, int]`: first cell in `action_queue`, or current position.

Do not put the current cell at the beginning of a planner path unless you intentionally want the
AGV to stay. `BasePlanner.plan()` expects returned paths to exclude the start position.

## Orders and scheduling

`ctx.order_manager` tracks order lifecycle:

- `all_orders: List[Order]`.
- `unprocessed_orders: Dict[int, Order]`.
- `processing_orders: Dict[int, Order]`.
- `finished_orders: Dict[int, Order]`.
- `total_orders_limit`, `next_order_id`.

Useful methods:

- `get_unprocessed_orders() -> List[Order]`.
- `get_all_orders() -> List[Order]`.
- `mark_order_as_processing(order_id, agv_id) -> bool`: moves an order out of the
  unprocessed bucket and records assignment logs.
- `complete_order(order_id, agv_id, box_id, agv_pos) -> bool`: succeeds only when the carried
  box contains the requested goods and `agv_pos` equals the receiver position.
- `is_all_orders_completed() -> bool`.

`Order` fields:

- `order_id`, `goods_id`, `receiver_id`, `required_size`.
- `source_floor`, `target_floor`, `is_cross_floor`.
- `created_step`, `start_processing_step`, `finished_step`.

Schedulers should fill or use floor information before comparing same-floor and cross-floor
tasks. `BaseScheduler._fill_orders_floor_info(orders)` is available to set `source_floor`,
`target_floor`, and `is_cross_floor` from the map.

## Task tuples and AGVAction

Scheduler output maps `agv_id` to a list of task tuples:

`(target_pos: Tuple[int, int], action: AGVAction, extra: object)`

Actions:

- `AGVAction.PICK`: `extra` is usually `box_id`. At the shelf, AGV picks the box if sizes match.
- `AGVAction.HANDOVER`: `extra` is `order_id`. At the receiver, the order is completed if the
  carried box contains the requested goods.
- `AGVAction.PLACE`: `extra` is usually `None`. The AGV returns the box to its shelf.
- `AGVAction.ENTER_ELEVATOR`: `extra` must be `(elevator_id, target_floor)`.

A typical same-floor order is:

1. `(box_pos, AGVAction.PICK, box_id)`
2. `(receiver_pos, AGVAction.HANDOVER, order_id)`
3. `(box_pos, AGVAction.PLACE, None)`

A typical cross-floor order is:

1. `(box_pos, AGVAction.PICK, box_id)`
2. `(elevator_pos, AGVAction.ENTER_ELEVATOR, (elevator_id, target_floor))`
3. `(receiver_pos, AGVAction.HANDOVER, order_id)`
4. `(elevator_pos, AGVAction.ENTER_ELEVATOR, (elevator_id, source_floor))`
5. `(box_pos, AGVAction.PLACE, None)`

After an AGV finishes a task, it replans toward the next task position.

## Elevators

`ctx.elevator_manager` manages runtime elevator state:

- `elevators: Dict[int, Elevator]`.
- `find_elevator(from_floor, to_floor, agv_size=1) -> List[int]`: returns suitable elevator ids
  sorted by queue length. It filters by connected floors and exact AGV/elevator size match.
- `get_elevator(elevator_id) -> Optional[Elevator]`.
- `get_elevator_ids_by_size(size) -> List[int]`.
- `enqueue_task(elevator_id, agv_id, from_floor, to_floor) -> bool`.
- `can_agv_enter(agv_id, elevator_id, floor_id) -> bool`.
- `start_boarding(agv_id, elevator_id, floor_id) -> bool`.

`Elevator` state includes `state`, `current_floor`, `task_queue`, `current_task`, `agv_id`,
`target_floor`, and `display_floor`. Candidate schedulers usually only need `find_elevator()`
and map elevator positions.

## Planner-specific guidance

`BasePlanner.plan(targets, scheduler)` receives:

- `targets: Dict[int, Tuple[start_pos, target_pos]]`.
- `scheduler`: the current scheduler instance, available if cooperative heuristics are useful.

Return `{agv_id: path}` where each path is a list of `(row, col)` cells and excludes the start
cell. Planning is effectively per floor because AGVs on different floors do not collide; use
`ctx.agv_manager.get_agv_floor(agv_id)` to group targets by floor.

Good planner inputs include:

- `ctx.agv_manager.get_replan_targets()`.
- `ctx.env.get_env_info_for_floor(floor_id)`.
- `ctx.env.get_walkable_neighbors(agv_id, pos, carrying_goods)`.
- Existing `action_queue`s from other AGVs as soft reservations.

## Scheduler-specific guidance

`BaseScheduler.assign_tasks(idle_agv_ids, planner)` should return tasks only for AGVs it wants
to assign. Useful scheduling steps are:

1. Read pending orders from `ctx.order_manager.get_unprocessed_orders()`.
2. Fill floor data with `_fill_orders_floor_info(orders)`.
3. For each order, use `ctx.warehouse_map.get_boxes_by_goods(order.goods_id)` and map queries to
   find feasible boxes and receiver positions.
4. Match AGV size with `order.required_size`, box size, and elevator size.
5. For cross-floor orders, call `ctx.elevator_manager.find_elevator(source_floor, target_floor, agv_size)`.
6. Call `ctx.order_manager.mark_order_as_processing(order.order_id, agv_id)` only for orders you
   actually assign.

Prefer feasible assignments over speculative ones. If no box, receiver, elevator, or compatible
AGV exists, leave the order unassigned for a later step.

## Faults and robustness

`ctx.fault_manager` may disable AGVs during simulation. A disabled AGV has `agv.is_working == False`
and may contribute dynamic occupied cells through `GridMap.dynamic_occupied`. Use `is_working`,
manager status queries, and walkability helpers instead of assuming every AGV can move.

## Important cautions

- Keep the public method signatures from `BasePlanner` and `BaseScheduler` unchanged.
- Do not change global simulation state from a planner except by returning paths.
- A scheduler may mark orders as processing only when it returns the corresponding task list.
- Use `(row, col)`, not `(x, y)`.
- Use walkability helpers for size, shelf, elevator, and fault rules.
- Returning an empty path means the AGV will stay until another replan.
