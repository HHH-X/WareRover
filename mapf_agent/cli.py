"""
CLI entry for MAPF Agent.
Single entry: input text -> the LangGraph workflow routes/suspends/resumes as needed.
Run: python -m mapf_agent.cli "<your request>"
Or:  python -m mapf_agent.cli
"""
import argparse
import json
import os
import sys

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from mapf_agent.agents.coordinator import Coordinator


def cmd_run(args: argparse.Namespace) -> int:
    """Single entry: user types one text; the graph may interrupt and ask follow-ups."""
    coordinator = Coordinator(use_llm=not args.no_llm)

    output_path = args.output or ""
    map_path = args.map_file or ""

    def _read_first_text() -> str:
        if args.text is not None:
            return str(args.text).strip()
        try:
            return input("You: ").strip()
        except (EOFError, KeyboardInterrupt):
            return "exit"

    first_text = _read_first_text()
    if not first_text or first_text.lower() in ("exit", "quit", "q"):
        print("Bye!")
        return 0

    state = coordinator.run(first_text, output_path=output_path, map_path=map_path)
    while state.get("pending_question"):
        q = state.get("pending_question", "")
        pending_type = state.get("pending_type", "")

        print(f"\nAgent: {q}")
        if pending_type == "result_decision" and state.get("metrics"):
            metrics = state.get("metrics", {})
            # Print a few common metric keys.
            for key in ("Task Success Rate", "completed_orders", "sim_steps", "finished"):
                if key in metrics:
                    print(f"  {key}: {metrics[key]}")

        try:
            follow_up = input("You: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nBye!")
            return 0

        if follow_up.lower() in ("exit", "quit", "q"):
            print("Bye!")
            return 0

        state = coordinator.resume(follow_up)

    _print_result(state)
    return 0 if not state.get("error") else 1

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
        if state.get("env_config_path"):
            print(f"  Env config: {state['env_config_path']}")

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
        elif suggestion.get("analysis"):
            print(f"  Final suggestion: {suggestion['analysis']}")

    if state.get("algo_config"):
        algo = state["algo_config"]
        if algo.get("reasoning"):
            print(f"\nAgent: Algorithm choice: {algo['reasoning']}")


def main() -> int:
    parser = argparse.ArgumentParser(description="MAPF Agent: input text -> route/interrupt/resume/run.")
    parser.add_argument("--no-llm", action="store_true", help="Disable LLM, use regex/rule fallback only")
    parser.add_argument("text", nargs="?", type=str, default=None, help="Your natural language request (map/algorithm/both).")
    parser.add_argument("-o", "--output", type=str, default=None, help="Output JSON path for generated maps (optional).")
    parser.add_argument("--map-file", type=str, default=None, help="Existing map JSON path for algorithm-only usage (optional).")
    args = parser.parse_args()
    return cmd_run(args)


if __name__ == "__main__":
    sys.exit(main())
