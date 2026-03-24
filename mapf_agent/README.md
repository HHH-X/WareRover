# MAPF Agent 使用说明

MAPF Agent 基于 WareRover 仿真器，提供两阶段能力：**阶段一**从自然语言生成并验证地图配置；**阶段二**选择或生成算法并在仿真中运行，结合优化建议辅助 MAPF 算法开发。系统支持 **LLM 驱动**（通过 OpenAI 兼容 API）和**规则回退**两种模式，可在无 API key 时降级使用。

---

## 一、功能概览

| 阶段 | 功能 | 说明 |
|------|------|------|
| **阶段一** | 地图配置生成 | 用自然语言描述地图（尺寸、AGV 数量与类型、货架/站台等），Agent 解析后生成符合 WareRover 约定的 JSON，并调用 JSON Schema + 语义校验工具做验证与重试。 |
| **阶段二** | 算法选择与仿真优化 | 在已有地图上，用自然语言指定算法（如 CBS、A\*），运行仿真得到指标，由优化 Agent 给出改进建议并可迭代优化。 |
| **交互模式** | 多轮对话 | 支持交互式多轮对话，Agent 能自动追问缺失信息，通过 LangGraph 工作流实现状态管理与条件路由。 |

所有命令需在 **项目根目录**（`WareRover-private/`）下执行，以便正确加载 `config`、`core`、`planner` 等模块。

---

## 二、环境与依赖

### 2.1 Python 版本

与 WareRover 主项目一致（建议 Python 3.10+）。

### 2.2 安装依赖

```bash
pip install -r mapf_agent/requirements.txt
```

依赖清单（`mapf_agent/requirements.txt`）：

| 包名 | 用途 |
|------|------|
| `openai>=1.0` | LLM API 调用（OpenAI 兼容接口） |
| `jsonschema>=4.0` | 地图 JSON Schema 校验 |
| `langgraph>=0.2` | 工作流状态图（交互模式） |
| `pyyaml>=6.0` | 读取 `knowledge/defaults.yaml` |

使用阶段二运行仿真时，还需 WareRover 主项目的依赖（`numpy`、`scipy` 等）。选用 **DHC** 规划器需额外安装 PyTorch。

### 2.3 配置 LLM API Key

Agent 通过 OpenAI 兼容 API 调用大语言模型。**唯一配置方式**：在 `mapf_agent` 目录下创建 `api_key` 文件，第一行填入你的 API key。

```bash
# 复制模板（可选）
cp mapf_agent/api_key.example mapf_agent/api_key
# 编辑 mapf_agent/api_key，填入真实 key
```

或直接新建 `mapf_agent/api_key`，内容为一行 key，例如：

```
sk-your-api-key-here
```

`mapf_agent/api_key` 已加入 `.gitignore`，不会被提交。自定义端点可在代码中修改 `agent_config.llm_base_url`（默认华为云 MaaS）。

**无 API key 时**：所有 Agent 会自动降级为规则/正则回退模式（`--no-llm`），阶段一使用正则解析 + 确定性地图生成，阶段二使用关键词匹配 + 规则分析，功能可用但生成质量受限。

---

## 三、命令行使用

### 3.1 阶段一：生成地图配置（generate-map）

从自然语言生成地图 JSON，并可写入文件。

```bash
# 基本用法：仅生成，不写文件（结果在内存中）
python -m mapf_agent.cli generate-map "20x15 地图，4 台 AGV，2 大 2 小"

# 指定输出文件
python -m mapf_agent.cli generate-map "20x15, 4 agvs, 2 large 2 small" -o config/maps/agent_generated.json

# 同时将生成的 JSON 打印到终端
python -m mapf_agent.cli generate-map "10x10, 2 agvs" -o config/maps/out.json --print-json

# 不使用 LLM（纯规则/正则模式）
python -m mapf_agent.cli generate-map "10x10, 2 agvs" --no-llm
```

**自然语言示例**（支持中英文混写）：

- `"20x15, 4 agvs"`：20×15 地图，4 台同构 AGV
- `"20x15, 4 agvs, 2 large 2 small"`：4 台 AGV，2 台 size=2、2 台 size=1
- `"width 25 height 20, 8 台 AGV，异构"`：25×20，8 台异构
- `"10x10, 2 agvs, 5 boxes, 2 receivers"`：可指定货架、站台数量

解析结果会转为结构化请求（地图尺寸、AGV 数量与尺寸等），再由环境配置 Agent 生成地图 JSON 并做校验（JSON Schema + 语义约束检查）；校验失败会自动重试（最多 3 次）。

