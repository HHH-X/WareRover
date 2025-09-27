"""
OR-Tools CP-SAT version of the AGV-task-box assignment & scheduling model.

Requirements:
    pip install ortools

Notes:
 - All times are scaled to integers by TIME_SCALE (default 100). Change if needed.
 - This keeps the structure of your original Gurobi model, but adapted to CP-SAT:
   y[i,k], z[k,b], w[k,l,i], x[k,l,i], v[k,l,b], q[k,l,b], s[k], C[k], Cmax
 - For pairwise ordering we explicitly create both x[k,l,i] and x[l,k,i] and constrain
   x[k,l,i] + x[l,k,i] == w[k,l,i] (so exactly one ordering holds when tasks share the AGV).
"""

from ortools.sat.python import cp_model
import math
from collections import defaultdict

# ---------------------------
# Example data loader (replace with your real data)
# ---------------------------
def load_data_example():
    # small example: 2 AGVs, 8 tasks, 5 boxes
    A = [0,1]
    T = list(range(8))
    B = list(range(5))

    # avail[(k,b)] = 1 if box b contains the good required by task k
    avail = {}
    for k in T:
        for b in B:
            # toy random availability pattern (replace)
            avail[(k,b)] = 1 if ((k + b) % 2 == 0) else 0

    # tau_start[(i,b)] : time from AGV i initial pos to box b (float)
    tau_start = {(i,b): float((i+1)*(b+2)) for i in A for b in B}

    # tau_end[(k,b)] : time from task k end location to box b (float)
    tau_end = {(k,b): float((k+2)*(b+1)) for k in T for b in B}

    # p[(b,k)] : processing time if using box b for task k (float)
    p = {(b,k): float(5 + ((b+k) % 4)) for b in B for k in T}

    data = dict(A=A, T=T, B=B, avail=avail, tau_start=tau_start, tau_end=tau_end, p=p)
    return data

# ---------------------------
# Utilities: prune candidate boxes per task (keep top-K by heuristic)
# ---------------------------
def prune_candidate_boxes(data, K=3):
    A, T, B, avail, p = data['A'], data['T'], data['B'], data['avail'], data['p']
    candidates = {k: [] for k in T}
    for k in T:
        cand = [b for b in B if avail.get((k,b),0) == 1]
        cand.sort(key=lambda b: p[(b,k)])
        candidates[k] = cand[:K]
    return candidates

