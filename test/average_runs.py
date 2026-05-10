"""
Script to run run_single_episode 20 times with different seeds and compute average metrics.
python -m test.average_runs
"""
import sys
sys.path.append('..')  # Add parent directory to path
from .single_run import run_single_episode

def main():
    results = []
    num_runs = 20

    for i in range(num_runs):
        print(f"Running episode {i+1}/{num_runs} with seed {i}")
        result = run_single_episode(seed=i)
        results.append(result)

    # Keys that are numeric and should be averaged
    numeric_keys = [
        'Tasks Completed', 'Task Success Rate', 'Total Task Time', 'Avg Task Time',
        'Throughput', 'Total AGV Collisions', 'Scheduler Calls', 'Scheduler Total Time',
        'Scheduler Avg Time', 'Planner Calls', 'Planner Total Time', 'Planner Avg Time',
        'Decision Total Time', 'Sim Steps', 'sim_stps'
    ]

    averages = {}
    for key in numeric_keys:
        values = [r[key] for r in results if key in r]
        if values:
            averages[key] = sum(values) / len(values)

    # Check if all runs finished
    all_finished = all(r.get('finished', False) for r in results)

    print("Average Metrics:")
    for key, value in averages.items():
        print(f"{key}: {value}")

    print(f"All runs finished: {all_finished}")

if __name__ == "__main__":
    main()