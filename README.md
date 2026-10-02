# CommAND

**小工具调度系统**——协议立骨，注册为籍，队列作脉，管线成势。

不做任何具体业务，只做三件事：**给小工具立规矩（协议）、上户口（注册表）、派活计（调度）**。工具能力按通用 Tool、Capability Pipeline、Workflow 和 Workbench 组合；前端筋络由 CommWEB 生长（仅与本项目 API 对话）。

## 快速开始

```bash
# 1. 启动 PostgreSQL（按 application.yml 配置连接）
# 2. 启动 Java API（默认 8080；启动时执行 Flyway 并校验 Hibernate Schema）
cd java
COMMAND_DB_PASSWORD=root mvn spring-boot:run -pl command-boot -am

# 3. 运行 Java 测试
mvn test
```

## 目录结构（七层契约）

```
command/
├── java/                      # Java 17/Spring Boot 平台
│   ├── command-boot/          # 启动模块
│   ├── command-contract/      # 与框架无关的协议类型
│   ├── command-definition/    # 四类定义加载与校验
│   ├── command-tool-catalog/  # 工具目录与版本解析边界
│   ├── command-tools/         # Java Tool SPI 与通用原子工具
│   ├── command-workflow/      # 用户工作流
│   ├── command-run/           # 运行与任务生命周期
│   ├── command-runtime/       # Worker/Runtime Adapter
│   ├── command-api/           # HTTP API
│   └── command-persistence/   # Hibernate/Flyway 唯一数据库边界
└── data/                      # 本地运行数据与输出目录（不纳入代码职责）
```

Java 平台使用 Java 17 和 Spring Boot 3.5.7，已具备定义加载/校验、类型化工作流、运行与任务生命周期，以及统一 Hibernate/JPA 持久化。PostgreSQL、Flyway 和 Hibernate 现在是默认生产启动依赖：`application.yml` 是唯一生产配置事实源，读取 `COMMAND_DB_URL`、`COMMAND_DB_USERNAME`、`COMMAND_DB_PASSWORD`，数据库不可用或密码缺失时应用启动失败。Flyway 使用 clean migration，Hibernate 使用 `ddl-auto=validate`。纯单元测试通过显式排除数据库自动配置隔离，不再把无数据库启动作为生产验收目标。迁移目标不是逐文件翻译 Python，而是按 Tool、Capability Pipeline、Workflow、Workbench 四层重新提纯和组合。
`command-boot` 根包只保留 `CommandApplication`；Spring 装配和类型化属性按 `configuration.definition`、`configuration.tool`、`configuration.runtime` 归档，定义加载、LLM Tool 注册和运行时生命周期不再与启动入口混放。
`command-tools` 按 `tools.spi`、`tools.llm`、`tools.records`、`tools.text`、`tools.table`、`tools.txt`、`tools.docx`、`tools.ocr`、`tools.file`、`tools.pdf` 归类：SPI 只定义 Java Tool、进度事件和注册表；LLM 类提供 `llm.chat.complete`、`llm.chat.complete-json` 两个通用原子能力及 OpenAI-compatible client。当前已完成 Java 化并接入 INPROC 运行时的纯数据能力包括 `records.merge.crosspage`、`records.export.csv`、`records.export.xlsx`、`text.dedup.values`、`text.verify.fidelity`、`txt.extract.text`、`docx.extract.text`、`table.classify.columns`，以及 OCR 的 `spec.template.resolve`、`ocrdb.extract.units`、`ocrdb.write.records`、`records.view.query`。文件适配器包括受控 `file.inspect`、PDF 文本页 `pdf.extract.pages`、PDF 页面渲染 `pdf.pages.to.images`、DOCX 文本提取 `docx.extract.text` 和独立视觉模型适配 `ocr.vision.extract`；`ocr.extract-by-template` 已串成 Java Pipeline。翻译工作台新增可复用的 `text.translate` Tool、`translate.text`、`translate.file-text` 和 `translate.file-docx` Workflow，OCR 工作台通过 `ocr.studio` 视图和 `/api/ocr/*` 协议投影注册到 CommWEB。OCR 正式结果库、模板版本 CRUD、ViewSpec CRUD、记录查询和 XLSX 导出均已接入 `command_runtime` Hibernate/Flyway 持久化。PDF 扫描页批量识别和 XLSX 文件翻译仍待适配，不会显示为可执行能力。各 Tool 的输入输出协议由独立 Tool Catalog manifest/schema 管理。
首批纯数据 Tool 已通过真实 Spring/PostgreSQL Scheduler 验收：后台任务领取、Java INPROC job、持久化输出、progress 事件、两步 Pipeline 输入映射和最终 Run 收口均在生产装配链路中验证。DOCX 文本提取只覆盖段落与表格纯文本，不保留 Word 样式、文本框、修订和复杂布局。XLSX 目前已完成工作表/行列/单元格值结构提取，但整表翻译与原工作簿回写仍待批处理和导出适配；迁移能力仍以真实运行链路验收，不以 Java Bean 注册作为完成标准。
`command-definition` 按 `loader`、`validation`、`registry` 三个包归档：加载/解析、跨定义校验、不可变定义注册分别承担独立职责。它只维护 Workflow、Capability Pipeline 等定义，不吸收 `command-tool-catalog` 的 ToolDescriptor 目录，也不直接依赖 Java Tool 实现；Tool 描述目录与可执行实现继续保持独立。
`command-tool-catalog` 现在从独立的 `tools/index.txt` 加载 Java Tool manifest；`DefinitionConfiguration` 会排除数据库历史 `kind=tool` 记录，避免旧数据重新污染 DefinitionRegistry；`RunSubmissionPlanner` 和 `PipelineExecutionPlanner` 改由 ToolCatalog 校验 Tool 是否存在且 active，再冻结到运行计划。OCR 旧 HTTP 占位 manifest 已删除，未迁移能力必须通过新的 Java Tool 或明确的外部适配器注册。

