# MA-CBS（Meta-Agent Conflict-Based Search）工程化 Skill

## 1. 适用目标

* 类型：MAPF 最优路径规划（planner）
* 适用于：基于 CBS 的改进算法生成（尤其是冲突密集场景）
* 解决问题：

  * CBS 在强耦合场景（大量冲突）下性能退化
  * 在“独立规划 vs 联合规划”之间动态选择策略
* 适用条件：

  * 多智能体之间冲突频繁或存在瓶颈结构
  * 需要最优解（sum of cost）
* 不适用：

  * 仅需可行解（用优先级规划/LNS更合适）
  * agent 数量极大（联合搜索会爆炸）

---

## 2. 核心思想

* CBS 在高层通过“加约束”解决冲突，但在高冲突场景下会爆炸
* MA-CBS 引入 **动态合并（merge）机制**：

  * 当两个 agent 冲突次数超过阈值 B → 合并为 meta-agent
* meta-agent 在低层使用 **联合搜索（coupled solver）**
* 算法在两种模式之间自适应切换：

  * 低冲突 → CBS（分解）
  * 高冲突 → A*（耦合）
* 使用 **冲突计数矩阵（Conflict Matrix）** 决定 merge
* 合并后：

  * 内部冲突不再由高层处理
  * 外部冲突通过 meta-constraint 处理
* MA-CBS(B) 是 CBS 和 ID 的统一框架：

  * B = ∞ → CBS
  * B = 0 → ID（完全合并）

---

## 3. 实现时必须保留的机制

### 3.1 高层 Constraint Tree（CT）

* 必须实现
* 原因：

  * 这是 CBS/MA-CBS 的核心搜索结构
  * 管理约束与解空间分裂

---

### 3.2 冲突检测（Conflict Detection）

* 必须实现（vertex + edge）
* 原因：

  * 决定分裂 or 合并
  * 错误会导致非法解

---

### 3.3 分裂（Branch）机制

* 必须保留
* 原因：

  * 保证最优性
  * 即使有 merge，也不能完全替代 branch

---

### 3.4 合并（Merge）机制（MA-CBS核心）

* 必须实现：

  * should_merge()
  * meta-agent 构造
* 原因：

  * 是该算法区别于 CBS 的关键

---

### 3.5 冲突计数矩阵（Conflict Matrix）

* 必须实现
* 原因：

  * 决定何时 merge
  * 没有它就退化为 CBS

---

### 3.6 低层搜索（Single / Multi-agent）

* 必须支持：

  * 单 agent A*
  * meta-agent 联合 A*
* 原因：

  * merge 后必须能求解联合路径

---

### 3.7 约束传播机制

* 必须实现：

  * 普通 constraint → meta-constraint 转换
* 原因：

  * 保证 merge 后约束仍正确

---

## 4. 可工程化简化的部分

### 4.1 merge 阈值 B

* 可简化为固定值（如 B=3 或 B=5）
* 不需要复杂自适应策略
* 影响：

  * B 小 → 更像 ID（更慢但稳定）
  * B 大 → 更像 CBS（更快但可能爆炸）

---

### 4.2 低层联合求解器

* 可直接使用：

  * A* over joint state
* 不必实现：

  * A*+OD / EPEA*
* 影响：

  * 性能下降，但实现简单

---

### 4.3 冲突选择策略

* 可简化为：

  * “第一个冲突”
* 不需要：

  * cardinal conflict 分类
* 影响：

  * 搜索效率略差

---

### 4.4 CAT（冲突规避表）

* 可选
* 不实现也可运行
* 影响：

  * 收敛变慢

---

### 4.5 k-agent conflict处理

* 只处理 pairwise（论文建议）
* 不用处理 k-way split
* 影响：

  * 更简单，正确性不受影响

---

## 5. 推荐的数据结构与状态表示

### 5.1 CT 节点

```python
class CTNode:
    constraints: List[Constraint]
    solution: Dict[agent_id, Path]
    cost: int
    parent: Optional[CTNode]
```

---

### 5.2 Constraint

```python
class Constraint:
    agent: int or MetaAgentID
    location: int or (u, v)
    time: int
```

---

### 5.3 MetaAgent

```python
class MetaAgent:
    agents: Set[int]
```

---

### 5.4 冲突表示

```python
class Conflict:
    agent1
    agent2
    location
    time
    type: "vertex" or "edge"
```

---

### 5.5 Conflict Matrix

