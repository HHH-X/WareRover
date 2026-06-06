# MAPF Agent Skill Reference

## Runtime Requirements

Run commands from the WareRover project root. The project must have the MAPF simulator, `mapf_agent`, and its Python dependencies installed.

LLM-backed actions use one unified configuration path for both MAPF Agent calls and OpenEvolve optimization. Defaults are defined in `mapf_agent/llm_config.py`; override them with environment variables when needed:

- `MAPF_AGENT_API_KEY`: OpenAI-compatible API key.
- `MAPF_AGENT_BASE_URL`: OpenAI-compatible base URL.
- `MAPF_AGENT_MODEL`: model name for normal agent calls.
- `MAPF_AGENT_EVOLVE_PRIMARY_MODEL`: optional model override for OpenEvolve.
- `MAPF_AGENT_EVOLVE_SECONDARY_MODEL`: optional secondary model for OpenEvolve.

The project also reuses common caller variables: `OPENAI_API_KEY`, `OPENAI_BASE_URL`, and `OPENAI_API_BASE`. If no key environment variable is available, put the API key in `api_key.txt` in the project root.

## JSON Bridge

Preferred command:

```bash
python -m mapf_agent.invoke --message "<natural language request>"
```

Pretty JSON:

```bash
python -m mapf_agent.invoke --message "<request>" --pretty
```

Request from JSON file:

```bash
python -m mapf_agent.invoke --input request.json --pretty
```

Request from stdin:

```bash
echo '{"message":"运行一次仿真"}' | python -m mapf_agent.invoke --input -
```

Request object shape:

```json
{
  "message": "生成一个 20x20 地图并运行仿真",
  "answers": ["补充回答 1", "补充回答 2"],
  "thread_id": "optional-stable-id"
}
```

`answers` is optional. The bridge consumes answers only while the workflow is waiting for input.

## Response Shape

The bridge returns the current `AgentSession` snapshot as JSON:

```json
{
  "thread_id": "session-id",
  "waiting_for_input": false,
  "question": null,
  "response": "仿真完成...",
  "error": "",
  "intents": [],
  "intent_index": 0,
  "current_intent": null,
  "map_file_path": "",
  "generated_code": {},
  "run_metrics": {},
  "optimize_result": {}
}
```

If `waiting_for_input` is `true`, ask the user `question` and retry with an `answers` array. If `error` is non-empty, surface it to the user and decide whether to retry with a clearer request.

## Supported Task Types

The underlying LangGraph workflow recognizes these task types:

- `map`: generate a WareRover map JSON file.
- `config`: update simulation configuration.
- `codegen`: generate planner or scheduler code.
- `optimize`: optimize planner, scheduler, or both with OpenEvolve.
- `run`: run the simulator and return metrics.

The user may combine tasks in one request, such as generating a map, changing the planner, and running the simulation. The workflow orders and executes the detected tasks.

## Output Locations

Generated artifacts are written under the project `output/` directory:

- Maps: `output/maps/`
- Generated code: `output/codegen/`
- OpenEvolve runs: `output/evolve/`

Always use returned paths from JSON instead of guessing filenames.

## Web UI

The skill does not require the Web UI. For manual observation, the project can still run:

```bash
python -m mapf_agent.server
```

The JSON bridge is preferred for external agent platforms because it is non-interactive and machine-readable.