---

### 3.2 阶段二：在已有地图上运行算法（generate-algorithm）

对**已有地图文件**用自然语言指定算法，运行仿真并输出指标与优化建议。

```bash
# 使用刚生成的地图，运行 A* 规划器（默认 TA 调度）
python -m mapf_agent.cli generate-algorithm "astar" --map-file config/maps/agent_generated.json

# 使用 CBS
python -m mapf_agent.cli generate-algorithm "use CBS" --map-file config/maps/map_25_20_het.json

# 指定随机种子与多次运行（会输出汇总指标）
python -m mapf_agent.cli generate-algorithm "CBS" --map-file config/maps/map_25_20_het.json --seed 42 --runs 3
```

**算法描述示例**：

| 输入 | 规划器 | 调度器 | 说明 |
|------|--------|--------|------|
| `"astar"` / `"A*"` | A\* | TA | 快速单智能体寻路，适合小地图 |
| `"CBS"` / `"cbs_fw"` | CBS-FW | TA | 冲突搜索，适合中等规模多 AGV |
| `"dhc"` | DHC | TA | 深度强化学习（需 PyTorch） |
| `"random"` | A\* | Random | 随机调度基线 |
| `"astar with optimize"` | A\* | TA | 启用迭代优化 |
| `"CBS 优化 5轮"` | CBS-FW | TA | 启用优化，5 轮迭代 |

输出包含仿真指标（如任务完成数、成功率、步数等）以及优化 Agent 的**文字建议**（如是否提高 max_steps、更换规划器等）。

---

### 3.3 两阶段串联（full）

先按自然语言生成地图并保存，再在该地图上运行指定算法。

```bash
# 生成地图并写入文件，再运行 astar
python -m mapf_agent.cli full "10x10, 2 agvs" "astar" -o config/maps/full_out.json

# 不写地图文件（会使用临时文件），运行 3 次取平均
python -m mapf_agent.cli full "20x15, 4 agvs, 2 large 2 small" "CBS" --runs 3 --seed 0
```

若阶段一失败，会直接报错并退出；阶段二会输出指标与建议。

---

### 3.4 交互式输入（interrupt/resume）

多轮输入模式：当工作流需要你补全缺失信息或做决策时，会在终端中显示 `Agent:` 并等待你回复；回复 `结束` 可退出当前会话。

```bash
python -m mapf_agent.cli

# 指定输出路径（生成地图时生效）
python -m mapf_agent.cli -o config/envs/maps/interactive_out.json

# 不使用 LLM
python -m mapf_agent.cli --no-llm
```

交互示例（示意）：

```
You: 帮我生成一个9*9的地图，4台agv, 并用TA调度器和CBS规划器运行
Agent: 环境/地图已就绪。是否要继续运行算法？（提供算法需求/结束）
You: 结束
```

---

## 四、在代码中调用

### 4.1 使用协调者（推荐）

```python
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)) or ".")

from mapf_agent.agents.coordinator import Coordinator

coord = Coordinator()

# 阶段一：生成地图
out1 = coord.run_phase1("20x15, 4 agvs, 2 large 2 small", output_path="config/maps/my_map.json")
if out1["ok"]:
    print("地图路径:", out1["map_path"])
    print("地图 JSON 键:", list(out1["map_json"].keys()))
else:
    print("失败:", out1["error"])

# 阶段二：在已有地图上跑算法
out2 = coord.run_phase2(
    map_path="config/maps/my_map.json",
    algorithm_nl="CBS",
    seed=42,
    num_runs=1,
)
if out2["ok"]:
    print("指标:", out2["metrics"])
    print("建议:", out2["suggestion"])

# 两阶段串联
out3 = coord.run_full(
    map_nl="10x10, 2 agvs",
    algorithm_nl="astar",
    map_output_path="config/maps/full.json",
)
```

### 4.2 使用 LangGraph 工作流

交互模式底层使用 LangGraph 状态图，也可直接调用：

```python
from mapf_agent.workflow.graph import build_graph

from langgraph.checkpoint.memory import MemorySaver
from langgraph.types import Command

graph = build_graph().compile(checkpointer=MemorySaver())
config = {"configurable": {"thread_id": "demo"}}

result = graph.invoke(
    {
        "user_input": "20x15 地图，4 台 AGV，用 CBS 跑仿真",
        "use_llm": True,
        "output_path": "",
        "map_path": "",
    },
    config=config,
)

# 如果触发 interrupt，LangGraph 会在 `__interrupt__` 里返回一个可恢复的中断信息
if result.get("__interrupt__"):
    # 这里给出一个示例 resume；实际可把 value["question"]/value["message"] 展示给用户
    result = graph.invoke(Command(resume="结束"), config=config)
```