```python
conflict_matrix: Dict[(agent_i, agent_j), int]
```

---

### 5.6 OPEN 表

```python
heapq based priority queue
key = cost (sum of costs)
```

---

### 5.7 路径表示

```python
Path = List[node_id]
# index = time
```

---

## 6. 建议的算法流程

### 主流程（MA-CBS）

1. 初始化 root：

   * constraints = ∅
   * solution = 对每个 agent 做低层 A*
   * cost = sum of costs

2. 初始化 OPEN（按 cost 排序）

3. while OPEN 非空：

   1. 取 cost 最小节点 P

   2. 检测冲突 C

   3. 若无冲突：

      * return solution

   4. 更新 conflict_matrix[C.agent1, C.agent2] += 1

   5. 判断是否 merge：

      * if conflict_matrix > B：

        * 执行 merge
      * else：

        * 执行 branch

---

### 子流程：Merge

1. 创建 meta-agent：

   * new_agent = union(ai, aj)

2. 更新 agent 集合

3. 构造新约束：

   * 删除 internal constraints
   * 保留 external constraints → 转换为 meta-constraint

4. 调用低层：

   * 对 meta-agent 做联合规划

5. 更新 solution 和 cost

6. 重新插入 OPEN

---

### 子流程：Branch

1. 对冲突 (ai, aj, v, t)：

   * 创建两个子节点：

     * N1: 加 constraint (ai, v, t)
     * N2: 加 constraint (aj, v, t)

2. 对对应 agent 重新规划路径

3. 更新 cost

4. 插入 OPEN

---

### 子流程：低层搜索

#### 单 agent

* A* in space-time
* 避免违反 constraint

#### meta-agent

* 状态 = 所有 agent 的位置组合
* 避免内部冲突

---

## 7. 与仿真器适配时的实现约束

* 优先保证：

  * 正确性 > 最优性 > 性能
* 若仿真器接口有限：

  * 不支持联合动作 → 拆解 meta-agent path
* 假设不成立：

  * 仿真器可能是连续时间 → 需离散化
* 若无全局地图：

  * 用局部规划近似低层 A*
* 必须可调试：

  * 输出每次冲突、merge、branch
* 避免：

  * 使用复杂并行框架
  * 依赖外部 MAPF solver

---

## 8. 生成代码时的关键规则

* 必须先实现 CBS，再扩展为 MA-CBS
* 必须保证 CT 节点 cost 单调递增
* merge 后必须重新规划 meta-agent
* constraint 必须严格过滤低层状态
* 不允许遗漏冲突检测
* OPEN 必须是最小堆（按 cost）
* 所有路径必须时间对齐（padding）
* 不要实现复杂优化（先保证正确）

---

## 9. 常见错误与避免方式

### 1. 忘记更新 conflict_matrix

* 导致永不 merge
* ✔ 每次检测到冲突都更新

---

### 2. merge 后未重新规划

* solution 不一致
* ✔ 必须调用低层

---

### 3. 约束未正确转换为 meta-constraint

* 导致非法解
* ✔ 所有 external constraint 转为 meta

---

### 4. 忽略 edge conflict

* 路径非法
* ✔ 同时检测 vertex + edge

---

### 5. OPEN 排序错误

* 非最优
* ✔ 按 cost 排序

---

### 6. 只修改一个 agent 的路径

* 不一致
* ✔ branch 只改一个，merge 改 meta-agent

---

### 7. meta-agent 状态定义错误

* 搜索空间错误
* ✔ 使用 joint state

---

### 8. 未处理路径长度不同

* 仿真错误
* ✔ 用 goal padding

---

### 9. 终止条件错误

* 死循环
* ✔ OPEN 空 → 无解

---

### 10. merge 后仍继续 branch

* 逻辑冲突
* ✔ merge 后直接 continue

---

## 10. 最小可行版本建议

### 第一阶段（MVP）

* 实现标准 CBS：

  * CT + A* + conflict detection

### 第二阶段

* 加入：

  * conflict_matrix
  * should_merge(B)

### 第三阶段

* 实现：

  * meta-agent
  * joint A*

### 第四阶段（优化）

* CAT
* better conflict selection

---

## 11. 一句话实现摘要

* 先实现 CBS，再加 merge，不要反过来
* 冲突是驱动一切的核心事件
* merge 是优化，不是替代 branch
* meta-agent 本质是“联合搜索”
* 所有约束必须严格生效
* 优先保证路径合法，其次才是性能
