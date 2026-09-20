"""Y1/Y2：跳步入进度分母 + 人话原因。"""

from __future__ import annotations

from services.pipeline_service import PipelineService


def _summary(skipped, titles=None, statuses=None, outputs=None):
    return PipelineService._assemble_summary(
        statuses or {}, outputs or {}, 3, skipped, titles or {})


def test_skipped_steps_count_into_steps_done() -> None:
    """when 跳过的步无 task 行——Y1 单独并入，2/3 不再误导。"""
    out = _summary([{"step_index": 2, "when": {"input.export_units": True}}],
                   statuses={0: "succeeded", 1: "succeeded"})
    assert out["steps_done"] == 3
    assert out["steps_total"] == 3


def test_skip_reason_human_readable() -> None:
    """Y2：when 条件翻成人话（input.X=True → 未开启「X」）。"""
    out = _summary([{"step_index": 2, "when": {"input.export_units": True}}],
                   titles={"export_units": "导出识别单元"})
    assert out["steps_skipped"] == [{"step_index": 2, "reason": "未开启「导出识别单元」"}]


def test_skip_reason_variants() -> None:
    r = PipelineService._skip_reason
    assert r({"input.model": "@exists"}, {"model": "模型"}) == "「模型」无值（该步需要它）"
    assert r({"input.use_cache": False}, {"use_cache": "缓存"}) == "「缓存」需关闭"
    assert r({"prev.view_spec": "@exists"}, {}) == "「prev.view_spec」无值（该步需要它）"
    assert r({"input.db": "a"}, {"db": "结果库"}) == "「结果库」需为 a"


def test_records_count_and_failed_pages_keys() -> None:
    """X4 键名修正 + Y4：records_count 进 summary（0 也透出，前端警示）。"""
    out = _summary([], outputs={1: {"failed_pages": 2, "records_count": 0}})
    assert out["failed_pages"] == 2
    assert out["records_count"] == 0


def test_no_skipped_no_noise() -> None:
    out = _summary(None, statuses={0: "succeeded"})
    assert "steps_skipped" not in out
    assert "records_count" not in out


def test_detail_endpoint_returns_summary(monkeypatch):
    """AI1b：详情端点补 summary（latest_note/steps_done/skipped_steps）——抽屉进度渲染位不再恒空。
    池隔离（全套跑不串扰）：自建 dev-PG 连接与真 service，不走 deps.get_db 的 lru_cache 单例——
    此前 monkeypatch get_config 后经单例开池，桩 URL 'x' 的后台线程会污染后续用例（e3 全链曾挂）。"""
    import json
    import secrets

    import deps
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from api import pipelines_router
    from store.db import Db
    from tests._dbutil import db_reachable
    from store.event_repo import EventRepo
    from store.pipeline_repo import PipelineRepo
    from store.run_event_repo import RunEventRepo
    from store.task_repo import TaskRepo
    from store.tool_repo import ToolRepo
    from services.dispatch_service import DispatchService
    from services.pipeline_service import PipelineService

    DB_URL = "postgresql://command_dev:root@192.168.8.41:5432/command_dev"
    if not db_reachable(DB_URL):
        import pytest

        pytest.skip("dev PG 不可达，跳过集成测试")
    db = Db(DB_URL)
    db.apply_migrations()
    svc = PipelineService(
        db=db, pipeline_repo=PipelineRepo(db), task_repo=TaskRepo(db),
        tool_repo=ToolRepo(db),
        dispatch_service=DispatchService(db=db, task_repo=TaskRepo(db),
                                         tool_repo=ToolRepo(db), event_repo=EventRepo(db)),
        run_event_repo=RunEventRepo(db))
    monkeypatch.setattr(deps, "get_pipeline_service", lambda: svc)
    monkeypatch.setattr(deps, "get_pipeline_repo", lambda: svc._pipeline_repo)
    monkeypatch.setattr(deps, "get_run_event_repo", lambda: RunEventRepo(db))
    app = FastAPI()
    app.include_router(pipelines_router.runs_router, prefix="/api")

    rid = "p_ai1_" + secrets.token_hex(6)
    with db.pool.connection() as conn:
        conn.execute(
            "INSERT INTO pipelines (id, name, steps) VALUES (%s, 'AI1', %s) ON CONFLICT DO NOTHING",
            ("flow.ai1.detail", json.dumps([{"tool": "t", "input": {}}])))
        conn.execute(
            "INSERT INTO pipeline_runs (id, pipeline_id, input, status) "
            "VALUES (%s, 'flow.ai1.detail', %s, 'running')",
            (rid, json.dumps({"file": "x.pdf"})))
    events = RunEventRepo(db)
    events.append(rid, None, "created", detail={"pipeline_id": "flow.ai1.detail"})
    events.append(rid, None, "progress", actor="tool",
                  detail={"type": "progress", "phase": "recognize", "message": "已识别 3/50 页"})
    try:
        with TestClient(app) as client:
            resp = client.get(f"/api/pipeline-runs/{rid}")
            assert resp.status_code == 200
            body = resp.json()
            assert "summary" in body
            assert body["summary"].get("latest_note") == "已识别 3/50 页"
    finally:
        with db.pool.connection() as conn:
            conn.execute("DELETE FROM run_events WHERE run_id = %s", (rid,))
            conn.execute("DELETE FROM pipeline_runs WHERE id = %s", (rid,))
        db.close()
