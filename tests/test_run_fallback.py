"""H7 失败降级全链路：图片翻译流遇「能力不可用」（退出码 5 → ToolUnavailableError）时，
不重试、run 落 failed(kind=unavailable)，并按 on_failure.fallback_flow **自动新起一条降级 run**。

用 tests.string.unavailable（退出码 5 演示工具）+ 两条真流 + 真 DB（dev PG）验证：
1) 原 run failed 且 error.kind=unavailable、message 注明降级目标；
2) 新 run 的 fallback_of 指向原 run、pipeline_id = 降级流，且跑通 succeeded；
3) 两条 run 各留一条 run_fallback 审计事件；
4) 降级流自身不再降级（无链式）。
"""
from __future__ import annotations

from pathlib import Path

import pytest

from config import load_config
from core.protocol import ToolManifest
from core.runner import Runner
from core.scheduler import Scheduler
from services.dispatch_service import DispatchService
from services.pipeline_service import PipelineService
from store.db import Db
from store.event_repo import EventRepo
from store.pipeline_repo import PipelineRepo
from store.run_event_repo import RunEventRepo
from store.task_repo import TaskRepo
from store.tool_repo import ToolRepo

REPO_ROOT = Path(__file__).resolve().parent.parent
from tests._dbutil import db_reachable  # noqa: E402

DB_URL = "postgresql://command_dev:root@192.168.8.41:5432/command_dev"

UNAVAILABLE_ID = "tests.string.unavailable"
PRIMARY = "test.fallback.primary"
SECONDARY = "test.fallback.secondary"
NO_FALLBACK = "test.no.fallback"   # P2：能力不可用且**未声明**降级流 → 应暂停而非失败


def _db_reachable() -> bool:
    return db_reachable(DB_URL)


pytestmark = pytest.mark.skipif(not _db_reachable(), reason="dev PG 不可达，跳过集成测试")


@pytest.fixture
def stack(tmp_path):
    db = Db(DB_URL)
    db.apply_migrations()
    tool_repo = ToolRepo(db)
    task_repo = TaskRepo(db)
    tool_repo.upsert(
        ToolManifest.from_toml(REPO_ROOT / "tests" / "fixtures" / "string_unavailable" / "tool.toml"),
        path="tests/fixtures/string_unavailable")
    dispatch = DispatchService(db=db, task_repo=task_repo, tool_repo=tool_repo,
                               event_repo=EventRepo(db))
    pipeline_repo = PipelineRepo(db)
    run_event_repo = RunEventRepo(db)
    service = PipelineService(db=db, pipeline_repo=pipeline_repo, task_repo=task_repo,
                              tool_repo=tool_repo, dispatch_service=dispatch,
                              run_event_repo=run_event_repo)
    scheduler = Scheduler(db=db, runner=Runner(), task_repo=task_repo, tool_repo=tool_repo,
                          event_repo=EventRepo(db), config=load_config(".env"),
                          on_task_done=service.advance)
    # 降级目标先注册（主流的 on_failure 指向它）。
    # 它额外引用 `{{ input.model }}` —— 主流 input 里**没有**这个键（图片流用 image_model），
    # 用来验证「降级继承 input」不因缺键而失败（I1）。
    service.register(SECONDARY, "降级目标流（文本翻译等价物）", [
        {"tool": UNAVAILABLE_ID,
         "input": {"file": "{{ input.file }}", "marker": "NEVER", "model": "{{ input.model }}"}},
    ])
    # 主流：marker 固定 UNAVAILABLE → 必抛 ToolUnavailableError（不重试）
    service.register(PRIMARY, "图片流（依赖不可用模型）", [
        {"tool": UNAVAILABLE_ID, "input": {"file": "{{ input.file }}", "marker": "UNAVAILABLE"}},
    ], on_failure={"fallback_flow": SECONDARY})
    yield {"svc": service, "repo": pipeline_repo, "audit": run_event_repo, "tasks": task_repo,
           "pump": lambda: scheduler.run_once("w-fb"), "tmp": tmp_path}
    with db.pool.connection() as conn:
        run_ids = [r[0] for r in conn.execute(
            "SELECT id FROM pipeline_runs WHERE pipeline_id = ANY(%s)",
            ([PRIMARY, SECONDARY, NO_FALLBACK],)).fetchall()]
        if run_ids:
            conn.execute("DELETE FROM run_events WHERE run_id = ANY(%s)", (run_ids,))
            conn.execute("DELETE FROM tasks WHERE pipeline_run = ANY(%s)", (run_ids,))
            conn.execute("DELETE FROM pipeline_runs WHERE id = ANY(%s)", (run_ids,))


def _pump_until_done(stack, limit: int = 12) -> None:
    for _ in range(limit):
        stack["pump"]()


def test_unavailable_error_triggers_fallback_run(stack):
    src = stack["tmp"] / "扫描件.txt"
    src.write_text("UNAVAILABLE\nhello\nworld\n", encoding="utf-8")

    created = stack["svc"].run(PRIMARY, {"file": str(src)}, batch_id="b_fbtest")
    primary_id = created["run_id"]
    _pump_until_done(stack)

    primary = stack["repo"].get_run(primary_id)
    assert primary["status"] == "failed", primary
    assert primary["error"]["kind"] == "unavailable", primary["error"]
    assert primary["error"]["fallback_flow"] == SECONDARY
    assert "自动改用" in primary["error"]["message"]

    # 降级 run：同 batch_id、fallback_of 指向原 run、用的是降级流，且**跑通**
    # （它的模板引用 input.model —— 主流 input 里没有该键，靠 I1 的「缺键视为 null」）
    fallback = [r for r in stack["repo"].list_runs(batch_id="b_fbtest", limit=10)
                if r["fallback_of"] == primary_id]
    assert len(fallback) == 1, fallback
    fb = fallback[0]
    assert fb["pipeline_id"] == SECONDARY
    assert fb["batch_id"] == "b_fbtest"
    _pump_until_done(stack)
    assert stack["repo"].get_run(fb["id"])["status"] == "succeeded", stack["repo"].get_run(fb["id"])

    kinds = [e["kind"] for e in stack["audit"].list(primary_id, limit=50)]
    assert "run_fallback" in kinds
    assert "run_fallback" in [e["kind"] for e in stack["audit"].list(fb["id"], limit=50)]


