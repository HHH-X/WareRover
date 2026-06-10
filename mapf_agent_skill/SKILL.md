---
name: mapf-agent
description: Use the WareRover MAPF Agent to generate MAPF warehouse maps, modify simulation config, run simulations, generate planner/scheduler code, and optimize algorithms with OpenEvolve. Use when the user mentions MAPF, WareRover, AGV simulation, warehouse maps, planner, scheduler, or algorithm optimization.
---

# MAPF Agent Skill

## Project

This skill controls the WareRover MAPF Agent. The skill repository only contains
agent instructions; the simulator and executable MAPF Agent live in:

`https://github.com/HHH-X/WareRover`

If the current workspace is not WareRover, clone it first, then run all commands
from the WareRover project root:

```bash
git clone https://github.com/HHH-X/WareRover.git
cd WareRover
python -m pip install -e .
python -m mapf_agent.invoke --message "运行一次仿真" --pretty
```

If editable install is unavailable, install the missing runtime packages reported
by Python, then retry the JSON bridge command.

## When To Use

Use this skill when the user asks to:

- Generate a MAPF/WareRover warehouse map.
- Modify simulation settings such as planner, scheduler, map file, max steps, order mode, or fault parameters.
- Run a MAPF simulation and report metrics.
- Open the simulator visualization page, or run a simulation with visualization.
- Generate planner or scheduler algorithm code.
- Optimize planner, scheduler, or both with OpenEvolve.

## Preferred Invocation

Call the non-interactive JSON bridge. It reuses the existing LangGraph workflow through `AgentSession`.

```bash
python -m mapf_agent.invoke --message "生成一个 20x20、6 台 AGV 的地图，然后运行仿真" --pretty
```

The command writes machine-readable JSON to stdout. Internal progress logs are written to stderr.

When the user asks to open or show simulation visualization, the calling agent
must add `--visualize`:

```bash
python -m mapf_agent.invoke --message "打开仿真可视化并运行一次仿真" --visualize --pretty
```

This opens the existing simulator frontend and streams frames while the run task executes.

## LLM Configuration

Before invoking LLM-backed tasks, provide an OpenAI-compatible API through the caller's environment:

```bash
export MAPF_AGENT_API_KEY="..."
export MAPF_AGENT_BASE_URL="https://api.example.com/v1"
export MAPF_AGENT_MODEL="model-name"
```

PowerShell:

```powershell
$env:MAPF_AGENT_API_KEY = "..."
$env:MAPF_AGENT_BASE_URL = "https://api.example.com/v1"
$env:MAPF_AGENT_MODEL = "model-name"
```

Existing `OPENAI_API_KEY`, `OPENAI_BASE_URL`, and `OPENAI_API_BASE` values are also reused. For local development, `api_key.txt` in the project root is accepted when no key environment variable is set.

## Follow-Up Questions

If the result contains `waiting_for_input: true`, ask the user for the missing information, then call again with answers:

```bash
python -m mapf_agent.invoke \
  --message "生成一个地图" \
  --answers '["20x20，6 台 AGV，包含货架和接收点"]' \
  --pretty
```

## Important Fields

Read these fields from the JSON result:

- `waiting_for_input`: whether more user input is required.
- `question`: follow-up question to ask the user.
- `response`: final human-readable response.
- `error`: error message, if any.
- `map_file_path`: generated map path.
- `generated_code`: generated planner/scheduler paths.
- `run_metrics`: simulation metrics.
- `optimize_result`: OpenEvolve optimization result.
- `visualization`: simulator visualization status and URL, when visualization is requested.

## More Details

- For the complete JSON protocol, see [reference.md](reference.md).
- For task examples, see [examples.md](examples.md).
