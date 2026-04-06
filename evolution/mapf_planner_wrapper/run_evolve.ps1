$ErrorActionPreference = "Stop"

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$repoRoot = Resolve-Path (Join-Path $scriptDir "..\..")

Push-Location $repoRoot
try {
    $env:PYTHONPATH = "$repoRoot\openevolve;$repoRoot"
    python openevolve/openevolve-run.py `
        evolution/mapf_planner_wrapper/initial_program.py `
        evolution/mapf_planner_wrapper/evaluator.py `
        --config evolution/mapf_planner_wrapper/config.yaml `
        --output evolution/mapf_planner_wrapper/openevolve_output
}
finally {
    Pop-Location
}
