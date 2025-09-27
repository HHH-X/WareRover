"""
Gurobi (gurobipy) MIP template for the AGV-task-box assignment & scheduling model
Based on the mathematical model described to the user.

How to use:
 - Fill the `data` dict or implement the `load_data()` function to provide:
     * A: list of AGV ids
     * T: list of task ids
     * B: list of box ids
     * avail[(k,b)] = 0/1 (box b contains the good required by task k)
     * tau_start[(i,b)] (time from AGV i start to box b)
     * tau_end[(k,b)] (time from task k end to box b)
     * p[(b,k)] (processing time of task k if using box b: box->task + service)
     * optional: end_pos, task_route etc — used by your preprocessing if needed
 - Run: `python gurobi_agv_mip_template.py` (requires gurobipy installed and Gurobi license)

This template implements the linearized MIP with variables:
 y[i,k], z[k,b], w[k,l,i], x[k,l,i], v[k,l,b], q[k,l,b], s[k], C[k], C_max

Note: For performance on large instances prune candidate boxes per task (K nearest boxes).
"""

from gurobipy import Model, GRB, quicksum
import math

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

    # tau_start[(i,b)] : time from AGV i initial pos to box b
    tau_start = {(i,b): float((i+1)*(b+2)) for i in A for b in B}

    # tau_end[(k,b)] : time from task k end location to box b
    tau_end = {(k,b): float((k+2)*(b+1)) for k in T for b in B}

    # p[(b,k)] : processing time if using box b for task k
    p = {(b,k): float(5 + ((b+k) % 4)) for b in B for k in T}

    data = dict(A=A, T=T, B=B, avail=avail, tau_start=tau_start, tau_end=tau_end, p=p)
    return data


# ---------------------------
# Utilities: prune candidate boxes per task (keep top-K by heuristic)
# ---------------------------

def prune_candidate_boxes(data, K=3):
    # Keep at most K boxes per task where avail==1; choose by smallest p[(b,k)] as heuristic
    A, T, B, avail, p = data['A'], data['T'], data['B'], data['avail'], data['p']
    candidates = {k: [] for k in T}
    for k in T:
        cand = [b for b in B if avail.get((k,b),0) == 1]
        # sort by p
        cand.sort(key=lambda b: p[(b,k)])
        candidates[k] = cand[:K]
    return candidates


# ---------------------------
# Build and solve model
# ---------------------------

