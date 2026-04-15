# planner/dhc_planner.py
import os
from collections import defaultdict
from typing import Dict, List, Set, Tuple

import torch

from planner.base_planner import BasePlanner
from utils.simulation_context import SimulationContext
from algorithm.DHC.dhc_converter import DHCCompatibleConverter
from algorithm.DHC.model import Network
from algorithm.DHC.dhc_env import ACTION_DELTA
import numpy as np


class DHCPlanner(BasePlanner):
    """
    DHC (learned) policy planner; relies on env for conflict rejection, no reservation checks.
    """
    def __init__(self, ctx: SimulationContext):
        super().__init__(ctx)
        self.env = ctx.env
        self.agv_manager = ctx.agv_manager
        self.order_manager = ctx.order_manager
        self.warehouse_map = ctx.warehouse_map
        self.fault_manager = ctx.fault_manager
        sim_cfg = ctx.system_config.sim_config
        model_path = sim_cfg.dhc_model_path
        self.device = "cuda" if torch.cuda.is_available() else "cpu"
        self.forward_steps = 1
        self.converter = DHCCompatibleConverter(
            num_agvs=self.env.agv_manager.num_agvs,
            gridmap=self.warehouse_map.get_floor(0),
            agvmanager=self.env.agv_manager,
        )
        self.model = Network().to(self.device)
        self.model.eval()
        if not os.path.exists(model_path):
            raise FileNotFoundError(f"DHC model not found: {model_path}")
        state_dict = torch.load(model_path, map_location=self.device)
        self.model.load_state_dict(state_dict)
        print(f"[DHCPlanner] Loaded weights: {model_path}")

    def plan(
        self, 
        targets: Dict[int, Tuple[Tuple[int, int], Tuple[int, int]]],
        scheduler
    ) -> Dict[int, List[Tuple[int, int]]]:
        if not targets:
            return {}
        env_info = self.env.get_env_info_for_floor(0)
        type_grid = env_info['type_grid']
        current_positions = env_info['current_grid_pos']
        obs_dhc, pos_dhc = self.converter.convert(
            type_grid=type_grid,
            agv_positions=current_positions,
            targets=targets
        )
        with torch.no_grad():
            obs_tensor = torch.from_numpy(obs_dhc).float().to(self.device)
            pos_tensor = torch.from_numpy(pos_dhc).long().to(self.device)
            actions, _, _, _ = self.model.step(obs_tensor, pos_tensor)
        paths: Dict[int, List[Tuple[int, int]]] = {}
        active_ids = list(targets.keys())
        for idx, agv_id in enumerate(active_ids):
            start_row, start_col = targets[agv_id][0]
            drow, dcol = ACTION_DELTA[actions[idx]]
            path = []
            cur_row, cur_col = start_row, start_col
            for _ in range(self.forward_steps):
                next_row = cur_row + drow
                next_col = cur_col + dcol
                path.append((next_row, next_col))
                cur_row, cur_col = next_row, next_col
            paths[agv_id] = path
        return paths
