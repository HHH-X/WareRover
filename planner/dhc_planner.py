# planner/dhc_planner.py
import torch
import numpy as np
from typing import Dict, Tuple, List, Set
from collections import defaultdict
import os

from core.env import Env
from core.gridmap import GridMap
from core.ordermanager import OrderManager
from core.fault_manager import FaultManager
from core.agvmanager import AGVManager
from planner.base_planner import BasePlanner
from algorithm.DHC.dhc_converter import DHCCompatibleConverter
from algorithm.DHC.model import Network
from algorithm.DHC.dhc_env import ACTION_DELTA

class DHCPlanner(BasePlanner):
    """
    DHC (learned) policy planner; relies on env for conflict rejection, no reservation checks.
    """
    def __init__(
        self,
        env: Env,
        agv_manager: AGVManager,
        order_manager: OrderManager,
        map: GridMap,
        fault_manager: FaultManager,
        model_path: str,
        forward_steps: int = 6,
        device: str = "cuda" if torch.cuda.is_available() else "cpu"
    ):
        super().__init__(env, agv_manager, order_manager, map, fault_manager)
        self.device = device
        self.forward_steps = forward_steps
        self.converter = DHCCompatibleConverter(num_agvs=self.env.agv_manager.num_agvs, gridmap=self.env.map, agvmanager=self.env.agv_manager)
        self.model = Network().to(self.device)
        self.model.eval()
        if not os.path.exists(model_path):
            raise FileNotFoundError(f"DHC model not found: {model_path}")
        state_dict = torch.load(model_path, map_location=device)
        self.model.load_state_dict(state_dict)
        print(f"[DHCPlanner] Loaded weights: {model_path}")

    def plan(
        self, 
        targets: Dict[int, Tuple[Tuple[int, int], Tuple[int, int]]],
        scheduler
    ) -> Dict[int, List[Tuple[int, int]]]:
        """
        Input: targets {agv_id: (current_pos, goal_pos)}.
        Output: {agv_id: [next_pos1, next_pos2, ...]} with length <= forward_steps.
        """
        if not targets:
            return {}
        env_info = self.env.get_env_info()
        static_grid = env_info['static_grid']
        current_positions = env_info['current_grid_pos']
        obs_dhc, pos_dhc = self.converter.convert(
            static_grid=static_grid,
            agv_positions_xy=current_positions,
            targets=targets
        )
        with torch.no_grad():
            obs_tensor = torch.from_numpy(obs_dhc).float().to(self.device)
            pos_tensor = torch.from_numpy(pos_dhc).long().to(self.device)
            actions, _, _, _ = self.model.step(obs_tensor, pos_tensor)
        paths: Dict[int, List[Tuple[int, int]]] = {}
        active_ids = list(targets.keys())
        for idx, agv_id in enumerate(active_ids):
            start_x, start_y = targets[agv_id][0]
            dx, dy = ACTION_DELTA[actions[idx]]
            path = []
            cur_x, cur_y = start_x, start_y
            for _ in range(self.forward_steps):
                next_x = cur_x + dx
                next_y = cur_y + dy
                path.append((next_x, next_y))
                cur_x, cur_y = next_x, next_y
            paths[agv_id] = path
        return paths