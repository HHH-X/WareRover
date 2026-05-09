"""Map generation node: LLM generates a map JSON validated against schema."""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Dict

import jsonschema
import yaml

from mapf_agent.llm import chat_json
from mapf_agent.paths import output_dir
from mapf_agent.state import AgentState

_BASE = Path(__file__).resolve().parent.parent
_SCHEMA_PATH = _BASE / "schema" / "map_schema.json"
_DEFAULTS_PATH = _BASE / "schema" / "map_defaults.yaml"
_PROMPT_PATH = _BASE / "prompts" / "map_gen.txt"


def _load_resources():
    schema = json.loads(_SCHEMA_PATH.read_text(encoding="utf-8"))
    defaults = yaml.safe_load(_DEFAULTS_PATH.read_text(encoding="utf-8"))
    prompt_tpl = _PROMPT_PATH.read_text(encoding="utf-8")
    return schema, defaults, prompt_tpl


def _build_prompt(user_detail: str) -> tuple[str, dict]:
    schema, defaults, tpl = _load_resources()
    system_prompt = tpl.format(
        defaults=yaml.dump(defaults.get("defaults", {}), allow_unicode=True),
        required="\n".join(f"- {r}" for r in defaults.get("required", [])),
        notes=defaults.get("notes", ""),
        schema=json.dumps(schema, indent=2, ensure_ascii=False),
    )
    return system_prompt, schema


def map_gen_node(state: AgentState) -> Dict:
    intents = state.get("intents") or []
    idx = state.get("intent_index", 0)
    detail = intents[idx].get("detail", "") if idx < len(intents) else ""

    print("[地图生成] 正在生成地图...")
    system_prompt, schema = _build_prompt(detail)
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": detail},
    ]

    result = chat_json(messages, max_tokens=8192)

    if "error" in result and result["error"] == "missing_info":
        missing = ", ".join(result.get("missing", []))
        return {"error": f"NEED_INPUT:生成地图缺少必要信息: {missing}，请补充。"}

    try:
        jsonschema.validate(instance=result, schema=schema)
    except jsonschema.ValidationError as exc:
        print("[地图生成] 数据校验失败")
        return {"error": f"地图数据校验失败: {exc.message}"}

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    w, h = result["map"]["width"], result["map"]["height"]
    if "floors" in result:
        n_agv = sum(len(f.get("agvs", [])) for f in result["floors"])
    else:
        n_agv = len(result.get("agvs", []))
    filename = f"map_{w}_{h}_{n_agv}agv_{timestamp}.json"
    out_path = output_dir("maps") / filename
    out_path.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")

    print(f"[地图生成] 完成 — {w}×{h} 地图, {n_agv} 台AGV → {filename}")
    return {"map_file_path": str(out_path), "error": ""}