def build_and_solve(data, candidates=None, time_limit=60, M=None, verbose=True):
    A = data['A']; T = data['T']; B = data['B']
    avail = data['avail']; tau_start = data['tau_start']; tau_end = data['tau_end']; p = data['p']

    # If not given, prune candidates automatically
    if candidates is None:
        candidates = prune_candidate_boxes(data, K=3)

    # If M not provided, set conservative big-M
    if M is None:
        # M = sum of max processing times + some travel upper bound
        max_p_k = {k: max((p[(b,k)] for b in B if avail.get((k,b),0)==1), default=0.0) for k in T}
        M = sum(max_p_k.values()) + max(tau_start.values()) + max(tau_end.values()) + 1.0

    model = Model('agv_task_box_scheduling')
    model.setParam('OutputFlag', 1 if verbose else 0)
    model.setParam('TimeLimit', time_limit)

    # ---------------------------
    # Variables
    # ---------------------------
    # y[i,k]
    y = {}
    for i in A:
        for k in T:
            y[i,k] = model.addVar(vtype=GRB.BINARY, name=f'y_{i}_{k}')

    # z[k,b] only for candidate boxes
    z = {}
    for k in T:
        for b in candidates[k]:
            z[k,b] = model.addVar(vtype=GRB.BINARY, name=f'z_{k}_{b}')

    # s_k and C_k
    s = {k: model.addVar(vtype=GRB.CONTINUOUS, lb=0.0, name=f's_{k}') for k in T}
    C = {k: model.addVar(vtype=GRB.CONTINUOUS, lb=0.0, name=f'C_{k}') for k in T}
    Cmax = model.addVar(vtype=GRB.CONTINUOUS, lb=0.0, name='Cmax')

    # w_{k,l,i} and x_{k,l,i} only for k<l to avoid duplicates
    w = {}
    x = {}
    for i in A:
        for kk in range(len(T)):
            for ll in range(kk+1, len(T)):
                k = T[kk]; l = T[ll]
                w[k,l,i] = model.addVar(vtype=GRB.BINARY, name=f'w_{k}_{l}_{i}')
                x[k,l,i] = model.addVar(vtype=GRB.BINARY, name=f'x_{k}_{l}_{i}')
                # Note: x_{l,k,i} will be represented via x[k,l,i] by symmetry in constraints below

    # v_{k,l,b} and q_{k,l,b} for box mutual exclusion: only when both k and l have this box as candidate
    v = {}
    q = {}
    for kk in range(len(T)):
        for ll in range(kk+1, len(T)):
            k = T[kk]; l = T[ll]
            common_boxes = set(candidates[k]).intersection(candidates[l])
            for b in common_boxes:
                v[k,l,b] = model.addVar(vtype=GRB.BINARY, name=f'v_{k}_{l}_b{b}')
                q[k,l,b] = model.addVar(vtype=GRB.BINARY, name=f'q_{k}_{l}_b{b}')
                # q_{l,k,b} will be represented as (1 - q_{k,l,b}) in constraints below via equality v = q+q_rev
                # but for simplicity we create separate var for reverse ordering as well
                # create reverse
                q[(l,k,b)] = model.addVar(vtype=GRB.BINARY, name=f'q_{l}_{k}_b{b}')

    model.update()

    # ---------------------------
    # Constraints
    # ---------------------------
    # 1) Each task assigned to exactly one AGV
    for k in T:
        model.addConstr(quicksum(y[i,k] for i in A) == 1, name=f'assgn_task_{k}')

    # 2) Each task chooses exactly one box among its candidates
    for k in T:
        model.addConstr(quicksum(z[k,b] for b in candidates[k]) == 1, name=f'choose_box_{k}')
        # Also ensure z only for available boxes -- already enforced by candidate selection
        for b in candidates[k]:
            model.addConstr(z[k,b] <= avail.get((k,b),0), name=f'avail_{k}_{b}')

    # 3) Link w_{k,l,i} to y (w = y_i_k AND y_i_l) for k<l
    for i in A:
        for kk in range(len(T)):
            for ll in range(kk+1, len(T)):
                k = T[kk]; l = T[ll]
                model.addConstr(w[k,l,i] <= y[i,k], name=f'w_le_y1_{k}_{l}_{i}')
                model.addConstr(w[k,l,i] <= y[i,l], name=f'w_le_y2_{k}_{l}_{i}')
                model.addConstr(w[k,l,i] >= y[i,k] + y[i,l] - 1, name=f'w_ge_y_{k}_{l}_{i}')

    # 4) For same-AGV pair, exactly one ordering: x_{k,l,i} + x_{l,k,i} = w_{k,l,i}
    # Represent x_{l,k,i} by a new variable referencing x for the pair (k,l)
    # We'll access x variables carefully: x_pair(k,l,i) returns x[k,l,i] if k<l else (1 - x[l,k,i]) ???
    # For simplicity create constraints explicitly using both x[k,l,i] and x[l,k,i] by symmetry
    # Create x_rev references: x_rev[l,k,i] corresponds to 'x_{l,k,i}' (we'll use same dict with ordered keys)
    # We added only x for k<l, so x_rev access needs to be careful.
    for i in A:
        for kk in range(len(T)):
            for ll in range(kk+1, len(T)):
                k = T[kk]; l = T[ll]
                # x[k,l,i] + x_rev = w[k,l,i]
                # define x_rev as (1 - x[k,l,i]) only when w=1; but linear form is:
                # x[k,l,i] + x_rev = w; and x_rev and x are binaries so this encodes ordering
                # We need to create explicit variable for x_rev; easier: also create x_rev var
                # But we already created only x[k,l,i]. Let's create x_rev on the fly:
                x_rev = model.addVar(vtype=GRB.BINARY, name=f'x_rev_{l}_{k}_{i}')
                model.addConstr(x[k,l,i] + x_rev == w[k,l,i], name=f'order_pair_{k}_{l}_{i}')
                # we'll use x_rev in time constraints where needed by searching the variable by name later

    model.update()

    # We'll collect x_rev variables by name for later use
    x_rev_vars = {v.VarName: v for v in model.getVars() if v.VarName.startswith('x_rev_')}

    # 5) Start-time lower bound from AGV initial position if y[i,k]==1: s_k >= sum_b tau_start_{i,b} z_{k,b} - M(1-y_{i,k})
    for i in A:
        for k in T:
            expr = quicksum(tau_start[(i,b)] * z[k,b] for b in candidates[k])
            model.addConstr(s[k] >= expr - M*(1 - y[i,k]), name=f'start_init_{i}_{k}')

    # 6) Sequence time constraints for same-AGV ordering
    # For pair k<l and AGV i, we have two orderings represented by x[k,l,i] and x_rev variable
    for i in A:
        for kk in range(len(T)):
            for ll in range(kk+1, len(T)):
                k = T[kk]; l = T[ll]
                # find the x_rev variable by name
                x_rev_name = f'x_rev_{l}_{k}_{i}'
                x_rev_var = x_rev_vars[x_rev_name]
                # If x[k,l,i] == 1 then k before l: s_l >= C_k + sum_b tau_end[k,b] z[l,b] - M(1 - x[k,l,i])
                expr_tau = quicksum(tau_end[(k,b)] * z[l,b] for b in candidates[l])
                model.addConstr(s[l] >= C[k] + expr_tau - M*(1 - x[k,l,i]), name=f'seq_time1_{k}_{l}_{i}')
                # If x_rev == 1 then l before k
                expr_tau2 = quicksum(tau_end[(l,b)] * z[k,b] for b in candidates[k])
                model.addConstr(s[k] >= C[l] + expr_tau2 - M*(1 - x_rev_var), name=f'seq_time2_{k}_{l}_{i}')

    # 7) Completion time lower bound: C_k >= s_k + sum_b p[b,k] z[k,b]
    for k in T:
        expr_p = quicksum(p[(b,k)] * z[k,b] for b in candidates[k])
        model.addConstr(C[k] >= s[k] + expr_p, name=f'completion_{k}')

    # 8) Box mutual exclusion: If both tasks use same box, enforce ordering q + q_rev = v and time sequencing
    for kk in range(len(T)):
        for ll in range(kk+1, len(T)):
            k = T[kk]; l = T[ll]
            common_boxes = set(candidates[k]).intersection(candidates[l])
            for b in common_boxes:
                # linearize v = z[k,b] AND z[l,b]
                model.addConstr(v[k,l,b] <= z[k,b], name=f'v_le_z1_{k}_{l}_b{b}')
                model.addConstr(v[k,l,b] <= z[l,b], name=f'v_le_z2_{k}_{l}_b{b}')
                model.addConstr(v[k,l,b] >= z[k,b] + z[l,b] - 1, name=f'v_ge_z_{k}_{l}_b{b}')
                # ordering on box usage: q + q_rev = v
                model.addConstr(q[k,l,b] + q[(l,k,b)] == v[k,l,b], name=f'q_sum_{k}_{l}_b{b}')
                # timing
                model.addConstr(s[l] >= C[k] - M*(1 - q[k,l,b]), name=f'box_time1_{k}_{l}_b{b}')
                model.addConstr(s[k] >= C[l] - M*(1 - q[(l,k,b)]), name=f'box_time2_{k}_{l}_b{b}')

    # 9) Cmax definition
    for k in T:
        model.addConstr(C[k] <= Cmax, name=f'cmax_def_{k}')

    # Optional: symmetry breaking / heuristics
    # e.g., assign task 0 to AGV 0 as a seed (only if applicable): y[0,0] == 1
    # model.addConstr(y[A[0], T[0]] == 1)

    # ---------------------------
    # Objective
    # ---------------------------
    model.setObjective(Cmax, GRB.MINIMIZE)

    # ---------------------------
    # Optimize
    # ---------------------------
    model.optimize()

    # ---------------------------
    # Extract solution
    # ---------------------------
    if model.status == GRB.OPTIMAL or model.status == GRB.TIME_LIMIT or model.status == GRB.SUBOPTIMAL:
        sol = {}
        sol['Cmax'] = Cmax.X
        sol['assignments'] = {k: None for k in T}
        sol['box_choice'] = {k: None for k in T}
        sol['start'] = {k: s[k].X for k in T}
        sol['complete'] = {k: C[k].X for k in T}
        for k in T:
            for i in A:
                if y[i,k].X > 0.5:
                    sol['assignments'][k] = i
            for b in candidates[k]:
                if z[k,b].X > 0.5:
                    sol['box_choice'][k] = b
        if verbose:
            print('\nSolution summary:')
            print('Cmax =', sol['Cmax'])
            for k in T:
                print(f'Task {k}: AGV {sol["assignments"][k]}, box {sol["box_choice"][k]}, s={sol["start"][k]:.2f}, C={sol["complete"][k]:.2f}')
        return sol
    else:
        print('No feasible solution found. Status:', model.status)
        return None


if __name__ == '__main__':
    data = load_data_example()
    candidates = prune_candidate_boxes(data, K=3)
    sol = build_and_solve(data, candidates=candidates, time_limit=30, verbose=True)

"""
Notes and caveats:
- This template creates many pairwise ordering variables. For medium/large-scale instances you must reduce the pairwise sets by:
    * limiting candidate boxes per task
    * only creating pairwise variables for task pairs that can actually overlap in time/space
- The code builds "x_rev" variables dynamically to represent reverse ordering for same-AGV pairs; this is a practical way to avoid creating twice the x variables for (k,l) and (l,k).
- For production use consider implementing interval variables in CP-SAT (OR-Tools) or using time-indexed formulations for special cases.

"""
