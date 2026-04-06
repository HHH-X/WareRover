# OpenEvolve MAPF Planner Wrapper

This directory contains the first runnable OpenEvolve integration for planner evolution.

## What gets evolved

- Target file: `initial_program.py`
- Evolved symbol: `rank_targets(...)`
- Integration point: `planner/evolved_wrapper_planner.py`

Only the code inside `EVOLVE-BLOCK` in `initial_program.py` will be modified by OpenEvolve.

## Metrics and combined score

The evaluator runs multiple seeded episodes and computes:

- `completion_score` (weight 0.35)
- `makespan_score` (weight 0.35)
- `time_score` (weight 0.20)
- `stability_score` (weight 0.10)

Formula:

`combined_score = 0.35*completion + 0.35*makespan + 0.20*time + 0.10*stability`

## Run evolution (Windows PowerShell)

From repository root:

```powershell
powershell -ExecutionPolicy Bypass -File evolution/mapf_planner_wrapper/run_evolve.ps1
```

Or run directly:

```powershell
python openevolve/openevolve-run.py `
  evolution/mapf_planner_wrapper/initial_program.py `
  evolution/mapf_planner_wrapper/evaluator.py `
  --config evolution/mapf_planner_wrapper/config.yaml `
  --output evolution/mapf_planner_wrapper/openevolve_output
```

### Smoke run without API key (manual mode)

Current `config.yaml` enables `llm.manual_mode: true` for local smoke testing.

Use:

```powershell
python evolution/mapf_planner_wrapper/smoke_manual_run.py
```

What it does:

- Starts OpenEvolve for 1 iteration.
- Auto-responds to manual queue with a valid no-op diff.
- Verifies full pipeline: mutate -> evaluate -> save best program.

## Output locations

- Best candidate metadata: `evolution/mapf_planner_wrapper/openevolve_output/best/best_program_info.json`
- Best candidate code: `evolution/mapf_planner_wrapper/openevolve_output/best/best_program.py`
- Run logs: `evolution/mapf_planner_wrapper/openevolve_output/logs/`

## Switch to real online evolution

1. Set `llm.manual_mode: false` in `config.yaml`.
2. Provide API key in environment (for OpenAI-compatible endpoint):
   - PowerShell: `$env:OPENAI_API_KEY = "<your_key>"`
3. Run `run_evolve.ps1` or direct CLI command above.

## Adopt best candidate

1. Inspect `evolution/mapf_planner_wrapper/openevolve_output/`.
2. Locate the best program file from OpenEvolve results.
3. Copy its evolved `rank_targets` implementation back to `initial_program.py` (inside `EVOLVE-BLOCK`) to set a new baseline.
4. Set planner to `evolved_wrapper` in `SimConfig.planner_type` when testing in simulator runs.
