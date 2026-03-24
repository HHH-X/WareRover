"""Agent-side configuration: LLM model, paths, and defaults."""
from dataclasses import dataclass
import os

PACKAGE_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(PACKAGE_DIR)

# 唯一 API key 来源：mapf_agent/api_key（已加入 .gitignore）
API_KEY_FILE = os.path.join(PACKAGE_DIR, "api_key")


def _read_api_key_file() -> str:
    """从 api_key 文件读取第一行作为 key，不存在或为空则返回空字符串。"""
    if not os.path.isfile(API_KEY_FILE):
        return ""
    try:
        with open(API_KEY_FILE, "r", encoding="utf-8") as f:
            line = f.readline()
        return (line or "").strip()
    except OSError:
        return ""


@dataclass
class AgentConfig:
    """Configuration for MAPF Agent (LLM, paths, limits)."""

    # LLM provider & model
    llm_provider: str = "openai"
    llm_model: str = "DeepSeek-V3.2"
    llm_base_url: str = "https://api.modelarts-maas.com/v1"
    llm_temperature: float = 0.2
    llm_max_tokens: int = 4096

    # Paths
    knowledge_dir: str = ""
    prompts_dir: str = ""
    generated_planners_dir: str = ""
    map_path: str = os.path.join(PACKAGE_DIR, "generated", "envs", "generated_map.json")
    sim_config_path: str = os.path.join(PACKAGE_DIR, "generated", "envs", "generated_sim_config.json")

    # Validation
    validate_map_trial_steps: int = 0

    # Simulation tool
    default_simulation_seed: int = 42
    default_simulation_runs: int = 1
    default_max_steps: int = 1000

    def __post_init__(self):
        if not self.knowledge_dir:
            self.knowledge_dir = os.path.join(PACKAGE_DIR, "knowledge")
        if not self.prompts_dir:
            self.prompts_dir = os.path.join(PACKAGE_DIR, "prompts")
        if not self.generated_planners_dir:
            self.generated_planners_dir = os.path.join(PACKAGE_DIR, "generated_planners")

    def get_api_key(self) -> str:
        """API key 仅从 mapf_agent/api_key 文件读取。"""
        return _read_api_key_file()


agent_config = AgentConfig()
