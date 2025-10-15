from ortools.sat.python import cp_model

def solve_agv_scheduling():
    # 数据参数（使用您提供的数据）
    num_agvs = 3  # A
    num_tasks = 5  # T
    num_containers = 4  # K
    horizon = 1000  # 时间上界
    processing_times = [5, 8, 6, 7, 9]  # p_t for each task
    possible_containers = [
        [0, 1],  # task 0
        [1, 2],
        [0, 3],
        [2, 3],
        [0, 2]
    ]
    setup_times = [
        [0, 10, 5, 15, 8],
        [12, 0, 7, 6, 9],
        [4, 11, 0, 13, 5],
        [14, 3, 10, 0, 12],
        [6, 8, 4, 11, 0]
    ]

    # 创建模型
    model = cp_model.CpModel()

    # 变量：每个任务的开始/结束时间
    starts = [model.NewIntVar(0, horizon, f'start_{t}') for t in range(num_tasks)]
    ends = [model.NewIntVar(0, horizon, f'end_{t}') for t in range(num_tasks)]
    # 每个任务选择的货箱
    containers = [model.NewIntVarFromDomain(cp_model.Domain.FromValues(possible_containers[t]), f'container_{t}') for t in range(num_tasks)]
    # 是否分配到 AGV a
    is_on_agv = [[model.NewBoolVar(f'is_on_{t}_{a}') for a in range(num_agvs)] for t in range(num_tasks)]

    # 约束：每个任务固定时长，且分配到一个 AGV
    for t in range(num_tasks):
        model.Add(ends[t] == starts[t] + processing_times[t])
        model.AddExactlyOne(is_on_agv[t])

    # 约束：货箱占用不重叠（简化版）
    intervals_per_container = [[] for _ in range(num_containers)]
    for t in range(num_tasks):
        for c in possible_containers[t]:
            # 如果任务 t 使用货箱 c，则激活区间
            is_active = model.NewBoolVar(f'task_{t}_cont_{c}')
            model.Add(containers[t] == c).OnlyEnforceIf(is_active)
            model.Add(containers[t] != c).OnlyEnforceIf(is_active.Not())
            interval = model.NewOptionalIntervalVar(
                starts[t], processing_times[t], ends[t], is_active,
                f'interval_task_{t}_cont_{c}')
            intervals_per_container[c].append(interval)
    # 每个货箱的区间不重叠
    for c in range(num_containers):
        model.AddNoOverlap(intervals_per_container[c])

    # 节点编号：任务 0 ~ num_tasks-1，之后为每个 AGV 的 start/end
    base_dummy_node = num_tasks

    # 为每个 AGV 构建序列图
    arcs_per_agv = [[] for _ in range(num_agvs)]  # 存储弧以便输出序列
    for a in range(num_agvs):
        start_node = base_dummy_node + 2 * a
        end_node = base_dummy_node + 2 * a + 1
        arcs = arcs_per_agv[a]

        # 未分配任务的自环
        for t in range(num_tasks):
            self_loop_lit = is_on_agv[t][a].Not()
            arcs.append((t, t, self_loop_lit))

        # end -> start
        arcs.append((end_node, start_node, True))

        # start -> task
        for t in range(num_tasks):
            lit = model.NewBoolVar(f'start_to_{t}_agv{a}')
            model.AddImplication(lit, is_on_agv[t][a])
            arcs.append((start_node, t, lit))

        # task -> end
        for t in range(num_tasks):
            lit = model.NewBoolVar(f'{t}_to_end_agv{a}')
            model.AddImplication(lit, is_on_agv[t][a])
            arcs.append((t, end_node, lit))

        # task1 -> task2
        for t1 in range(num_tasks):
            for t2 in range(num_tasks):
                if t1 != t2:
                    lit = model.NewBoolVar(f'{t1}_to_{t2}_agv{a}')
                    model.AddImplication(lit, is_on_agv[t1][a])
                    model.AddImplication(lit, is_on_agv[t2][a])
                    arcs.append((t1, t2, lit))
                    model.Add(starts[t2] >= ends[t1] + setup_times[t1][t2]).OnlyEnforceIf(lit)

        # 空 AGV 的直接弧：start -> end
        direct_lit = model.NewBoolVar(f'start_to_end_agv{a}')
        arcs.append((start_node, end_node, direct_lit))

        # 如果有任务，则不使用 direct
        no_tasks = model.NewBoolVar(f'no_tasks_agv{a}')
        model.Add(sum(is_on_agv[t][a] for t in range(num_tasks)) == 0).OnlyEnforceIf(no_tasks)
        model.Add(sum(is_on_agv[t][a] for t in range(num_tasks)) > 0).OnlyEnforceIf(no_tasks.Not())
        model.AddImplication(no_tasks, direct_lit)
        for t in range(num_tasks):
            model.AddImplication(direct_lit, is_on_agv[t][a].Not())

        # 添加 circuit 约束
        model.AddCircuit(arcs)

    # 目标：最小化 makespan
    makespan = model.NewIntVar(0, horizon, 'makespan')
    model.AddMaxEquality(makespan, ends)
    model.Minimize(makespan)

    # 求解
    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = 60.0
    solver.parameters.log_search_progress = True  # 开启日志以调试
    status = solver.Solve(model)

    if status == cp_model.OPTIMAL or status == cp_model.FEASIBLE:
        print(f'Optimal makespan: {solver.Value(makespan)}')
        # 输出任务分配
        for t in range(num_tasks):
            agv = next(a for a in range(num_agvs) if solver.BooleanValue(is_on_agv[t][a]))
            cont = solver.Value(containers[t])
            start_time = solver.Value(starts[t])
            end_time = solver.Value(ends[t])
            print(f'Task {t}: AGV {agv}, Container {cont}, Start {start_time}, End {end_time}')

        # 输出每台 AGV 的任务序列
        for a in range(num_agvs):
            print(f'\nAGV {a} sequence:')
            sequence = []
            current = base_dummy_node + 2 * a  # start node
            visited = set()
            while True:
                for src, dst, lit in arcs_per_agv[a]:
                    if solver.BooleanValue(lit) and src == current and dst not in visited:
                        if dst < num_tasks:  # 仅记录任务节点
                            sequence.append(dst)
                        current = dst
                        visited.add(dst)
                        break
                if current == base_dummy_node + 2 * a + 1:  # 到达 end 节点
                    break
            if sequence:
                print(f'Tasks: {sequence}')
            else:
                print('No tasks assigned.')
    else:
        print('No solution found.')

if __name__ == '__main__':
    solve_agv_scheduling()