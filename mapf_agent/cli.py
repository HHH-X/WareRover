"""
CLI entry for MAPF Agent: generate-map, generate-algorithm, full, interactive.
Run from project root: python -m mapf_agent.cli <subcommand> ...
"""
import argparse
import json
import os
import sys

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from mapf_agent.agents.coordinator import Coordinator


def cmd_generate_map(args: argparse.Namespace) -> int:
    coordinator = Coordinator()
    # Use workflow in map_only mode
    state = coordinator.run(args.nl_input, output_path=args.output, mode_hint="map_only")

    if state.get("pending_question") and not state.get("map_json"):
        print(state["pending_question"])
        return 1

    if state.get("map_json") and not state.get("error"):
        print("Map generated successfully.")
        if state.get("map_path"):
            print(f"Written to: {state['map_path']}")
        if args.print_json:
            print(json.dumps(state["map_json"], indent=2, ensure_ascii=False))
        return 0

    print("Error:", state.get("error", "Unknown error"), file=sys.stderr)
    return 1


def cmd_generate_algorithm(args: argparse.Namespace) -> int:
    if not args.map_file or not os.path.isfile(args.map_file):
        print("Error: --map-file must point to an existing map JSON.", file=sys.stderr)
        return 1

    coordinator = Coordinator(use_llm=not args.no_llm)
    state = coordinator.run(
        args.nl_input,
        output_path=None,
        map_path=args.map_file,
        mode_hint="algorithm_only",
    )

    if state.get("error"):
        print("Error:", state.get("error", "Unknown error"), file=sys.stderr)
        return 1

    print("Simulation completed.")
    if state.get("metrics"):
        print("Metrics:", json.dumps(state["metrics"], indent=2))
    history = state.get("optimization_history", [])
    if history:
        last = history[-1]
        suggestion = last.get("suggestion", {})
        if suggestion.get("reasoning"):
            print("Suggestion:", suggestion["reasoning"])
    return 0


def cmd_full(args: argparse.Namespace) -> int:
    coordinator = Coordinator(use_llm=not args.no_llm)
    out = coordinator.run_full(
        map_nl=args.map_nl,
        algorithm_nl=args.algorithm_nl,
        map_output_path=args.output,
        seed=args.seed,
        num_runs=args.runs,
    )

    if not out.get("ok"):
        print("Error:", out.get("error", "Unknown error"), file=sys.stderr)
        return 1

    print("Full pipeline completed.")
    if out.get("map_path"):
        print("Map path:", out["map_path"])
    if out.get("metrics"):
        print("Metrics:", json.dumps(out["metrics"], indent=2))
    history = out.get("optimization_history", [])
    if history:
        last = history[-1]
        suggestion = last.get("suggestion", {})
        if suggestion.get("reasoning"):
            print("Suggestion:", suggestion["reasoning"])
    return 0


def cmd_interactive(args: argparse.Namespace) -> int:
    """Interactive mode: multi-turn conversation with the MAPF Agent."""
    coordinator = Coordinator(use_llm=not args.no_llm)

    print("=" * 60)
    print("MAPF Agent Interactive Mode")
    print("=" * 60)
    print("Describe your warehouse map and/or algorithm requirements.")
    print("Type 'quit' or 'exit' to leave.\n")

    output_path = args.output or ""

    while True:
        try:
            user_input = input("You: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nBye!")
            return 0

        if user_input.lower() in ("quit", "exit", "q"):
            print("Bye!")
            return 0

        if not user_input:
            continue

        state = coordinator.run(user_input, output_path=output_path)

        while state.get("pending_question"):
            print(f"\nAgent: {state['pending_question']}")
            try:
                follow_up = input("You: ").strip()
            except (EOFError, KeyboardInterrupt):
                print("\nBye!")
                return 0

            if follow_up.lower() in ("quit", "exit", "q"):
                print("Bye!")
                return 0

            state = coordinator.resume(follow_up)

        _print_result(state)
        print()


