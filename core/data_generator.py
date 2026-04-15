import numpy as np
from typing import Dict, Any, Tuple
from utils.simulation_context import SimulationContext


def to_frontend_pos(pos: Tuple[int, int], size: int = 1) -> Tuple[float, float]:
    """Convert grid (row, col) to frontend (x, y) where x=col-based, y=row-based."""
    row, col = pos
    offset = (size - 1) / 2
    return (col + 0.5 + offset, row + 0.5 + offset)


def agv_real_to_frontend(real_pos: Tuple[float, float], size: int) -> Tuple[float, float]:
    """Convert AGV real_pos (real_row, real_col) to frontend center (x, y)."""
    real_row, real_col = real_pos
    if size <= 1:
        return (real_col, real_row)
    offset = (size - 1) / 2.0
    return (real_col + offset, real_row + offset)


def generate_send_data(
    ctx: SimulationContext,
    data_type: str = "init",
) -> Dict[str, Any]:
    """Build frontend payload; supports multi-floor."""
    wmap = ctx.warehouse_map
    data = {}

    if data_type == "init":
        data['type'] = 'init'
        data['map_size'] = {
            "width": wmap.width,
            "height": wmap.height,
        }
        data['num_floors'] = wmap.num_floors

        floors_data = {}
        for fid in wmap.all_floor_ids():
            floor_grid = wmap.get_floor(fid)
            fd = {}

            fd['boxes'] = {
                str(bid): {
                    "pos": to_frontend_pos(pos, floor_grid.box_sizes.get(bid, 1)),
                    "size": floor_grid.box_sizes.get(bid, 1)
                }
                for bid, pos in floor_grid.box_positions.items()
            }

            fd['receivers'] = {
                str(rid): {
                    "pos": to_frontend_pos(pos, floor_grid.receiver_zones_size.get(rid, 1)),
                    "size": floor_grid.receiver_zones_size.get(rid, 1)
                }
                for rid, pos in floor_grid.receiver_zones.items()
            }

            fd['wait_zones'] = {
                str(wid): {
                    "pos": to_frontend_pos(pos, floor_grid.wait_zones_size.get(wid, 1)),
                    "size": floor_grid.wait_zones_size.get(wid, 1)
                }
                for wid, pos in floor_grid.wait_zones.items()
            }

            fd['obstacles'] = [to_frontend_pos(pos) for pos in floor_grid.obstacles]

            floors_data[str(fid)] = fd

        data['floors'] = floors_data

        agvs_info = {}
        for agv in ctx.agv_manager.all_agvs():
            center_pos = agv_real_to_frontend(agv.real_pos, agv.size)
            agvs_info[str(agv.id)] = {
                "pos": center_pos,
                "size": agv.size,
                "floor": agv.floor_id
            }
        data['agvs'] = agvs_info

        elevators_info = {}
        for eid, edef in wmap.elevator_defs.items():
            elevators_info[str(eid)] = {
                "pos": to_frontend_pos(edef.position),
                "floors": edef.connected_floors,
                "travel_time": edef.travel_time,
            }
        data['elevators'] = elevators_info

        data['orders'] = {
            "counts": {
                "unprocessed": len(ctx.order_manager.unprocessed_orders),
                "processing": len(ctx.order_manager.processing_orders),
                "completed": len(ctx.order_manager.finished_orders),
            },
            "logs": {"generation": [], "assignment": [], "completion": []},
            "agv_progress": ctx.logger.get_agv_order_progress(ctx.agv_manager),
        }

    elif data_type == "update":
        data['type'] = 'update'

        agv_pos = {}
        for aid, pos in ctx.agv_manager.get_all_real_positions().items():
            size = ctx.agv_manager.get_agv_size(aid)
            center = agv_real_to_frontend(pos, size)
            floor_id = ctx.agv_manager.get_agv_floor(aid)
            agv_pos[str(aid)] = {"pos": center, "floor": floor_id}
        data['agvs'] = agv_pos

        carrying_status = ctx.agv_manager.get_carried_box_ids()
        boxes_on_agv = {}
        for agv_id, b_id in carrying_status.items():
            if b_id is not None:
                agv_info = agv_pos[str(agv_id)]
                floor_id = ctx.agv_manager.get_agv_floor(agv_id)
                boxes_on_agv[str(b_id)] = {"pos": agv_info["pos"], "floor": floor_id}

        boxes_on_shelf = {}
        for fid in wmap.all_floor_ids():
            floor_grid = wmap.get_floor(fid)
            on_shelf_ids = floor_grid.box_id_set - {int(k) for k in boxes_on_agv.keys()}
            for b_id in on_shelf_ids:
                pos = floor_grid.box_positions.get(b_id)
                if pos is not None:
                    real_pos = to_frontend_pos(pos, floor_grid.box_sizes.get(b_id, 1))
                    boxes_on_shelf[str(b_id)] = {"pos": real_pos, "floor": fid}

        data['boxes_on_agv'] = boxes_on_agv
        data['boxes_on_shelf'] = boxes_on_shelf

        safe_paths = {}
        for fid in wmap.all_floor_ids():
            floor_grid = wmap.get_floor(fid)
            for key, occ_set in floor_grid.dynamic_occupied.items():
                safe_paths[key] = {
                    "path": [to_frontend_pos(pos) for pos in occ_set],
                    "floor": fid
                }
        data['safe_paths'] = safe_paths

        if ctx.elevator_manager:
            elev_status = {}
            for eid, elev in ctx.elevator_manager.elevators.items():
                elev_status[str(eid)] = {
                    "state": elev.state.name,
                    "current_box": elev.current_box_id,
                    "timer": elev.timer,
                    "pending_boxes": {str(f): b for f, b in elev.pending_boxes.items()},
                }
            data['elevators'] = elev_status

        data['metrics'] = ctx.logger.get_runtime_metrics(ctx.clock.now())

        data['orders'] = {
            "counts": {
                "unprocessed": len(ctx.order_manager.unprocessed_orders),
                "processing": len(ctx.order_manager.processing_orders),
                "completed": len(ctx.order_manager.finished_orders),
            },
            "logs": ctx.logger.get_order_logs_for_panel(),
            "agv_progress": ctx.logger.get_agv_order_progress(ctx.agv_manager),
        }

    return data
