# CommAND

**小工具调度系统**——协议立骨，注册为籍，队列作脉，管线成势。

不做任何具体业务，只做三件事：**给小工具立规矩（协议）、上户口（注册表）、派活计（调度）**。工具的血肉来自 translee / commocr / rag 的拆分与未来的无限新增；前端筋络由 CommWEB 生长（仅与本项目 API 对话）。

## 快速开始

```bash
# 1. 启动 PostgreSQL（Colima / Docker，端口 5433）
docker compose up -d

# 2. 安装依赖
uv sync

# 3. 启动（API 8800；启动时自动执行版本化迁移）
bash run.sh            # 等价 uv run main.py serve

# 4. 注册小工具（扫描 tools/ 落位区）
uv run main.py register

# 5. 测试
uv run pytest
```

## 目录结构（七层契约）

```
command/
├── main.py / run.sh           # L0 入口：CLI（serve/register）+ app 工厂
├── config.py                  # L1 配置：frozen dataclass + .env 覆盖
├── deps.py                    # L2 装配：lru_cache 单例工厂，只装配不使用
├── api/                       # L3 路由：system / tools / tasks / pipelines + schemas
├── services/                  # L4 编排：registry / dispatch / pipeline / definition / lifecycle / recovery / query / rerun / batch / artifact / submission / completion / deletion / cleanup / subrun
├── core/                      # L5 调度域：protocol / runner / scheduler / pipeline / errors
├── store/                     # L6 PostgreSQL：db + migrations + 三仓储
├── models/                    # 数据模型集中（TaskView / ToolView / EventView）
├── tools/                     # 小工具落位区（每目录一工具，见 tools/README.md）
├── java/                      # Java 17/Spring Boot 平台（迁移期与 Python 并存）
│   ├── command-boot/          # 启动模块
│   ├── command-contract/      # 与框架无关的协议类型
│   ├── command-definition/    # 四类定义加载与校验
│   ├── command-tool-catalog/  # 工具目录边界
│   ├── command-workflow/      # 用户工作流
│   ├── command-run/           # 运行与任务生命周期
│   ├── command-runtime/       # Worker/Runtime Adapter
│   ├── command-api/           # HTTP API
│   └── command-persistence/   # JDBC/Flyway 唯一数据库边界
└── tests/                     # 镜像 core/ 结构，Fake 客户端零外部依赖
```

Java 平台使用 Java 17 和 Spring Boot 3.5.7，已具备定义加载/校验、类型化工作流、运行与任务生命周期、Spring JDBC 持久化端口和 PostgreSQL adapter。Flyway 以 Python migration 001~022 为历史基线，Java 增量从 V23 开始；默认禁用。定义启动时以 classpath 资源作为种子，在存在 DataSource 时幂等写入 `command_definitions` 并从 PostgreSQL 读取校验；运行定义快照通过 `run_definition_snapshots` 以 insert-only 方式绑定不可变定义版本。迁移目标不是逐文件翻译 Python，而是按 Tool、Capability Pipeline、Workflow、Workbench 四层重新提纯和组合。