运行提交当前已具备纯领域计划器：Workflow → CapabilityPipeline → 首个 Tool step 会生成运行 ID、任务 handle、定义快照集合和首任务输入；首步 subrun 暂明确拒绝。真正持久化前会先完成新架构的运行、步骤、任务表设计，不把旧 `pipelines`/`tasks` 表作为长期模型。
Clean schema 已在本地 `command_dev.command_runtime` 验证：Flyway V1/V2 创建运行时表，V3 创建 `ocr_templates`、`ocr_result_sets`、`ocr_records`、`ocr_views`，V4 刷新已有 OCR Workflow/Pipeline 定义；不创建旧表。`public` 旧表仅为当前迁移参考，最终切换后清理。
新运行提交已通过 clean schema 原子写入：一次事务创建 `runs`、定义快照、`run_steps` 和首个 `task_executions`；重复运行主键冲突时整体回滚，不产生半成品。
Clean `task_executions` 已支持 `SKIP LOCKED` 认领、worker 心跳校验、terminal 完成和 attempt 递增回队；worker 不匹配或终态任务不能继续更新。
Clean `run_events/task_events` 已支持 PostgreSQL 生成事件 ID、JSON detail 追加和 `afterId` 增量查询，后续 SSE 直接消费新事件表。
Clean 任务完成收口已在单事务内更新 `task_executions`、`run_steps`、`runs` 并追加两类事件；worker CAS 保证重复完成不重复推进或写事件。
Clean 多步骤推进已独立为 `CleanStepCoordinatorRepository`：成功步骤原子创建下一 `run_step/task_execution` 并保持 run running；最后一步才收口 run succeeded。
`PipelineExecutionPlanner` 已将 `CapabilityPipelineDefinition` 的 Tool steps 转换为有序执行计划；复合定义引用明确拒绝，必须经过独立 subrun 边界，不会伪装成普通 Tool。步骤可通过 `input` 显式声明 `$run.<path>` 和 `$step.<stepId>.<path>` 引用，解析器支持嵌套对象/数组并在引用不可用时明确失败。
Clean 首次提交现在接收完整 Pipeline 计划：冻结全部定义和 task ID，但只落库首个 queued step/task，后续步骤由成功推进事务按顺序创建。
Coordinator 通过当前 step index 消费冻结的 `PipelineRunSubmissionPlan`，校验 runId 归属；后台推进时读取原始 run input 与已完成步骤 output 后解析下一步输入。未配置 `input` 的步骤继续使用初始输入。
Pipeline 的 step/task ID 由 `PipelineExecutionIdentifiers` 按 `runId + stepIndex` 确定性生成；提交计划、首次落库和后台恢复共用同一规则，避免冻结计划与实际运行标识分叉。恢复 attempt 还把 attempt 编入确定性任务 ID，因此不会生成 `:retry:` 形式的临时主键。
失败收口独立更新 task/step/run 并追加失败事件，不创建后续步骤；worker CAS 与重复失败均保持幂等。
取消与中断使用不同终态：用户取消为 `cancelled`，进程/worker 中断为 `interrupted`；两者均通过新表原子收口，不创建后续步骤。
恢复只针对 `interrupted`：保留历史执行记录，创建递增 attempt 的 queued retry；`cancelled`、`failed` 和成功运行不会被恢复。
恢复达到 `max_attempts` 时保持 interrupted，不再创建 retry；恢复事务锁定 run/step/task，重复或并发恢复不会重复创建 attempt。
Clean 运行查询只读取新 `runs/run_steps/task_executions/run_events`，详情返回每个 step 的最新 task attempt，事件支持 `afterId` 增量读取。
Clean artifact 只登记外部对象存储索引，不把文件字节写入数据库；支持按 run/step 查询、artifact ID 幂等登记和外键级联清理。
`command-runtime` 已提供 `HttpWorkerRuntime`：Java 通过 HTTP 创建/查询/取消 Worker job，并按 sequence 读取 Worker 事件；Worker 不访问平台数据库。
`command-runtime` 同时提供 `InProcessToolRuntime`：Java 原生工具通过相同的 job handle、状态、事件游标和取消接口执行；`ToolRuntimeRouter` 以 Tool Catalog 声明的 `runtime` 和 `status` 为准，`inproc` Tool 必须存在 Java Tool Registry 实现，`http` Tool 必须配置 HTTP Worker，`TaskDispatcher` 不区分工具实现语言或运行形态。
Tool 身份统一使用公共契约 `ToolKey(id, version)`：Pipeline 冻结的 Tool 版本从 `run_steps.definition_version` 贯通到 claim、`TaskExecution`、`WorkerJobRequest` 和 `JavaToolRegistry`，Router 按请求版本选择 Java INPROC 实现，避免将运行时版本硬编码为 v1。
`command-runtime` 已按职责整理为 `worker`、`tool`、`dispatch`、`scheduler`、`recovery` 五个包：Worker 协议与 HTTP Adapter、Java INPROC 路由、任务执行编排、调度生命周期、陈旧任务恢复分别归属独立边界；生产与测试目录采用相同结构，不再把全部运行类堆在根包。
`TaskDispatcher` 已提供 task→Worker→task 终态编排端口，成功、失败、取消和 Worker 异常均走独立收口路径。
`TaskDispatcher` 已支持长任务 Worker job：对 `queued/running` 做有界轮询，按 `afterSequence` 单调游标转发事件，重复 sequence 不重复写入，并在终态后执行一次最终事件 drain；`job-poll-interval` 与 `job-timeout` 可配置。
当平台先将当前 worker 持有的 task 标记为 `cancelled` 时，dispatcher 会调用 Worker `cancelJob`；Worker 终态返回后不会重复写平台取消收口。Worker 自发返回 `cancelled` 仍走正常平台 `cancel()` CAS。
长任务轮询期间，dispatcher 按 `heartbeat-interval` 调用 clean task heartbeat；heartbeat CAS 返回 false 表示 worker ownership 丢失，立即停止 Worker 轮询并进入 runtime failure。默认 heartbeat interval 为 `30s`，且必须短于 `job-timeout`。
Worker job 创建成功后的超时、ownership 丢失、轮询中断、未知状态或 HTTP 失败会执行 best-effort `cancelJob`，避免留下孤儿任务；清理失败作为 suppressed exception 保留，不覆盖原始 runtime error。平台取消已发送时不重复 cancel。
若 heartbeat CAS 返回 false，dispatcher 认定旧 worker 已失去 task ownership：会清理 Worker job 并抛出 runtime error，但不会再用旧 worker 身份写 `failed` 终态，后续由 stale recovery/新的持有者处理。
`CleanRecoveryRepository.recoverStaleTasks(staleBefore, limit)` 已支持并发安全的 stale running task 恢复：旧 execution 标记 `interrupted`，创建下一 attempt 的 queued execution，恢复 run/step 为 running，并写 recovery events；达到 max attempts 的任务不自动重试。当前已接入独立的 scheduler recovery loop，默认关闭，不与普通 task dispatch 共用线程。
`CleanRecoveryPoller` 提供独立的单次 recovery poll，`CleanRecoveryLoop` 提供与普通 task scheduler 分离的后台生命周期；配置位于 `command.clean.scheduler.recovery-enabled/stale-after/recovery-batch-size/recovery-poll-interval`，默认关闭。显式开启后独立启动 recovery 线程，按 poll interval 扫描并受 batch size 限制；单轮异常记录后继续，应用关闭时停止线程。Recovery 不依赖 Worker 健康检查，也不与 task dispatch 共用线程。

