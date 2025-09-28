# OR-Tools CP-SAT model for the AGV-task-box scheduling problem (small example)
# This code builds the MILP-like model in OR-Tools CP-SAT, solves it, and prints results.
# Time is discretized as integer units. The model follows the formulation provided earlier:
#   - x[i,t]: task t assigned to AGV i
#   - z[t,k]: task t uses box k (only allowed if box contains required good)
#   - y[i,t,u]: on AGV i, task t is immediately before task u
#   - q[t,u,k]: tasks t and u use the same box k
#   - s[t], c[t]: integer start/completion times
#
# Small example dataset included and solver run.
from ortools.sat.python import cp_model

def build_and_solve_example():
    # Example data (small)
    # AGVs
    I = [0,1]  # two AGVs
    N = len(I)
    # Boxes
    K = [0,1]  # two boxes
    # Goods types
    G = [0,1]  # two goods
    # Tasks
    # Each task needs a good id, has a service time, has start/end locations for distance calc (we use simple d_tu)
    tasks = {
        0: {'good':0, 'p':3, 'loc':(0,0)},
        1: {'good':1, 'p':4, 'loc':(5,0)},
        2: {'good':0, 'p':2, 'loc':(2,3)}
    }
    T = list(tasks.keys())
    C = len(T)
    # Box contents: h[k,g] = 1 if box k contains good g
    h = {
        (0,0):1, (0,1):0,  # box0 contains good0
        (1,0):1, (1,1):1   # box1 contains good0 and good1
    }
    # pick and ret times per box (integer)
    pick = {0:2, 1:2}
    ret = {0:2, 1:2}
    # service times p_t
    p = {t: tasks[t]['p'] for t in T}
    # compute travel times d_tu as Manhattan distance rounded up (or simple Euclidean)
    import math
    d = {}
    for t in T:
        for u in T:
            if t==u:
                d[(t,u)] = 0
            else:
                x1,y1 = tasks[t]['loc']
                x2,y2 = tasks[u]['loc']
                d[(t,u)] = int(math.ceil(math.hypot(x1-x2, y1-y2)))
    # start distances from AGV start positions to task starts (S(i) to t)
    # AGV starts at positions:
    starts = {0:(-1,0), 1:(6,0)}
    dS = {}
    for i in I:
        for t in T:
            x1,y1 = starts[i]
            x2,y2 = tasks[t]['loc']
            dS[(i,t)] = int(math.ceil(math.hypot(x1-x2, y1-y2)))
    # AGV availability
    a_i = {i:0 for i in I}
    # Big M: upper bound on schedule horizon (sum of all service + travel + pick/ret)
    M_upper = sum(p.values()) + max(d.values())*C + sum(max(pick.values()),)
    # make it a bit larger:
    M = 1000
    
    # Build model
    model = cp_model.CpModel()
    # Variables
    x = {}  # x[i,t]
    for i in I:
        for t in T:
            x[(i,t)] = model.NewBoolVar(f'x_{i}_{t}')
    z = {}  # z[t,k]
    for t in T:
        for k in K:
            # only allow if box k contains the required good
            allowed = h.get((k, tasks[t]['good']), 0)
            if allowed:
                z[(t,k)] = model.NewBoolVar(f'z_{t}_{k}')
            else:
                # force 0 by creating a constant 0 via equality to 0 bool var
                z[(t,k)] = None  # we'll treat as 0 in constraints and solution extraction
    
    y = {}  # y[i,t,u] (t != u)
    for i in I:
        for t in T:
            for u in T:
                if t==u: continue
                y[(i,t,u)] = model.NewBoolVar(f'y_{i}_{t}_{u}')
    q = {}  # q[t,u,k] symmetric; define for all t!=u and any k that is feasible for both
    for t in T:
        for u in T:
            if t==u: continue
            for k in K:
                # q only meaningful if both z(t,k) and z(u,k) allowed
                if (z.get((t,k)) is not None) and (z.get((u,k)) is not None):
                    q[(t,u,k)] = model.NewBoolVar(f'q_{t}_{u}_{k}')
                else:
                    q[(t,u,k)] = None
    
    # start and completion times (integers)
    # choose a horizon bound:
    horizon = 50
    s = {}
    c = {}
    for t in T:
        s[t] = model.NewIntVar(0, horizon, f's_{t}')
        c[t] = model.NewIntVar(0, horizon, f'c_{t}')
    
    Cmax = model.NewIntVar(0, horizon, 'Cmax')
    
    # Constraints
    # Each task assigned to exactly one AGV
    for t in T:
        model.Add(sum(x[(i,t)] for i in I) == 1)
    # Each task chooses exactly one box among allowed ones
    for t in T:
        allowed_boxes = [k for k in K if z.get((t,k)) is not None]
        model.Add(sum(z[(t,k)] for k in allowed_boxes) == 1)
    # connect x and y: outdegree equals x_{i,t}
    for i in I:
        for t in T:
            model.Add(sum(y[(i,t,u)] for u in T if u!=t) == x[(i,t)])
    # indegree equals x_{i,t}
    for i in I:
        for u in T:
            model.Add(sum(y[(i,t,u)] for t in T if t!=u) == x[(i,u)])
    # y only allowed if both tasks assigned to same AGV (implied by above but we add guards)
    for i in I:
        for t in T:
            for u in T:
                if t==u: continue
                model.AddImplication(y[(i,t,u)], x[(i,t)])
                model.AddImplication(y[(i,t,u)], x[(i,u)])
    # c_t = s_t + p_t
    for t in T:
        model.Add(c[t] == s[t] + p[t])
    # q linearization: q <= z_tk, q <= z_uk, q >= z_tk + z_uk -1
    for t in T:
        for u in T:
            if t==u: continue
            for k in K:
                if q.get((t,u,k)) is None: continue
                model.Add(q[(t,u,k)] <= z[(t,k)])
                model.Add(q[(t,u,k)] <= z[(u,k)])
                model.Add(q[(t,u,k)] >= z[(t,k)] + z[(u,k)] - 1)
    # time transition constraints for y: if y(i,t,u)=1 then s_u >= c_t + Trans_{t,u}
    # Trans_{t,u} = d[t,u] + sum_ret(z_tk) + sum_pick(z_uk) - sum(ret+pick)*q_tuk
    for i in I:
        for t in T:
            for u in T:
                if t==u: continue
                # build linear expression for trans
                # Note: OR-Tools CP-SAT needs linearexpr: coefficients for IntVars/bools fine.
                expr_terms = []
                const_term = d[(t,u)]
                # sum ret_k * z_tk
                for k in K:
                    if z.get((t,k)) is not None:
                        expr_terms.append((ret[k], z[(t,k)]))
                # sum pick_k * z_uk
                for k in K:
                    if z.get((u,k)) is not None:
                        expr_terms.append((pick[k], z[(u,k)]))
                # minus sum (ret+pick) * q_tuk
                for k in K:
                    if q.get((t,u,k)) is None: continue
                    coeff = -(ret[k] + pick[k])
                    expr_terms.append((coeff, q[(t,u,k)]))
                # Build RHS: c_t + const_term + linear terms <= s_u + M*(1-y)
                # Move all to LHS: c_t + const + sum(coeff*var) - s_u <= M*(1 - y)
                # Implement using linear constraint with allowed slack via big-M
                # Left side linear: c_t - s_u + const + sum(coeff*var) <= M*(1-y)
                left_vars = []
                left_coeffs = []
                left_vars.append(c[t]); left_coeffs.append(1)
                left_vars.append(s[u]); left_coeffs.append(-1)
                # add z/q terms
                for coeff,var in expr_terms:
                    left_vars.append(var); left_coeffs.append(coeff)
                # constant
                lhs_const = const_term
                # Create constraint: sum(coeffs*vars) + lhs_const <= M*(1 - y)
                # Convert to: sum(coeffs*vars) + lhs_const + M*y <= M
                # i.e., sum(coeffs*vars) + M*y <= M - lhs_const
                # We'll use M_big large enough (horizon*10)
                M_big = 1000
                # left expression + M*y <= M - lhs_const
                model.Add(sum(left_coeffs[i]*left_vars[i] for i in range(len(left_vars))) + M_big * y[(i,t,u)] <= M_big - lhs_const)
    # Start from AGV start to first task: if y[i,S,u]=1 then s_u >= a_i + dS + sum_pick(z_u)
    # We don't have explicit S node; we emulate by: for each i and u, define a bool start_i_u indicating it's first task.
    start_bool = {}
    for i in I:
        for u in T:
            start_bool[(i,u)] = model.NewBoolVar(f'start_{i}_{u}')
            # relate start_bool to y: start_bool == y from a virtual S which has outgoing sum = x_i_*
            # We'll enforce: start_bool <= x_{i,u} and sum_u start_bool ==  sum_t x_{i,t}? simpler: require start_bool <= x_{i,u},
            model.AddImplication(start_bool[(i,u)], x[(i,u)])
    # Ensure each AGV has at most one start (if it does tasks) and if it has tasks then exactly one start_bool =1
    for i in I:
        # sum start_bool == (sum x_{i,t} >= 1) ? We'll enforce sum_start == 1 if sum_x >=1, else 0.
        sum_x = sum(x[(i,t)] for t in T)
        sum_start = sum(start_bool[(i,u)] for u in T)
        # sum_start <= sum_x  (if no tasks, no start)
        model.Add(sum_start <= sum_x)
        # sum_start >= sum_x / C  -> not linear; but we can enforce sum_x >=1 => sum_start >=1 via big-M
        # Introduce used_i bool
        used_i = model.NewBoolVar(f'used_{i}')
        model.Add(sum_x >= 1).OnlyEnforceIf(used_i)
        model.Add(sum_x == 0).OnlyEnforceIf(used_i.Not())
        model.Add(sum_start == 1).OnlyEnforceIf(used_i)
        model.Add(sum_start == 0).OnlyEnforceIf(used_i.Not())
    # Now start constraints: if start_bool true then s_u >= a_i + dS[i,u] + sum_k pick_k * z[u,k]
    for i in I:
        for u in T:
            # left: s_u - sum(pick*z_uk) >= a_i + dS - M*(1-start_bool)
            # convert to: s_u - sum(pick*z_uk) + M*(1-start_bool) >= a_i + dS
            # OR-Tools uses OnlyEnforceIf for implications; simpler: Add(s_u >= a_i + dS + sum(pick*z_uk)) with enforcement
            # Use half-reified constraint:
            picks = []
            for k in K:
                if z.get((u,k)) is not None:
                    picks.append((pick[k], z[(u,k)]))
            # Build expression: s_u >= a_i + dS + sum(pick*z_uk)  if start_bool true
            if picks:
                model.Add(s[u] >= a_i[i] + dS[(i,u)] + sum(coeff*var for coeff,var in picks)).OnlyEnforceIf(start_bool[(i,u)])
            else:
                model.Add(s[u] >= a_i[i] + dS[(i,u)]).OnlyEnforceIf(start_bool[(i,u)])
    # Cmax constraints
    for t in T:
        model.Add(c[t] <= Cmax)
    # Objective: minimize Cmax
    model.Minimize(Cmax)
    
    # Solve
    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = 20
    solver.parameters.num_search_workers = 8
    result = solver.Solve(model)
    status = solver.StatusName(result)
    out = {'status':status}
    if result == cp_model.OPTIMAL or result == cp_model.FEASIBLE:
        out['Cmax'] = solver.Value(Cmax)
        assignments = {}
        boxes = {}
        starts_out = {}
        completions_out = {}
        order_arcs = []
        for t in T:
            # find assigned i
            for i in I:
                if solver.Value(x[(i,t)])==1:
                    assignments[t]=i
            # box
            for k in K:
                if z.get((t,k)) is not None and solver.Value(z[(t,k)])==1:
                    boxes[t]=k
            starts_out[t]=solver.Value(s[t])
            completions_out[t]=solver.Value(c[t])
        # reconstruct sequences per AGV using y
        seqs = {i:[] for i in I}
        # build adjacency for each AGV
        for i in I:
            adj = {t: None for t in T}
            preds = {t: None for t in T}
            for t in T:
                for u in T:
                    if t==u: continue
                    if solver.Value(y[(i,t,u)])==1:
                        adj[t] = u
                        preds[u] = t
            # find start: node with no predecessor but assigned to i
            start_node = None
            for t in T:
                if assignments.get(t)==i and preds[t] is None:
                    start_node = t; break
            # follow path
            cur = start_node
            while cur is not None:
                seqs[i].append(cur)
                cur = adj[cur] if adj.get(cur) is not None else None
        out['assignments'] = assignments
        out['boxes'] = boxes
        out['starts'] = starts_out
        out['completions'] = completions_out
        out['sequences'] = seqs
    else:
        out['message'] = 'No feasible solution found or solver status not optimal/feasible.'
    return out, {'data':{'I':I,'K':K,'T':T,'p':p,'d':d,'dS':dS,'pick':pick,'ret':ret,'h':h}}

if __name__ == '__main__':
    try:
        result, meta = build_and_solve_example()
        print('Solver status:', result['status'])
        if result['status'] in ('OPTIMAL','FEASIBLE'):
            print('Makespan Cmax =', result['Cmax'])
            print('Assignments (task -> AGV):', result['assignments'])
            print('Selected boxes (task -> box):', result['boxes'])
            print('Start times:', result['starts'])
            print('Completion times:', result['completions'])
            print('Sequences per AGV:', result['sequences'])
        else:
            print(result.get('message', 'No solution data.'))
    except ImportError as e:
        print('OR-Tools not installed in this environment. Error:', e)
    except Exception as e:
        print('Error during solving:', e)