运行提交当前已具备纯领域计划器：Workflow → CapabilityPipeline → 首个 Tool step 会生成运行 ID、任务 handle、定义快照集合和首任务输入；首步 subrun 暂明确拒绝。真正持久化前会先完成新架构的运行、步骤、任务表设计，不把旧 `pipelines`/`tasks` 表作为长期模型。
Clean schema 已在本地 `command_dev.command_runtime` 验证：独立 Flyway V1 创建 `runs`、`run_steps`、`task_executions`、`run_events`、`task_events`、`artifacts`、`command_definitions`、`run_definition_snapshots`；不创建旧表。`public` 旧表仅为当前迁移参考，最终切换后清理。
新运行提交已通过 clean schema 原子写入：一次事务创建 `runs`、定义快照、`run_steps` 和首个 `task_executions`；重复运行主键冲突时整体回滚，不产生半成品。
Clean `task_executions` 已支持 `SKIP LOCKED` 认领、worker 心跳校验、terminal 完成和 attempt 递增回队；worker 不匹配或终态任务不能继续更新。
Clean `run_events/task_events` 已支持 PostgreSQL 生成事件 ID、JSON detail 追加和 `afterId` 增量查询，后续 SSE 直接消费新事件表。
Clean 任务完成收口已在单事务内更新 `task_executions`、`run_steps`、`runs` 并追加两类事件；worker CAS 保证重复完成不重复推进或写事件。
Clean 多步骤推进已独立为 `CleanStepCoordinatorRepository`：成功步骤原子创建下一 `run_step/task_execution` 并保持 run running；最后一步才收口 run succeeded。
`PipelineExecutionPlanner` 已将 `CapabilityPipelineDefinition` 的 Tool steps 转换为有序执行计划；复合定义引用明确拒绝，必须经过独立 subrun 边界，不会伪装成普通 Tool。
Clean 首次提交现在接收完整 Pipeline 计划：冻结全部定义和 task ID，但只落库首个 queued step/task，后续步骤由成功推进事务按顺序创建。
Coordinator 通过当前 step index 消费冻结的 `PipelineRunSubmissionPlan`，校验 runId 归属，不在运行中重新解析定义。
失败收口独立更新 task/step/run 并追加失败事件，不创建后续步骤；worker CAS 与重复失败均保持幂等。
取消与中断使用不同终态：用户取消为 `cancelled`，进程/worker 中断为 `interrupted`；两者均通过新表原子收口，不创建后续步骤。
恢复只针对 `interrupted`：保留历史执行记录，创建递增 attempt 的 queued retry；`cancelled`、`failed` 和成功运行不会被恢复。
恢复达到 `max_attempts` 时保持 interrupted，不再创建 retry；恢复事务锁定 run/step/task，重复或并发恢复不会重复创建 attempt。
Clean 运行查询只读取新 `runs/run_steps/task_executions/run_events`，详情返回每个 step 的最新 task attempt，事件支持 `afterId` 增量读取。
Clean artifact 只登记外部对象存储索引，不把文件字节写入数据库；支持按 run/step 查询、artifact ID 幂等登记和外键级联清理。
`command-runtime` 已提供 `HttpWorkerRuntime`：Java 通过 HTTP 创建/查询/取消 Worker job，并按 sequence 读取 Worker 事件；Worker 不访问平台数据库。
`TaskDispatcher` 已提供 task→Worker→task 终态编排端口，成功、失败、取消和 Worker 异常均走独立收口路径。

当前内部边界：Java 新平台按 Definition、Workflow、Run、Step、Task、Runtime、Artifact、Audit 分层设计；Python `api/core/services/store` 只作为重构参考，不作为 Java 长期依赖。旧 API、旧表、旧运行模型和兼容代理不进入重构完成态；历史数据通过一次性离线迁移转换或归档后停止旧模型。

## 工具协议 v1 摘要

一个工具 = 一个目录 + 一份 `tool.toml`：

| 节 | 必填字段 | 说明 |
|---|---|---|
| `[tool]` | id / name / version | id 点分三段 `<域>.<对象>.<动作>`，全局唯一 |
| `[io]` | input/output_schema + input/output_types | JSON Schema 2020-12（文件引用或内联）；类型标签 `<域>.<形态>` 供 v3 接线 |
| `[runtime]` | kind / entry | inproc（进程内函数）/ subprocess（任意语言）/ http（远端） |
| `[resources]` | timeout_s / concurrency | max_attempts 仅领域错误触发重试 |

调用信封自包含（`{"tool": id, "input": {...}}`）；长任务返回 handle（`t_` 前缀）驱动生命周期，语义对齐 MCP 2026-07-28（Tasks 扩展）。

## 集成工具拆解模版

> 面对一个既有集成工具（如 translee / commocr），把本节直接喂给 LLM，即可按统一方法产出拆解与调度。

**目标**：把集成工具拆为零耦合通用小工具，并用 CommAND 管线重新集成为「全自动流」。

