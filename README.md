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
├── services/                  # L4 编排：registry / dispatch / pipeline
├── core/                      # L5 调度域：protocol / runner / scheduler / pipeline / errors
├── store/                     # L6 PostgreSQL：db + migrations + 三仓储
├── models/                    # 数据模型集中（TaskView / ToolView / EventView）
├── tools/                     # 小工具落位区（每目录一工具，见 tools/README.md）
└── tests/                     # 镜像 core/ 结构，Fake 客户端零外部依赖
```

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
