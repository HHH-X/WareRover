"""
Initial evolve target for MAPF planner wrapper.

OpenEvolve will only modify code inside the EVOLVE-BLOCK.
"""

# EVOLVE-BLOCK-START
def rank_targets(target_rows, current_step=0):
    """
    Rank AGV replanning targets and return ordered agv_id list.

    Args:
        target_rows: list[dict], each item includes:
            - agv_id: int
            - start: tuple[int, int]
            - goal: tuple[int, int]
        current_step: int simulation step
    """
    scored = []
    for row in target_rows:
        agv_id = int(row["agv_id"])
        sx, sy = row["start"]
        gx, gy = row["goal"]

        # Baseline heuristic: prioritize shorter Manhattan distance.
        distance = abs(sx - gx) + abs(sy - gy)

        # Tiny deterministic tie-break to avoid unstable ordering.
        tie_break = ((agv_id * 31 + current_step) % 17) * 1e-4

        score = -float(distance) + tie_break
        scored.append((score, agv_id))

    scored.sort(reverse=True)
    return [agv_id for _, agv_id in scored]


# EVOLVE-BLOCK-END


def run_ranker_preview():
    """Optional local sanity check entry for manual testing."""
    sample = [
        {"agv_id": 1, "start": (0, 0), "goal": (5, 5)},
        {"agv_id": 2, "start": (2, 2), "goal": (3, 2)},
        {"agv_id": 3, "start": (1, 1), "goal": (1, 8)},
    ]
    return rank_targets(sample, current_step=0)