**第一步 · 理解**：梳理工作流关键节点（N1..Nn：输入/变换/输出），区分「节点语义」（进管线）与「成本机制」（内化）。必须读源码核实——用户口述的功能点可能不存在于代码。

**第二步 · 抽象、提炼**：关键节点 → 复用性极高的通用工具，逐个过**耦合度=0 三检验**：

| 检验 | 标准 |
|---|---|
| 类型化 I/O | 工具间只经 schema 契约通信；对应关系（映射/索引）一律显式为数据 |
| 可独立成立 | 换掉上下游，工具依然可用（说得出第二消费场景才算通过） |
| 机制内化 | 重试/缓存/降级/含环机制留在工具内部（线性管线无环，含环机制不得拆出） |

**第三步 · CommAND 核心**：节点 → `tool.toml` 注册 → 管线模板变量接线（`{{step[N].output.x}}`）串成原工具的等价全自动流 → 注册 + pytest + 冒烟 → （可选）CommWEB 流工具入口。

**产出清单**：工具清单表（tool id / 抽象自 / I/O 类型 / 独立复用场景）+ 管线定义 + 裁定记录（每个「不拆」的决定写明依据）+ 实施顺序。参考实证：知识库蓝图第九章「Translee 拆解 v2」。

## 里程碑

| 阶段 | 内容 | 状态 |
|---|---|---|
| S0 | 工程骨架 + 协议模型 + 迁移 SQL + 健康检查 | ✅ |
| S1 | 注册闭环：scan → 校验 → tools 表入库 → 查询 | ✅ |
| S2 | 任务闭环：PG 队列认领/心跳/恢复 + 三形态 Runner + SSE | ✅ |
| S3 | 线性管线：逐步入队 + 模板变量解析 | ✅ |

## 架构体检记录

每次结构性 commit 后必填一行；任一答「是」→ 先重构再继续功能。

体检五项：① 单模块 >300 行？ ② 依赖单向？ ③ 反模式命中？（入口写算法/路由写状态机/全局可变配置/跨层 import/垃圾抽屉/内存态无落盘/空壳目录）④ 新增工具需改 >3 既有模块？ ⑤ 协议是否仍最简？

| 日期 | 变更摘要 | ① | ② | ③ | ④ | ⑤ | 处置 |
|------|----------|---|---|---|---|---|------|
| 2026-09-09 | S0 骨架 | 否 | 是 | 无 | 0 模块 | 是 | 通过 |
| 2026-09-09 | S1 注册闭环（tool_repo + 参考工具 text.llm.translate + 集成测试） | 否 | 是 | 无 | 0 模块（manifest 即入） | 是 | 通过 |
| 2026-09-09 | S2 任务闭环（migration 002 path 列 + Runner 三形态 + Scheduler + SSE + dev.string.reverse 参考工具） | 否 | 是 | tools 表加 path 列（002 迁移） | 0 模块（manifest 即入） | 是 | 通过 |
| 2026-09-09 | S3 线性管线（migration 003 pipeline_runs + 三变量模板解析 + scheduler 推进钩子 + pipelines API） | 否 | 是 | 新增 pipeline_runs 表（003 迁移） | 0 模块（管线定义经 API 注册） | 是 | 通过 |
| 2026-09-09 | 工具视图附带 tags（存 manifest JSONB，无新列；tool.toml [tool] tags 随注册下发） | 否 | 是 | 无 schema 变更 | 0 模块（tool.toml 加 tags 即生效） | 是 | 通过 |

## 基础设施

- PostgreSQL 16（`docker-compose.yml`，本地 5433，弱口令仅限本地）
- Python 3.13 + uv；FastAPI + pydantic v2 + psycopg3
- 架构蓝图与决策留档见知识库 `02Sessions/02-个人/01Projects-项目/Web/01Result/`
| 2026-09-10 | 协议 v2：GET /api/meta/site 站点清单下发（视图集/顺序/落地页/when 能力条件），渲染控制权移交前端声明驱动（蓝图03） | 是 | — | 否 | 是（视图声明变更即前端导航变更） | 通过 |
