# OR-Tools MIP 模板：AGV + Container 任务调度（基于上面模型）
# 说明：这是一个可运行的示例模板。你可以替换示例数据（A, T, K, g_t, S_k, R_t, s_same, s_diff, I）为你的实际数据。
# 运行此脚本会构建 MIP 并使用 CBC 求解器（默认）求解最小化 makespan (C_max) 的问题。
# 变量说明见注释：x[i,t], z[i,t,k], y[i,t,u], C[t], C_max

from ortools.linear_solver import pywraplp

def build_and_solve_example():
    # -------------------- 示例数据（可改） --------------------
    A = 2  # AGV 数量
    T = 4  # 任务数量
    K = 4  # 货箱数量
    G = 4  # 货物种类数量 (用于示例)
    
    # 任务所需货物种类 g_t (从 0 开始索引)
    g = [0, 1, 2, 3]  # length T
    
    # 每个货箱包含的货物种类集合 S_k
    S = [
        {0},    # container 0 包含物品类型 0
        {1},  # container 1 包含物品类型 0 和 1
        {2},
        {3}
    ]
    
    # 任务执行时间 R_t（不含换箱）
    R = [4, 3, 5, 6]  # length T
    
    # 转换时间：相同箱 vs 不同箱 (可以依赖任务对)
    # 这里为简化，使用统一参数矩阵（T x T）
    s_same = [[0]*T for _ in range(T)]
    s_diff = [[1]*T for _ in range(T)]
    # 使对角无意义（任务对相同通常不会出现，但保留为0）
    for t in range(T):
        s_diff[t][t] = 0
        s_same[t][t] = 0
    
    # AGV 从初始位置开始到执行任务 t 的前置时间 I_{i,t}
    I = [[2 for _ in range(T)] for _ in range(A)]
    
    # big-M 常数（应足够大，视实例扩大）
    M = 1e6
    
    # -------------------- 构建求解器 --------------------
    solver = pywraplp.Solver.CreateSolver('CBC')
    if not solver:
        raise Exception("无法创建 CBC 求解器（ortools 未正确安装？）")
    
    # 变量 ----------------------------------------
    x = {}  # x[i,t] in {0,1}
    for i in range(A):
        for t in range(T):
            x[(i,t)] = solver.IntVar(0, 1, f"x_{i}_{t}")
    
    # z[i,t,k] 仅为可行组合创建（即 container k 包含任务 t 所需货物）
    z = {}
    for i in range(A):
        for t in range(T):
            for k in range(K):
                if g[t] in S[k]:
                    z[(i,t,k)] = solver.IntVar(0, 1, f"z_{i}_{t}_{k}")
                else:
                    # 不可行组合 - 不创建变量，也可以显式置为 0（此处用 None 占位）
                    z[(i,t,k)] = None
    
    # y[i,t,u] 表示在同一 AGV i 上，任务 t 的直接后继是 u
    y = {}
    for i in range(A):
        for t in range(T):
            for u in range(T):
                if t == u:
                    y[(i,t,u)] = None  # 不需要 t->t
                else:
                    y[(i,t,u)] = solver.IntVar(0, 1, f"y_{i}_{t}_{u}")
    
    # 完成时间变量 C_t >= 0
    C = [solver.NumVar(0.0, solver.infinity(), f"C_{t}") for t in range(T)]
    C_max = solver.NumVar(0.0, solver.infinity(), "C_max")
    
    # 约束 ----------------------------------------
    # 每个任务被且仅被一个 AGV 执行
    for t in range(T):
        solver.Add(sum(x[(i,t)] for i in range(A)) == 1)
    
    # 若 AGV i 执行任务 t，则为其选择且仅选择一个可行的 container k
    for i in range(A):
        for t in range(T):
            feasible_z = [z[(i,t,k)] for k in range(K) if z[(i,t,k)] is not None]
            # sum z = x
            if feasible_z:
                solver.Add(solver.Sum(feasible_z) == x[(i,t)])
            else:
                # 如果没有可行容器，这个任务不可被任何 AGV 执行（模型数据有问题）
                solver.Add(x[(i,t)] == 0)
    
    # y 的 "直接后继" 定义：若任务 t 被分配给 i，则恰好有一个直接后继或为末尾（允许无后继）
    # 我们要求：sum_u y_{i,t,u} == x_{i,t}
    for i in range(A):
        for t in range(T):
            succ_vars = [y[(i,t,u)] for u in range(T) if y[(i,t,u)] is not None]
            solver.Add(solver.Sum(succ_vars) <= x[(i,t)])
    # 每个任务 u 在 AGV i 上最多有一个前驱
    for i in range(A):
        for u in range(T):
            pred_vars = [y[(i,t,u)] for t in range(T) if y[(i,t,u)] is not None]
            solver.Add(solver.Sum(pred_vars) <= x[(i,u)])
    
    # 起始任务的初始时间下界：若 t 是 AGV i 的首个任务（即 x_{i,t}=1 并且没有前驱），
    # 我们使用松弛的约束： C_t >= I_{i,t} + R_t - M*(1 - x_{i,t})，以确保若 x_{i,t}=1 则满足
    for i in range(A):
        for t in range(T):
            solver.Add(C[t] >= I[i][t] + R[t] - M * (1 - x[(i,t)]))
    
    # 若 t 的直接后继是 u，则完成时间递推： C_u >= C_t + R_t + switch_time - bigM * (inactive)
    # 需要考虑相同 container (k==l) 和 不同 container (k!=l) 两种情形
    for i in range(A):
        for t in range(T):
            for u in range(T):
                if t == u: 
                    continue
                # for same container k:
                for k in range(K):
                    zk_t = z[(i,t,k)]
                    zk_u = z[(i,u,k)]
                    if zk_t is None or zk_u is None:
                        continue  # 不可行
                    # C_u >= C_t + R_t + s_same[t][u] - M*(1 - y) - M*(1 - zk_t) - M*(1 - zk_u)
                    solver.Add(C[u] >= C[t] + R[t] + s_same[t][u] - M*(1 - y[(i,t,u)]) - M*(1 - zk_t) - M*(1 - zk_u))
                # for different containers k != l:
                for k in range(K):
                    for l in range(K):
                        if k == l:
                            continue
                        zk_t = z[(i,t,k)]
                        zl_u = z[(i,u,l)]
                        if zk_t is None or zl_u is None:
                            continue
                        solver.Add(C[u] >= C[t] + R[t] + s_diff[t][u] - M*(1 - y[(i,t,u)]) - M*(1 - zk_t) - M*(1 - zl_u))
    
    # makespan 定义
    for t in range(T):
        solver.Add(C_max >= C[t])
    
    # 对称性与可行性提示（可选）：
    # 若想避免同等等价解的对称性，可以对 AGV 编号强制某些顺序（此处不强制）
    
    # 目标：最小化 C_max
    solver.Minimize(C_max)
    
    # 求解
    status = solver.Solve()
    
    # 结果解析与展示
    if status == pywraplp.Solver.OPTIMAL or status == pywraplp.Solver.FEASIBLE:
        print("解决状态:", "OPTIMAL" if status == pywraplp.Solver.OPTIMAL else "FEASIBLE")
        print("最优的 C_max =", C_max.solution_value())
        for i in range(A):
            print(f"\nAGV {i} 分配的任务序列：")
            # 打印分配给 i 的任务
            assigned = [t for t in range(T) if x[(i,t)].solution_value() > 0.5]
            if not assigned:
                print("  (无任务)")
                continue
            # 简单重构任务顺序：从任意被分配任务找链（注意：若存在多条链/循环，需进一步处理）
            # 找出没有前驱的任务作为起点（在 AGV i 上）
            preds = {u: sum(y[(i,t,u)].solution_value() for t in range(T) if y[(i,t,u)] is not None) for u in assigned}
            start_tasks = [u for u in assigned if preds[u] < 0.5]
            # 逐链打印（通常应该只有一条链/若有多条，则说明并行或多段）
            for start in start_tasks:
                cur = start
                seq = [cur]
                while True:
                    # 找直接后继
                    succ = None
                    for u in range(T):
                        if y.get((i,cur,u)) is None:
                            continue
                        if y[(i,cur,u)].solution_value() > 0.5:
                            succ = u
                            break
                    if succ is None:
                        break
                    seq.append(succ)
                    cur = succ
                # 打印序列及使用的 containers（若有）
                print("  序列起点 task", start, " -> ", seq)
                for t in seq:
                    used_k = None
                    for k in range(K):
                        if z[(i,t,k)] is not None and z[(i,t,k)].solution_value() > 0.5:
                            used_k = k
                            break
                    print(f"    task {t}: 完成时间 C[{t}]={C[t].solution_value():.1f}, 使用 container={used_k}")
    else:
        print("未找到可行解或求解器失败，状态码：", status)

if __name__ == "__main__":
    build_and_solve_example()
