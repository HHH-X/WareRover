import numpy as np
from typing import Dict, Any, Tuple
from core.gridmap import GridMap
from core.agvmanager import AGVManager
from core.ordermanager import OrderManager
from utils.logger import global_logger
from utils.simulation_clock import clock

def to_real_position(pos: Tuple[int, int], size: int = 1) -> Tuple[float, float]:
    """Grid (logical) top-left to real center position, with size offset."""
    x, y = pos
    offset = (size - 1) / 2
    return (x + 0.5 + offset, y + 0.5 + offset)

def agv_to_real_center(real_pos: Tuple[float, float], size: int) -> Tuple[float, float]:
    """Convert AGV top-left to geometric center (size=1: +0.5; size>1: +size/2)."""
    if size <= 1:
        return real_pos
    offset = (size - 1) / 2.0
    return (real_pos[0] + offset, real_pos[1] + offset)

def generate_send_data(map: GridMap, agvmanager: AGVManager, ordermanager: OrderManager, data_type: str = "init") -> Dict[str, Any]:
    """Build frontend payload; all positions in real (center) coordinates."""
    data = {}
    if data_type == "init":
        data['type'] = 'init'
        data['map_size'] = {
            "width": map.width,
            "height": map.height
        }
        agvs_info = {}
        for agv in agvmanager.all_agvs():
            agv_id = agv.id
            real_pos = agv.real_pos
            size = agv.size
            center_pos = agv_to_real_center(real_pos, size)
            agvs_info[agv_id] = {
                "pos": center_pos,
                "size": size
            }

        data['agvs'] = agvs_info
        data['boxes'] = {
            bid: {
                "pos": to_real_position(pos, map.box_sizes.get(bid, 1)),
                "size": map.box_sizes.get(bid, 1)
            }
            for bid, pos in map.box_positions.items()
        }

        data['receivers'] = {
            rid: {
                "pos": to_real_position(pos, map.receiver_zones_size.get(rid, 1)),
                "size": map.receiver_zones_size.get(rid, 1)
            }
            for rid, pos in map.receiver_zones.items()
        }

        data['wait_zones'] = {
            wid: {
                "pos": to_real_position(pos, map.wait_zones_size.get(wid, 1)),
                "size": map.wait_zones_size.get(wid, 1)
            }
            for wid, pos in map.wait_zones.items()
        }
        
        data['obstacles'] = [to_real_position(pos) for pos in map.obstacles]

        # Initial order panel data
        data['orders'] = {
            "counts": {
                "unprocessed": len(ordermanager.unprocessed_orders),
                "processing": len(ordermanager.processing_orders),
                "completed": len(ordermanager.finished_orders),
            },
            "logs": {"generation": [], "assignment": [], "completion": []},
            "agv_progress": global_logger.get_agv_order_progress(agvmanager),
        }

    elif data_type == "update":
        data['type'] = 'update'
        agv_pos = {aid: agv_to_real_center(pos, agvmanager.get_agv_size(aid)) for aid, pos in agvmanager.get_all_real_positions().items()}
        data['agvs'] = agv_pos
        
        carrying_status = agvmanager.get_carried_box_ids()
        boxes_on_agv = {}
        boxes_on_shelf = {}
        for agv_id, b_id in carrying_status.items():
            if b_id is not None:
                boxes_on_agv[b_id] = agv_pos[agv_id]
        
        boxes_on_shelf_id_set = map.box_id_set - set(boxes_on_agv.keys())
        for b_id in boxes_on_shelf_id_set:
            shelf_pos = map.box_positions[b_id]
            real_pos = to_real_position(shelf_pos, map.box_sizes.get(b_id, 1))
            boxes_on_shelf[b_id] = real_pos
          
        data['boxes_on_agv'] = boxes_on_agv
        data['boxes_on_shelf'] = boxes_on_shelf

        safe_paths = {}
        for agv_id, occupied_set in map.dynamic_occupied.items():
            safe_paths[agv_id] = [to_real_position(pos) for pos in occupied_set]
        data['safe_paths'] = safe_paths
        data['metrics'] = global_logger.get_runtime_metrics(clock.now())

        # Order panel data
        data['orders'] = {
            "counts": {
                "unprocessed": len(ordermanager.unprocessed_orders),
                "processing": len(ordermanager.processing_orders),
                "completed": len(ordermanager.finished_orders),
            },
            "logs": global_logger.get_order_logs_for_panel(),
            "agv_progress": global_logger.get_agv_order_progress(agvmanager),
        }

    return data