`GET /api/system/recovery` 提供只读运行状态：enabled/active、poll/recovery/error 计数、最近轮询时间、最近恢复数量和最新错误摘要。指标由 Recovery loop 内部独立维护，不暴露任务输入、任务 ID 或数据库连接信息。
`command-api` 按 `controller`、`application`、`stream`、`model`、`port` 五个包组织：HTTP 路由、运行提交与查询、SSE 事件生命周期、API DTO、运行状态端口分别归属独立边界；Controller 不直接承担运行编排或流生命周期管理。
`CleanScheduler` 已提供无状态 `pollOnce(workerId)` 边界：一次只认领并派发一个 clean task，返回是否实际派发；`CleanSchedulerLoop` 在默认数据库装配下仅于 `enabled=true` 时由 `SchedulerActivation` 完成可选 readiness check 后启动。
`CleanSchedulerLoop` 已提供可控后台生命周期：按固定间隔调用单次 poll，`stop()/close()` 中断等待并等待线程退出；单轮异常交给 error handler 后继续轮询。Worker 地址、identity、超时和轮询策略均由 `command.clean.scheduler` 配置并在 Bean 创建时校验。
Scheduler 配置位于 `command.clean.scheduler`：默认 `enabled=true`，使用 `COMMAND_WORKER_ID`（默认 `command-local-1`）作为 Worker 身份，启动后创建 INPROC runtime、runtime router、task execution port、dispatcher 和后台 loop；`poll-interval` 与任务超时在 Bean 创建时校验。`worker-base-url` 为可选的外部工具回退配置。
配置 `worker-base-url` 时，scheduler 启动前执行 `GET {worker-base-url}/health`；只有 2xx 响应才启动后台 loop。未配置时按 Java-only 模式启动，不创建 HTTP Worker 或健康检查；遇到未注册 Tool 时明确失败，不静默选择错误 runtime。
`SchedulerActivation` 统一管理 activate/deactivate/close；当前 Spring 启用配置在 Bean 初始化时执行一次 activate，未来动态恢复需创建新的 loop/activation 实例，不复用已停止的 executor。
`SchedulerMetrics` 已记录 scheduler 自身的 poll/dispatched/idle/error 计数、最后轮询时间、最后错误摘要和 active 快照；计数线程安全且暂存内存，不引入 Micrometer/Actuator，也不记录任务输入输出。
已提供只读状态端点 `GET /api/system/scheduler`：默认或 scheduler disabled 时返回 enabled=false 的零值快照；启用时返回共享 metrics 的 active、计数和错误摘要，不返回 Worker 地址、任务输入、任务输出或控制操作。
`PersistentTaskExecutionPort` 已将 dispatcher 接入 clean persistence：认领同时把 queued step/task 原子切换为 running，返回冻结的 toolId、attempt 和输入；成功路径再由 clean completion 事务同步收口 step/run 并追加事件。clean 持久层已批量切换到 Hibernate/JPA：普通提交、查询、事件、制品使用 EntityManager/JPQL，认领、CAS、恢复、收口和多步骤推进使用 Hibernate Native Query，不再由 Spring 装配 JDBC 业务适配器。
`command_definitions` 已完成 Hibernate/JPA 迁移：实体、Repository 和 Adapter 统一位于 `persistence.definition`，复合主键和 JSONB 由 Hibernate 管理，Spring Data Repository 提供 active 查询，`JpaDefinitionRepositoryAdapter` 负责 insert-only 幂等写入；该表不再由 JDBC 适配器承担运行时写入。
`command-persistence` 不再使用根包堆叠或 `entity/jpa` 技术分层，生产代码按 `config`、`support`、`definition`、`run`、`step`、`task`、`event`、`artifact` 领域归档；实体与对应仓储放在同一领域包，测试目录采用相同结构。
PostgreSQL、Flyway 和 Hibernate 是默认生产装配，`application.yml` 固定 clean migration 与 `ddl-auto=validate`；数据库缺失、迁移校验失败或实体映射不一致都会阻止应用启动，不再存在无数据库生产模式。
`command_definitions` 及 clean run/step/task/event/artifact 的 Hibernate EntityManagerFactory 已通过真实 `command_dev.command_runtime` schema 校验。clean runtime 已删除旧 `RunRepository`、`TaskRepository`、JDBC SQL/RowMapper 和相关 LocalOpsRunner，不再保留第二套持久层。真实 PostgreSQL 回归已覆盖默认应用启动、Flyway V1-V2 校验、Hibernate schema validation、定义查询、运行提交/查询/事件/SSE、Scheduler disabled 状态与 Recovery enabled 生命周期；事务仓储使用可代理类型，Recovery 后台线程由 Spring `SmartLifecycle` 在上下文完成后启动。
Java clean API 已提供 `POST /api/runs`、`GET /api/runs/{runId}`、`GET /api/runs/{runId}/events?afterId=0&limit=100` 和 `GET /api/runs/{runId}/events/stream?afterId=0`：提交接口只接收 Workflow、可选版本和用户输入，详情接口只返回运行/步骤/最新任务状态，事件接口按数据库事件 ID 增量读取 run events，stream 接口在终态 run 发送完待处理事件后自动关闭；API 不暴露定义快照、内部 task ID 或任务输入。默认生产装配已通过真实 PostgreSQL MockMvc 集成测试，重复运行数据自动清理。

当前内部边界：Java 新平台按 Definition、Workflow、Run、Step、Task、Runtime、Artifact、Audit 分层设计。旧 API、旧表、旧运行模型和兼容代理已从代码仓库清除；历史数据通过一次性离线迁移转换或归档后不再由 CommAND 旧模型管理。

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
- Java 17 + Spring Boot 3.5.7；PostgreSQL + Flyway + Hibernate/JPA
- 架构蓝图与决策留档见知识库 `02Sessions/02-个人/01Projects-项目/Web/01Result/`
| 2026-09-10 | 协议 v2：GET /api/meta/site 站点清单下发（视图集/顺序/落地页/when 能力条件），渲染控制权移交前端声明驱动（蓝图03） | 是 | — | 否 | 是（视图声明变更即前端导航变更） | 通过 |