def test_fallback_flow_guard_is_pure_logic(stack):
    """降级判定：只对「顶层 + 未降级过 + kind=unavailable」的失败 run 生效（不建 DB）。"""
    svc = stack["svc"]
    err = {"kind": "unavailable", "message": "模型未开通"}
    top = {"pipeline_id": PRIMARY, "parent_run_id": None, "fallback_of": None}
    assert svc._fallback_flow_for(top, "failed", err) == SECONDARY
    # 已降级过 → 不再降级（无链式）
    assert svc._fallback_flow_for({**top, "fallback_of": "p_x"}, "failed", err) is None
    # 子 run → 由父 run 承担降级
    assert svc._fallback_flow_for({**top, "parent_run_id": "p_p"}, "failed", err) is None
    # 非「能力不可用」错误 → 不降级
    assert svc._fallback_flow_for(top, "failed", {"kind": "user", "message": "入队失败"}) is None
    assert svc._fallback_flow_for(top, "failed", None) is None
    # 非失败终态 → 不降级
    assert svc._fallback_flow_for(top, "succeeded", err) is None


def _pump_until_status(stack, run_id: str, timeout_s: float = 20.0) -> str:
    """反复发牌直到 run 离开 running（子进程任务耗时不定，固定次数会 flaky）。"""
    import time
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        stack["pump"]()
        status = stack["repo"].get_run(run_id)["status"]
        if status != "running":
            return status
        time.sleep(0.2)
    return stack["repo"].get_run(run_id)["status"]


def test_unavailable_without_fallback_pauses_run(stack):
    """P2：能力不可用但**没有**可降级的等价流 → run 落 `paused`（而非红色失败）。

    这样用户换好密钥后点「继续」即可**重试原流**；若降级到 skip 流，文件会被永久标记为
    「不翻译」且再也无法重试（线上 PNG 的教训）。同时校验暂停的 run 能正常「继续」。
    """
    svc = stack["svc"]
    svc.register(NO_FALLBACK, "单图流（无等价降级流）", [
        {"tool": UNAVAILABLE_ID, "input": {"file": "{{ input.file }}", "marker": "UNAVAILABLE"}},
    ])
    src = stack["tmp"] / "扫描图.png"
    src.write_text("UNAVAILABLE\n", encoding="utf-8")
    created = svc.run(NO_FALLBACK, {"file": str(src)}, batch_id="b_pausetest")
    assert _pump_until_status(stack, created["run_id"]) == "paused"

    run = stack["repo"].get_run(created["run_id"])
    assert run["status"] == "paused", run
    assert run["error"]["paused_unavailable"] is True
    assert run["error"]["kind"] == "unavailable"
    assert "能力不可用" in run["error"]["message"]
    assert "继续" in run["error"]["hint"] and "版式翻译" in run["error"]["hint"]
    # 没有产生降级 run
    assert not [r for r in stack["repo"].list_runs(batch_id="b_pausetest", limit=10)
                if r.get("fallback_of")]

    # 「继续」可重试原流（再次撞不可用 → 仍暂停，不抛异常）
    svc.resume_run(created["run_id"])
    assert _pump_until_status(stack, created["run_id"]) == "paused"


def test_fallback_injects_reason_when_target_declares_it(stack):
    """降级目标若声明了 reason（如「暂不翻译」流），应写入降级原因——

    否则留档记录只显示工具默认文案（「本轮不处理」），用户看不出为何被跳过。
    """
    svc = stack["svc"]
    target = "test.skip.like"
    svc.register(target, "留档型降级目标", [
        {"tool": UNAVAILABLE_ID, "input": {"file": "{{ input.file }}", "marker": "NEVER"}},
    ], input_schema={"type": "object", "required": ["file"],
                     "properties": {"file": {"type": "string"}, "reason": {"type": ["string", "null"]}}})
    source = "test.image.like"
    svc.register(source, "图片流（不可用模型）", [
        {"tool": UNAVAILABLE_ID, "input": {"file": "{{ input.file }}", "marker": "UNAVAILABLE"}},
    ], on_failure={"fallback_flow": target})

    src = stack["tmp"] / "图.png"
    src.write_text("UNAVAILABLE\n", encoding="utf-8")
    created = svc.run(source, {"file": str(src)}, batch_id="b_reason")
    _pump_until_done(stack)
    fb = [r for r in stack["repo"].list_runs(batch_id="b_reason", limit=10)
          if r.get("fallback_of") == created["run_id"]]
    assert len(fb) == 1, fb
    reason = str(fb[0]["input"].get("reason") or "")
    assert "已自动降级" in reason and source in reason

    with stack["repo"]._db.pool.connection() as conn:
        ids = [r[0] for r in conn.execute(
            "SELECT id FROM pipeline_runs WHERE pipeline_id = ANY(%s)", ([target, source],)).fetchall()]
        if ids:
            conn.execute("DELETE FROM run_events WHERE run_id = ANY(%s)", (ids,))
            conn.execute("DELETE FROM tasks WHERE pipeline_run = ANY(%s)", (ids,))
            conn.execute("DELETE FROM pipeline_runs WHERE id = ANY(%s)", (ids,))