# ---------------------------
# Build and solve using OR-Tools CP-SAT
# ---------------------------
def build_and_solve_ortools(data, candidates=None, time_limit=30,
                             TIME_SCALE=100, verbose=True):
    """
    - TIME_SCALE: multiply all float times by this and round to int for CP-SAT.
    - time_limit: seconds
    """
    A = data['A']; T = data['T']; B = data['B']
    avail = data['avail']; tau_start = data['tau_start']; tau_end = data['tau_end']; p = data['p']

    if candidates is None:
        candidates = prune_candidate_boxes(data, K=3)

    # scale float times to int
    def scale(v):
        return int(round(v * TIME_SCALE))

    # compute M if not given: conservative upper bound
    max_p_k = {k: max((p[(b,k)] for b in B if avail.get((k,b),0)==1), default=0.0) for k in T}
    max_tau_start = max(tau_start.values()) if tau_start else 0.0
    max_tau_end = max(tau_end.values()) if tau_end else 0.0
    M_float = sum(max_p_k.values()) + max_tau_start + max_tau_end + 1.0
    M = scale(M_float)

    # compute an upper bound on times for variables s,C,Cmax
    # crude UB: sum of all processing + max travel
    UB_float = sum(max_p_k.values()) + max_tau_start + max_tau_end + M_float
    UBOUND = max(1, scale(UB_float) + M)  # ensure >0

    model = cp_model.CpModel()

    # ---------------------------
    # Variables
    # ---------------------------
    # y[i,k] boolean
    y = {}
    for i in A:
        for k in T:
            y[i,k] = model.NewBoolVar(f'y_{i}_{k}')

    # z[k,b] only for candidates
    z = {}
    for k in T:
        for b in candidates[k]:
            z[k,b] = model.NewBoolVar(f'z_{k}_{b}')

    # s_k and C_k (integer scaled)
    s = {k: model.NewIntVar(0, UBOUND, f's_{k}') for k in T}
    C = {k: model.NewIntVar(0, UBOUND, f'C_{k}') for k in T}
    Cmax = model.NewIntVar(0, UBOUND, 'Cmax')

    # w_{k,l,i} and x_{k,l,i} for all unordered pairs (explicitly create both directions)
    w = {}
    x = {}
    # iterate over index pairs to ensure deterministic ordering
    for i in A:
        for kk in range(len(T)):
            for ll in range(kk+1, len(T)):
                k = T[kk]; l = T[ll]
                w[k,l,i] = model.NewBoolVar(f'w_{k}_{l}_{i}')
                # create both directional x variables: x_{k,l,i} and x_{l,k,i}
                x[k,l,i] = model.NewBoolVar(f'x_{k}_{l}_{i}')
                x[l,k,i] = model.NewBoolVar(f'x_{l}_{k}_{i}')

    # v_{k,l,b} and q_{k,l,b} for common boxes (both directions for q)
    v = {}
    q = {}
    for kk in range(len(T)):
        for ll in range(kk+1, len(T)):
            k = T[kk]; l = T[ll]
            common_boxes = set(candidates[k]).intersection(candidates[l])
            for b in common_boxes:
                v[k,l,b] = model.NewBoolVar(f'v_{k}_{l}_b{b}')
                q[k,l,b] = model.NewBoolVar(f'q_{k}_{l}_b{b}')
                q[l,k,b] = model.NewBoolVar(f'q_{l}_{k}_b{b}')

    # ---------------------------
    # Constraints
    # ---------------------------
    # 1) Each task assigned to exactly one AGV
    for k in T:
        model.Add(sum(y[i,k] for i in A) == 1)

    # 2) Each task chooses exactly one box among its candidates
    for k in T:
        model.Add(sum(z[k,b] for b in candidates[k]) == 1)
        for b in candidates[k]:
            if avail.get((k,b),0) == 0:
                # disallow
                model.Add(z[k,b] == 0)

    # 3) Link w_{k,l,i} to y (w = y_i_k AND y_i_l) for k<l
    for i in A:
        for kk in range(len(T)):
            for ll in range(kk+1, len(T)):
                k = T[kk]; l = T[ll]
                # w <= y_i_k, w <= y_i_l
                model.Add(w[k,l,i] <= y[i,k])
                model.Add(w[k,l,i] <= y[i,l])
                # w >= y_i_k + y_i_l - 1  -> rearranged as linear:
                # y_i_k + y_i_l - w <= 1  -> CP-SAT supports Add(y + y - w <= 1)
                model.Add(y[i,k] + y[i,l] - w[k,l,i] <= 1)
                # equivalently also add w >= y+y-1 is implied

    # 4) For same-AGV pair, exactly one ordering: x[k,l,i] + x[l,k,i] == w[k,l,i]
    for i in A:
        for kk in range(len(T)):
            for ll in range(kk+1, len(T)):
                k = T[kk]; l = T[ll]
                model.Add(x[k,l,i] + x[l,k,i] == w[k,l,i])

    # 5) Start-time lower bound from AGV initial position if y[i,k]==1:
    # s_k >= sum_b tau_start_{i,b} * z_{k,b} - M*(1 - y_{i,k})
    # transform to: s_k + M*(1 - y_ik) >= sum_b tau_start * z
    for i in A:
        for k in T:
            expr = sum(scale(tau_start[(i,b)]) * z[k,b] for b in candidates[k])
            # s[k] + M*(1 - y[i,k]) >= expr
            # Expand: s[k] + M - M*y >= expr  -> s[k] - M*y >= expr - M
            # CP-SAT linear form supports Add(s + M*(1 - y) >= expr)
            model.Add(s[k] + M * (1 - y[i,k]) >= expr)

    # 6) Sequence time constraints for same-AGV ordering
    # If x[k,l,i] == 1 then k before l: s_l >= C_k + sum_b tau_end[k,b] * z[l,b] - M*(1 - x[k,l,i])
    for i in A:
        for kk in range(len(T)):
            for ll in range(kk+1, len(T)):
                k = T[kk]; l = T[ll]
                # k before l
                expr_tau = sum(scale(tau_end[(k,b)]) * z[l,b] for b in candidates[l])
                # s_l + M*(1 - x_kl_i) >= C_k + expr_tau
                model.Add(s[l] + M * (1 - x[k,l,i]) >= C[k] + expr_tau)
                # l before k
                expr_tau2 = sum(scale(tau_end[(l,b)]) * z[k,b] for b in candidates[k])
                model.Add(s[k] + M * (1 - x[l,k,i]) >= C[l] + expr_tau2)

    # 7) Completion time lower bound: C_k >= s_k + sum_b p[b,k] z[k,b]
    for k in T:
        expr_p = sum(scale(p[(b,k)]) * z[k,b] for b in candidates[k])
        model.Add(C[k] >= s[k] + expr_p)

    # 8) Box mutual exclusion: linearize v = z[k,b] AND z[l,b], and q+q_rev = v, timing
    for kk in range(len(T)):
        for ll in range(kk+1, len(T)):
            k = T[kk]; l = T[ll]
            common_boxes = set(candidates[k]).intersection(candidates[l])
            for b in common_boxes:
                # v <= z[k,b], v <= z[l,b]
                model.Add(v[k,l,b] <= z[k,b])
                model.Add(v[k,l,b] <= z[l,b])
                # v >= z[k,b] + z[l,b] - 1  -> z[k]+z[l] - v <= 1
                model.Add(z[k,b] + z[l,b] - v[k,l,b] <= 1)
                # ordering on box usage: q + q_rev == v
                model.Add(q[k,l,b] + q[l,k,b] == v[k,l,b])
                # timing: s_l >= C_k - M*(1 - q[k,l,b])
                model.Add(s[l] + M * (1 - q[k,l,b]) >= C[k])
                model.Add(s[k] + M * (1 - q[l,k,b]) >= C[l])

    # 9) Cmax definition
    for k in T:
        model.Add(C[k] <= Cmax)

    # Optional: symmetry breaking / heuristics (none by default)

    # Objective: minimize Cmax
    model.Minimize(Cmax)

    # ---------------------------
    # Solver params and solve
    # ---------------------------
    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = time_limit
    # allow some log
    solver.parameters.log_search_progress = verbose
    # optionally set num_workers = 8 etc
    # solver.parameters.num_search_workers = 8

    result = solver.Solve(model)

    status = result
    if verbose:
        print("Solver status:", solver.StatusName(status))

    if status in (cp_model.OPTIMAL, cp_model.OPTIMAL, cp_model.FEASIBLE):
        # extract solution, rescale times back to float
        sol = {}
        sol['Cmax'] = solver.Value(Cmax) / TIME_SCALE
        sol['assignments'] = {k: None for k in T}
        sol['box_choice'] = {k: None for k in T}
        sol['start'] = {k: solver.Value(s[k]) / TIME_SCALE for k in T}
        sol['complete'] = {k: solver.Value(C[k]) / TIME_SCALE for k in T}

        for k in T:
            for i in A:
                if solver.Value(y[i,k]) == 1:
                    sol['assignments'][k] = i
            for b in candidates[k]:
                if solver.Value(z[k,b]) == 1:
                    sol['box_choice'][k] = b

        if verbose:
            print('\nSolution summary:')
            print('Cmax =', sol['Cmax'])
            for k in T:
                print(f'Task {k}: AGV {sol["assignments"][k]}, box {sol["box_choice"][k]}, '
                      f's={sol["start"][k]:.2f}, C={sol["complete"][k]:.2f}')
        return sol
    else:
        if verbose:
            print('No feasible solution found. Status:', solver.StatusName(status))
        return None

# ---------------------------
# Example usage
# ---------------------------
if __name__ == '__main__':
    data = load_data_example()
    candidates = prune_candidate_boxes(data, K=3)
    sol = build_and_solve_ortools(data, candidates=candidates, time_limit=15, TIME_SCALE=10, verbose=True)

