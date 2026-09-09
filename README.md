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

## 里程碑

| 阶段 | 内容 | 状态 |
|---|---|---|
| S0 | 工程骨架 + 协议模型 + 迁移 SQL + 健康检查 | ✅ |
| S1 | 注册闭环：scan → 校验 → tools 表入库 → 查询 | ⬜ |
| S2 | 任务闭环：PG 队列认领/心跳/恢复 + 三形态 Runner + SSE | ⬜ |
| S3 | 线性管线：逐步入队 + 模板变量解析 | ⬜ |

## 架构体检记录

每次结构性 commit 后必填一行；任一答「是」→ 先重构再继续功能。

体检五项：① 单模块 >300 行？ ② 依赖单向？ ③ 反模式命中？（入口写算法/路由写状态机/全局可变配置/跨层 import/垃圾抽屉/内存态无落盘/空壳目录）④ 新增工具需改 >3 既有模块？ ⑤ 协议是否仍最简？

| 日期 | 变更摘要 | ① | ② | ③ | ④ | ⑤ | 处置 |
|------|----------|---|---|---|---|---|------|
| | | | | | | | |

## 基础设施

- PostgreSQL 16（`docker-compose.yml`，本地 5433，弱口令仅限本地）
- Python 3.13 + uv；FastAPI + pydantic v2 + psycopg3
- 架构蓝图与决策留档见知识库 `02Sessions/02-个人/01Projects-项目/Web/01Result/`
