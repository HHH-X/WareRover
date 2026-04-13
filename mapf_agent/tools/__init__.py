"""Tool registry and executor factory for codegen ReAct loop."""
from __future__ import annotations

import json
from typing import TYPE_CHECKING, Callable

from mapf_agent.tools import explore, run_code

if TYPE_CHECKING:
    from mapf_agent.state import AgentState

TOOL_DEFINITIONS = [
    {
        "type": "function",
        "function": {
            "name": "list_directory",
            "description": "列出项目目录下的文件和子目录",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "相对于项目根目录的路径，例如 'core' 或 'planner'",
                    }
                },
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": "读取项目中某个文件的内容（支持指定行范围）",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "相对于项目根目录的文件路径，例如 'core/agvmanager.py'",
                    },
                    "start_line": {
                        "type": "integer",
                        "description": "起始行号（从1开始），可选",
                    },
                    "end_line": {
                        "type": "integer",
                        "description": "结束行号，可选",
                    },
                },
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_class_signatures",
            "description": "提取Python文件中所有类的方法签名（不含实现代码），用于快速了解类的接口",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "相对于项目根目录的Python文件路径",
                    }
                },
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "test_code",
            "description": "提交生成的算法代码进行测试：加载到注册表并运行冒烟测试（50步仿真）。返回 '测试通过' 或错误信息。",
            "parameters": {
                "type": "object",
                "properties": {
                    "code": {
                        "type": "string",
                        "description": "完整的Python代码字符串",
                    }
                },
                "required": ["code"],
            },
        },
    },
]


def create_executor(
    algo_type: str, reg_name: str, state: "AgentState"
) -> Callable[[str, dict], str]:
    """Return a tool executor pre-configured with codegen context."""

    def execute(name: str, arguments: dict) -> str:
        if name in ("list_directory", "read_file", "get_class_signatures"):
            return explore.execute(name, arguments)
        if name == "test_code":
            return run_code.test_code(
                arguments["code"], algo_type, reg_name, state
            )
        return f"未知工具: {name}"

    return execute
