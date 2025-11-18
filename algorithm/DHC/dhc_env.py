# 文件名: dhc_agv_wrapper.py
import numpy as np
from typing import List, Dict, Tuple
from environment import Environment as BaseDHCEnv  # 你原来的 DHC environment.py（只为了继承部分属性）
from your_real_agv_env import YourRealAGVEnv         # ← 改成你的真实 AGV env 类名
from dhc_converter import DHCCompatibleConverter     # 我之前给你写的转换器


class DHCAVGWrapper:
    """
    完全模仿 DHC Environment 的接口，但底层使用你的真实仓库 AGV 环境
    可直接替换所有 DHC 训练代码中的 env = Environment(...)
    """
    def __init__(
        self,
        real_env: YourRealAGVEnv,
        obs_radius: int = 5,
        reward_fn: dict = None,
    ):
        self.real_env = real_env
        self.obs_radius = obs_radius
        
        # DHC 标准奖励（你可以根据真实任务调整）
        self.reward_fn = reward_fn or {
            'move': -0.05,
            'stay_off_goal': -0.1,
            'stay_on_goal': 0.0,
            'collision': -1.0,
            'finish': 10.0,
        }

        # 转换器
        self.converter = DHCCompatibleConverter(obs_radius=obs_radius)

        # 下面这些属性是为了完美兼容 DHC 训练脚本而伪造的
        self.num_agents = 0                     # 动态变化，每步更新
        self.map_size = (real_env.height, real_env.width)
        self.steps = 0
        self.last_actions = None                # 用于可选的 last_action 通道

    def reset(self, *args, **kwargs):
        # 调用你的真实环境 reset
        real_obs = self.real_env.reset(*args, **kwargs)
        
        self.steps = 0
        self._update_internal_state()
        
        # 返回 DHC 格式的观测
        return self.observe()

    def step(self, actions: List[int]) -> Tuple:
        """
        actions: List[int] 长度 = 当前需要决策的 AGV 数量，值 0~4
        返回: obs, rewards, done, info   （完全和 DHC 一致）
        """
        # 1. 把动作映射回真实 AGV 的 id
        active_ids = list(self.current_targets.keys())
        action_dict = {agv_id: actions[i] for i, agv_id in enumerate(active_ids)}

        # 2. 执行真实环境一步
        real_obs, real_rewards, done, info = self.real_env.step(action_dict)

        self.steps += 1
        self._update_internal_state()

        # 3. 构造 DHC 风格的奖励（只给活跃的 AGV，非活跃的补0）
        dhc_rewards = [0.0] * self.num_agents
        for i, agv_id in enumerate(active_ids):
            # 你可以在这里把 real_rewards 映射成 DHC 的奖励结构
            # 简单示例：碰撞就-1，成功到达就+10，每步-0.05
            if real_rewards.get(agv_id, 0) == "collision":
                dhc_rewards[i] = self.reward_fn['collision']
            elif real_rewards.get(agv_id, 0) == "success":
                dhc_rewards[i] = self.reward_fn['finish']
            else:
                dhc_rewards[i] = self.reward_fn['move']

        # 4. 判断整体 done（所有任务都完成了，或者你自己定义）
        overall_done = done  # 你可以改成 len(self.real_env.pending_tasks) == 0

        return self.observe(), dhc_rewards, overall_done, {'step': self.steps}

    def observe(self) -> Tuple[np.ndarray, np.ndarray]:
        """
        返回和 DHC 一模一样的 observe()
        obs:  (N_active, 6, 2*r+1, 2*r+1) bool
        pos:  (N_active, 2) int
        """
        obs, pos = self.converter.convert(
            static_grid=self.real_env.static_grid,           # (H, W)
            agv_positions=self.real_env.agv_positions,       # Dict[id -> (x,y)]
            targets=self.real_env.current_targets,           # Dict[id -> (curr, goal)]
        )
        return obs, pos

    def render(self):
        # 直接调用你的真实环境渲染，或者自己画
        self.real_env.render()

    def close(self):
        self.real_env.close()

    # ==================== 下面是为了 100% 兼容 DHC 训练脚本加的伪属性 ====================
    def _update_internal_state(self):
        """每步更新活跃 AGV 数量、last_actions 等"""
        self.num_agents = len(self.real_env.current_targets)
        if self.num_agents > 0:
            if self.last_actions is None or self.last_actions.shape[0] != self.num_agents:
                self.last_actions = np.zeros(
                    (self.num_agents, 5, 2*self.obs_radius+1, 2*self.obs_radius+1), dtype=bool
                )
        else:
            self.last_actions = np.zeros((0, 5, 1, 1), dtype=bool)

    # 伪造的属性，让 DHC 训练代码不报错
    @property
    def agents_pos(self):
        active_ids = list(self.real_env.current_targets.keys())
        return np.array([self.real_env.agv_positions[i] for i in active_ids])

    @property
    def goals_pos(self):
        active_ids = list(self.real_env.current_targets.keys())
        return np.array([self.real_env.current_targets[i][1] for i in active_ids])

    # 如果你想加 last_action 通道（强烈建议加！防止来回晃）
    def get_full_obs_with_last_action(self):
        obs, pos = self.observe()
        if obs.shape[0] == 0:
            return obs, pos
        # 扩展到 11 通道
        full_obs = np.concatenate([obs, self.last_actions[:obs.shape[0]]], axis=1)
        return full_obs, pos

    def update_last_actions(self, actions: List[int]):
        """在 step 后调用，更新 last_actions（和原 DHC 一样）"""
        if self.num_agents > 0:
            self.last_actions.fill(0)
            self.last_actions[np.arange(self.num_agents), actions] = 1