工作流会自动完成：输入路由 → 解析 → 地图生成 → 校验 → 算法选择 → 仿真 → 优化分析。

### 4.3 单独使用各 Agent

```python
from mapf_agent.agents.input_parser import InputParserAgent
from mapf_agent.agents.env_config_agent import EnvConfigAgent
from mapf_agent.agents.algorithm_agent import AlgorithmAgent
from mapf_agent.agents.optimizer_agent import OptimizerAgent

# 输入解析
parser = InputParserAgent()
parsed = parser.parse("20x15, 4 agvs, 2 large 2 small", use_llm=True)

# 地图生成
env_agent = EnvConfigAgent()
result = env_agent.generate(parsed["map_config"], use_llm=True)

# 算法选择
algo_agent = AlgorithmAgent()
algo = algo_agent.select("CBS, optimize 3 rounds", use_llm=True)

# 优化建议
optimizer = OptimizerAgent()
suggestion = optimizer.suggest(
    metrics={"Task Success Rate": 0.7, "sim_steps": 500},
    current_config={"planner_type": "astar", "scheduler_type": "ta"},
    history=[],
    use_llm=True,
)
```

### 4.4 仅使用工具

不经过 Agent，直接校验地图或跑仿真：

```python
from mapf_agent.tools.validate_map import validate_map, validate_schema, validate_semantic
from mapf_agent.tools.run_simulation import run_simulation

# 校验地图：传入路径或 dict
result = validate_map("config/maps/template_map.json", trial_steps=0)
print(result)  # {"ok": True} 或 {"ok": False, "error": "..."}

# 分步校验
schema_ok = validate_schema(map_json)   # JSON Schema 结构校验
semantic_ok = validate_semantic(map_json)  # 语义约束（越界、重叠、ID 匹配）

# 运行仿真（会临时覆盖 SimConfig）
run_result = run_simulation(
    map_file="config/maps/template_map.json",
    planner_type="astar",
    scheduler_type="ta",
    seed=42,
    num_runs=1,
)
print(run_result["metrics"])
```

---

## 五、架构与模块说明

### 5.1 目录结构

```
mapf_agent/
├── README.md                  # 本使用说明
├── requirements.txt           # Agent 专属依赖
├── __init__.py                # 包入口
├── config.py                  # AgentConfig：LLM 模型、路径、默认参数；API key 从 api_key 文件读取
├── llm.py                     # LLM 服务层：OpenAI 兼容 API 封装，含重试与 JSON mode
├── cli.py                     # 命令行入口（单一入口：输入文本 -> interrupt/resume）
├── agents/                    # 各 Agent
│   ├── input_parser.py        # 输入解析 Agent（NL → 结构化 map_config + sim_config）
│   ├── env_config_agent.py    # 环境配置 Agent（map_config → 地图 JSON，含 LLM 生成 + 校验重试）
│   ├── algorithm_agent.py     # 算法选择 Agent（NL → planner/scheduler 配置）
│   ├── optimizer_agent.py     # 优化建议 Agent（仿真指标 → 改进建议，避免重复尝试）
│   └── coordinator.py         # 协调者（编排阶段一/二，提供便捷方法）
├── tools/
│   ├── validate_map.py        # 地图校验（JSON Schema + 语义约束 + 可选运行时试跑）
│   └── run_simulation.py      # 封装 single_run.run_single_episode，临时覆盖 SimConfig
├── workflow/
│   └── graph.py               # LangGraph 状态图：路由、解析、生成、校验、仿真、优化的完整工作流
├── prompts/                   # Prompt 模板
│   ├── router.txt             # 路由分类（map / algorithm / both）
│   ├── input_parser.txt       # 输入解析
│   ├── env_config.txt         # 地图生成
│   ├── algorithm.txt          # 算法选择
│   └── optimizer.txt          # 优化建议
├── knowledge/                 # 知识库
│   ├── map_schema.json        # 地图 JSON Schema
│   ├── defaults.yaml          # 领域默认值（AGV 尺寸范围、地图尺寸限制等）
│   └── examples/              # 示例地图
│       └── template_map.json
└── generated_planners/        # 预留：阶段二将来存放生成的新规划器代码
```

### 5.2 核心流程

