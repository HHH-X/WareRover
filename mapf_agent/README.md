# MAPF Agent

MAPF Agent 是 WareRover 仿真器上的自然语言辅助入口，可以生成地图、修改配置、生成或优化算法，并运行仿真获取指标或可视化过程。

## 命令行使用

```bash
python -m mapf_agent
```

输入自然语言指令后，Agent 会按 LangGraph 工作流执行；如果需要补充信息，会在命令行继续追问。

## Web UI

```bash
python -m mapf_agent.server
```

默认启动：

- 页面地址：`http://localhost:8010/mapf_agent/web/index.html`
- Agent WebSocket：`ws://localhost:8766`

可选参数：

```bash
python -m mapf_agent.server --http-port 8010 --ws-port 8766 --no-browser
```

Agent 页面展示的是自然语言交互、任务进度、产物路径和仿真指标。页面中的“打开仿真可视化”只会打开 `frontend/` 可视化查看器，不会直接启动一条默认仿真；Agent 正在处理任务时也可以随时打开该页面。“打开优化进度”会打开 OpenEvolve 可视化页面，用于查看优化产生的 checkpoint。

Agent 执行时，后端会把节点内部输出的阶段日志实时推送到页面中，作为运行过程展示。

## 与仿真器 UI 的关系

Agent Web UI 会管理一条可视化服务：

- 页面地址：`http://localhost:8000/frontend/index.html`
- 可视化 WebSocket：`ws://localhost:8765`

点击“打开仿真可视化”后，页面会连接到 Agent 管理的可视化服务并等待数据。真正的仿真过程由 Agent 指令触发：当工作流执行到 `mapf_agent/nodes/run.py` 的运行仿真节点时，会使用当前 Agent 状态中的地图、配置和生成算法运行仿真。

可视化页面是可选观察者：如果没有打开页面，后端仍会正常完成仿真并返回指标；如果页面已经打开，或者在仿真运行中途打开，后端会向页面推送 `init` / `update` 数据用于展示过程。

Agent 页面中的“停止退出”用于结束当前 Agent 服务。它在 Agent 忙时仍可点击，并会强制退出后端进程。

## 与 OpenEvolve 可视化的关系

Agent Web UI 会管理一条 OpenEvolve 优化可视化服务：

- 页面地址：`http://localhost:8080/`
- 数据目录：`output/evolve/`

点击“打开优化进度”后，后端会在 `mapf_agent` 侧启动 OpenEvolve 自带的 visualizer，并把 `--path` 指向 MAPF Agent 默认优化输出目录。visualizer 会展示该目录下最新的 checkpoint；新的优化运行生成 checkpoint 后，刷新或重新打开页面即可看到最新进度。该集成不修改 `openevolve/` 下载源码。

如果缺少可视化依赖，请先安装：

```bash
pip install -r openevolve/scripts/requirements.txt
```

独立仿真器仍可通过以下命令启动：

```bash
python run.py
```

它会按项目默认配置启动传统可视化仿真流程。不要同时运行独立 `run.py` 和 Agent 可视化服务，因为二者默认使用相同的 `8000` / `8765` 端口。
