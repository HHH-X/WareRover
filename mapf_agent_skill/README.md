# MAPF Agent Skill

Cursor Agent Skill for using the WareRover MAPF Agent from another agent
session. The skill teaches an agent how to download WareRover, configure an
OpenAI-compatible model, invoke the non-interactive JSON bridge, and report
simulation or optimization results.

This repository is the skill package only. The simulator, MAPF Agent runtime,
and OpenEvolve integration live in:

https://github.com/HHH-X/WareRover

## Files

- `SKILL.md`: main skill instructions loaded by Cursor.
- `reference.md`: setup, JSON protocol, output fields, and troubleshooting.
- `examples.md`: common commands for map generation, simulation, code
  generation, and optimization.

## Quick Start

Download WareRover and run commands from the WareRover project root:

```bash
git clone https://github.com/HHH-X/WareRover.git
cd WareRover
python -m pip install -e .
python -m mapf_agent.invoke --message "运行一次仿真" --pretty
```

If editable install is unavailable in your checkout, install the missing
packages reported by Python and retry the bridge command.

## LLM Configuration

POSIX shell:

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

`OPENAI_API_KEY`, `OPENAI_BASE_URL`, and `OPENAI_API_BASE` are also reused by
WareRover when the `MAPF_AGENT_*` variables are not set.

## Typical Invocation

```bash
python -m mapf_agent.invoke \
  --message "生成一个 20x20、6 台 AGV 的地图，然后运行仿真" \
  --pretty
```

The command writes JSON to stdout and progress logs to stderr. Read
`waiting_for_input`, `question`, `response`, `map_file_path`, `generated_code`,
`run_metrics`, and `optimize_result` from the JSON response.