```
用户输入（自然语言）
       │
       ▼
  ┌─────────────┐
  │  route_input │  路由分类：map / algorithm / both
  └──────┬──────┘
         │
    ┌────┴────┐
    ▼         ▼
┌────────┐ ┌───────────────┐
│ 地图流程│ │  算法流程       │
└───┬────┘ └──────┬────────┘
    │              │
    ▼              │
parse_map_input    │  输入解析（LLM / 正则回退）
    │              │  ↳ 缺必填字段时向用户追问
    ▼              │
generate_map       │  地图生成（LLM / 确定性回退）
    │              │  ↳ 校验失败自动重试（最多 3 次）
    ▼              │
apply_sim_config   │  应用仿真参数覆盖
    │              │
    └──────┬───────┘
           ▼
   select_algorithm     算法选择（LLM / 关键词匹配）
           │
           ▼
   run_simulation       运行 WareRover 仿真
           │
           ▼
   analyze_optimize     分析指标 + 优化建议
           │             ↳ 可迭代：更换算法或调整参数后重新仿真
           ▼
         结束
```

### 5.3 LLM 集成

`llm.py` 提供统一的 LLM 调用层：

- **`chat_completion()`**：发送聊天补全请求，支持重试（速率限制、API 错误自动指数退避，默认最多 3 次）。
- **`chat_completion_json()`**：启用 JSON mode 并自动解析返回的 JSON 对象。
- **`reset_client()`**：配置变更后强制重建 OpenAI 客户端。

支持任何 OpenAI 兼容端点（修改 `agent_config.llm_base_url`）。

### 5.4 AgentConfig 配置项

在 `config.py` 中通过 `AgentConfig` 数据类管理所有配置：

| 配置项 | 默认值 | 说明 |
|--------|--------|------|
| `llm_provider` | `"openai"` | LLM 提供商 |
| `llm_model` | `"gpt-4o"` | 使用的模型名称 |
| API key | `mapf_agent/api_key` | 从该文件第一行读取（唯一来源，已 gitignore） |
| `llm_base_url` | 华为云 MaaS | 自定义 API 端点 |
| `llm_temperature` | `0.2` | 生成温度 |
| `llm_max_tokens` | `4096` | 最大 token 数 |
| `validate_map_trial_steps` | `0` | 地图校验时试跑步数（0=仅做静态校验） |
| `default_simulation_seed` | `42` | 仿真默认随机种子 |
| `default_simulation_runs` | `1` | 仿真默认运行次数 |
| `default_max_steps` | `1000` | 仿真默认最大步数 |

---

## 六、运行测试

在项目根目录执行：

```bash
python -m pytest test/test_mapf_agent.py -v
```

所有测试使用 `use_llm=False`（规则/正则回退模式），无需 API key 即可运行。

测试覆盖：
- **地图校验**：文件/dict/非法 JSON、Schema 校验、语义约束（越界、重叠、ID 匹配、尺寸不一致）
- **输入解析**：基础解析、缺失信息检测、默认值填充、异构 AGV
- **地图生成**：基本生成、校验通过、AGV/wait_zone 匹配、goods_id 连续
- **算法选择**：关键词匹配（A\*、CBS、DHC、Random）、优化标志、迭代轮数
- **优化建议**：良好指标→满足、低成功率→换算法、步数上限→增加 max_steps、避免重复
- **协调者**：阶段一成功/失败/写文件/校验/异构
- **集成测试**：解析 → 生成 → 校验全流程

---

## 七、常见问题

**Q: 没有 API key 能用吗？**
A: 可以。添加 `--no-llm` 参数或设置 `use_llm=False`，所有 Agent 会降级为规则/正则回退模式。阶段一使用正则提取地图参数 + 确定性布局生成，阶段二使用关键词匹配算法 + 规则分析指标。

**Q: 如何使用非 OpenAI 的 LLM（如本地模型、第三方兼容 API）？**
A: 在 `mapf_agent/api_key` 中填入对应 key，并在代码或启动前设置 `agent_config.llm_base_url` 指向兼容端点，例如：
```python
from mapf_agent.config import agent_config
agent_config.llm_base_url = "http://localhost:11434/v1"
```

**Q: 地图生成失败怎么办？**
A: Agent 在 LLM 模式下会自动重试最多 3 次（将校验错误反馈给 LLM 重新生成）。如仍失败，可尝试 `--no-llm` 使用确定性生成，或简化自然语言描述。

**Q: 如何自定义 Prompt？**
A: 直接编辑 `mapf_agent/prompts/` 下的 `.txt` 文件。各 Prompt 对应不同 Agent：`router.txt`（路由）、`input_parser.txt`（解析）、`env_config.txt`（地图生成）、`algorithm.txt`（算法选择）、`optimizer.txt`（优化建议）。
