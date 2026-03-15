from mapf_agent.tools.validate_map import validate_map

__all__ = ["validate_map", "run_simulation"]


def __getattr__(name: str):
    """Lazy import run_simulation to avoid loading test.single_run (and torch) when only using validate_map."""
    if name == "run_simulation":
        from mapf_agent.tools.run_simulation import run_simulation
        return run_simulation
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
