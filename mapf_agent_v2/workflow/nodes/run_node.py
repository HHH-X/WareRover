from __future__ import annotations

from typing import Dict

from mapf_agent_v2.session.state import AgentState
from mapf_agent_v2.tools.run_tool import run_with_config


def run_node(state: AgentState) -> Dict:
    try:
        result = run_with_config(state["system_config"], runs=1, seed=42)
    except Exception as e:
        return {"error": str(e), "metrics": {}, "result_summary": f"运行失败: {e}"}

    metrics = result.get("metrics", {})
    return {
        "metrics": metrics,
        "error": "",
        "result_summary": f"运行完成，关键指标: {metrics}",
    }

