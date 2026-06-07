# MAPF Agent Skill Examples

## Configure LLM Access

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

Then run any skill command from the project root. Existing `OPENAI_API_KEY` and OpenAI-compatible base URL variables are reused when the `MAPF_AGENT_*` variables are not set.

## Smoke Test The Bridge

Run this first after downloading WareRover and installing dependencies:

```bash
python -m mapf_agent.invoke --message "运行一次仿真" --pretty
```

Expected behavior: stdout is a JSON object. If `error` is non-empty, report it
and fix the missing configuration or dependency before running larger tasks.

## Generate A Map

```bash
python -m mapf_agent.invoke \
  --message "生成一个 20x20 的仓储地图，包含 6 台 AGV、货架、接收点和等待区" \
  --pretty
```

Use `map_file_path` from the JSON response as the generated map artifact.

## Configure And Run A Simulation

```bash
python -m mapf_agent.invoke \
  --message "使用 CBS planner 和 TA scheduler，最大步数设为 1000，然后运行仿真" \
  --pretty
```

Report `run_metrics` and `response` to the user.

## Generate A Map Then Run

```bash
python -m mapf_agent.invoke \
  --message "生成一个 30x30、10 台 AGV 的地图，然后用默认算法运行仿真" \
  --pretty
```

This produces both `map_file_path` and `run_metrics` when successful.

## Handle Missing Information

First call:

```bash
python -m mapf_agent.invoke --message "生成一个地图" --pretty
```

If the response has `waiting_for_input: true`, ask the user the returned `question`, then retry:

```bash
python -m mapf_agent.invoke \
  --message "生成一个地图" \
  --answers '["20x20，4 台 AGV，8 个货架，2 个接收点"]' \
  --pretty
```

## Optimize Algorithms

Prefer optimizing a generated algorithm path from `generated_code`, or an
existing WareRover planner/scheduler file that is present in the local checkout.

```bash
python -m mapf_agent.invoke \
  --message "优化 planner/cbs_fw_planner.py 和 scheduler/TA_scheduler.py，目标是提高任务完成率，迭代 100 轮" \
  --pretty
```

Use `optimize_result.best_score`, `optimize_result.best_metrics`, and `optimize_result.run_dir` in the final user report.

## JSON File Input

`request.json`:

```json
{
  "message": "生成一个 20x20 地图并运行仿真",
  "answers": []
}
```

Command:

```bash
python -m mapf_agent.invoke --input request.json --pretty
```
