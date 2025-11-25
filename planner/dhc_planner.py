# planner/dhc_planner.py
import torch
import numpy as np
from typing import Dict, Tuple, List, Set
from collections import defaultdict
import os

from core.env import Env
from planner.base_planner import BasePlanner
from algorithm.DHC.dhc_wrapper import DHCCompatibleConverter
from algorithm.DHC.model import Network  # 注意：这是你训练的 DHC 模型

# 动作映射（和 DHCAVGWrapper 完全一致）
ACTION_DELTA = {
    0: (0,  0),   # stay
    1: (0, -1),   # up
    2: (0,  1),   # down
    3: (-1, 0),   # left
    4: (1,  0)    # right
}

class DHCPlanner(BasePlanner):
    """
    极简 DHC 策略规划器
    完全依赖底层 env 的冲突强制拒绝，不做任何 reservation 检查
    """
    def __init__(
        self,
        env_instance: Env,
        model_path: str,
        forward_steps: int = 6,           # 建议 4~8，越大路径越平滑
        device: str = "cuda" if torch.cuda.is_available() else "cpu"
    ):
        self.env = env_instance
        self.device = device
        self.forward_steps = forward_steps

        # DHC 观测生成器（和训练时 100% 一致）
        self.converter = DHCCompatibleConverter(obs_radius=4)

        # 加载训练好的模型
        self.model = Network().to(self.device)
        self.model.eval()
        if not os.path.exists(model_path):
            raise FileNotFoundError(f"DHC model not found: {model_path}")
        state_dict = torch.load(model_path, map_location=device)
        self.model.load_state_dict(state_dict)
        print(f"[DHCPlanner] Loaded weights: {model_path}")

    def plan(self, targets: Dict[int, Tuple[Tuple[int, int], Tuple[int, int]]]) -> Dict[int, List[Tuple[int, int]]]:
        """
        输入:  {agv_id: (current_pos, goal_pos)}
        输出:  {agv_id: [next_pos1, next_pos2, ...]}   # 长度 ≤ forward_steps
        """
        if not targets:
            return {}

        # 1. 获取全局状态
        env_info = self.env.get_env_info()
        static_grid = env_info['static_grid']
        current_positions = env_info['current_grid_pos']   # {agv_id: (x, y)}

        # 2. 生成 DHC 标准观测（只给需要决策的 AGV）
        obs_dhc, pos_dhc = self.converter.convert(
            static_grid=static_grid,
            agv_positions_xy=current_positions,
            targets=targets
        )

        # 3. 模型推理（一次性推理所有活跃 AGV）
        with torch.no_grad():
            obs_tensor = torch.from_numpy(obs_dhc).float().to(self.device)
            pos_tensor = torch.from_numpy(pos_dhc).long().to(self.device)
            actions, _, _, _ = self.model.step(obs_tensor, pos_tensor)
            # actions 是 list[int]，长度 = len(targets)

        # 4. 统一使用同一个动作向前走 forward_steps 步（或直到目标）
        paths: Dict[int, List[Tuple[int, int]]] = {}
        active_ids = list(targets.keys())

        for idx, agv_id in enumerate(active_ids):
            start_x, start_y = targets[agv_id][0]   # 当前位置（左上角）
            dx, dy = ACTION_DELTA[actions[idx]]

            path = []
            cur_x, cur_y = start_x, start_y
            for _ in range(self.forward_steps):
                next_x = cur_x + dx
                next_y = cur_y + dy
                path.append((next_x, next_y))
                cur_x, cur_y = next_x, next_y

            paths[agv_id] = path   # 即使后续被 env 拒绝也没关系，下次会重新规划

        return paths