def _print_result(state: dict):
    """Print the final result from a workflow state."""
    if state.get("error"):
        print(f"\nAgent [Error]: {state['error']}")
        return

    if state.get("map_json"):
        print("\nAgent: Map generated successfully!")
        w = state["map_json"].get("map", {}).get("width", "?")
        h = state["map_json"].get("map", {}).get("height", "?")
        n_agvs = len(state["map_json"].get("agvs", []))
        n_boxes = len(state["map_json"].get("boxes", []))
        print(f"  Size: {w}x{h}, AGVs: {n_agvs}, Shelves: {n_boxes}")
        if state.get("map_path"):
            print(f"  Saved to: {state['map_path']}")

    if state.get("sim_config_applied"):
        applied = {k: v for k, v in state["sim_config_applied"].items() if v is not None}
        if applied:
            print(f"  SimConfig updated: {applied}")

    if state.get("metrics"):
        print(f"\nAgent: Simulation results:")
        metrics = state["metrics"]
        for key in ("Task Success Rate", "completed_orders", "sim_steps", "finished"):
            if key in metrics:
                print(f"  {key}: {metrics[key]}")

    history = state.get("optimization_history", [])
    if history:
        print(f"\nAgent: Optimization ran {len(history)} iteration(s).")
        last = history[-1]
        suggestion = last.get("suggestion", {})
        if suggestion.get("reasoning"):
            print(f"  Final suggestion: {suggestion['reasoning']}")

    if state.get("algo_config"):
        algo = state["algo_config"]
        if algo.get("reasoning"):
            print(f"\nAgent: Algorithm choice: {algo['reasoning']}")


def main() -> int:
    parser = argparse.ArgumentParser(description="MAPF Agent: generate map config and/or run algorithm.")
    parser.add_argument("--no-llm", action="store_true", help="Disable LLM, use regex/rule fallback only")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # generate-map
    p1 = subparsers.add_parser("generate-map", help="Phase 1: generate map config from natural language")
    p1.add_argument("nl_input", type=str, help="Natural language description of the map")
    p1.add_argument("-o", "--output", type=str, default=None, help="Output JSON path")
    # p1.add_argument("--print-json", action="store_true", help="Print generated JSON to stdout")
    # p1.add_argument("--no-llm", action="store_true", help="Disable LLM")
    p1.set_defaults(func=cmd_generate_map)

    # generate-algorithm
    p2 = subparsers.add_parser("generate-algorithm", help="Phase 2: run algorithm on existing map")
    p2.add_argument("nl_input", type=str, help="Algorithm description")
    p2.add_argument("--map-file", type=str, required=True, help="Path to map JSON file")
    p2.add_argument("--seed", type=int, default=None, help="Random seed")
    p2.add_argument("--runs", type=int, default=1, help="Number of simulation runs")
    p2.add_argument("--no-llm", action="store_true", help="Disable LLM")
    p2.set_defaults(func=cmd_generate_algorithm)

    # full
    p3 = subparsers.add_parser("full", help="Run both phases")
    p3.add_argument("map_nl", type=str, help="Natural language for map")
    p3.add_argument("algorithm_nl", type=str, help="Natural language for algorithm")
    p3.add_argument("-o", "--output", type=str, default=None, help="Output path for generated map JSON")
    p3.add_argument("--seed", type=int, default=None)
    p3.add_argument("--runs", type=int, default=1)
    p3.add_argument("--no-llm", action="store_true", help="Disable LLM")
    p3.set_defaults(func=cmd_full)

    # interactive
    p4 = subparsers.add_parser("interactive", help="Interactive multi-turn conversation mode")
    p4.add_argument("-o", "--output", type=str, default=None, help="Default output path for generated maps")
    p4.add_argument("--no-llm", action="store_true", help="Disable LLM")
    p4.set_defaults(func=cmd_interactive)

    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
