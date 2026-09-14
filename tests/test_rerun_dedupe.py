"""I2：批量重跑按文件去重（同一文件只重跑最新一条失败 run）。

线上现象：每次失败的重跑都会新产生一条 failed run，若按钮重跑「视图内全部失败项」，
第二次点击会把历史失败+新失败一起重跑 → 数量指数增长（用户反馈「越重跑越多」）。
"""

from __future__ import annotations

import pytest

from services.pipeline_service import PipelineService


class _Repo:
    """只实现重跑去重用到的两个方法。"""

    def __init__(self, runs: dict[str, dict]):
        self._runs = runs

    def get_run(self, run_id: str):
        return self._runs.get(run_id)

    def list_runs(self, pipeline_id=None, limit=50, offset=0, batch_id=None):
        rows = [r for r in self._runs.values() if r.get("batch_id") == batch_id]
        rows.sort(key=lambda r: str(r.get("created_at") or ""), reverse=True)
        return rows[:limit]


@pytest.fixture
def service():
    svc = object.__new__(PipelineService)  # 只测纯逻辑，不建 DB
    svc._pipeline_repo = _Repo({
        "r1": {"id": "r1", "status": "failed", "created_at": "2026-09-14T10:00:00",
               "input": {"file": "/u/A.pdf"}, "batch_id": "b1", "pipeline_id": "p"},
        "r2": {"id": "r2", "status": "failed", "created_at": "2026-09-14T11:00:00",
               "input": {"file": "/u/A.pdf"}, "batch_id": "b1", "pipeline_id": "p"},
        "r3": {"id": "r3", "status": "failed", "created_at": "2026-09-14T09:00:00",
               "input": {"file": "/u/B.pdf"}, "batch_id": "b1", "pipeline_id": "p"},
        "r4": {"id": "r4", "status": "succeeded", "created_at": "2026-09-14T12:00:00",
               "input": {"file": "/u/C.pdf"}, "batch_id": "b1", "pipeline_id": "p"},
        "r5": {"id": "r5", "status": "paused", "created_at": "2026-09-14T13:00:00",
               "input": {"file": "/u/D.pdf"}, "batch_id": "b1", "pipeline_id": "p"},
    })
    return svc


def test_failed_runs_of_batch_dedupes_by_file(service):
    """同文件 3 条里取最新那条失败；succeeded/paused 不入选。"""
    assert service.failed_runs_of_batch("b1") == ["r2", "r3"]


def test_rerun_runs_skips_superseded_same_file(service):
    """显式给多条同文件失败 run：只重跑最新一条，其余记 skipped。"""
    calls: list[str] = []
    service.rerun_run = lambda rid, **_: (calls.append(rid), {"run_id": f"new_{rid}"})[1]

    out = service.rerun_runs(["r1", "r2", "r3"])

    assert calls == ["r2", "r3"], calls
    assert [r["from"] for r in out["rerun"]] == ["r2", "r3"]
    assert out["count"] == 2
    assert any(s["run_id"] == "r1" and "更新的失败任务" in s["reason"] for s in out["skipped"])


def test_rerun_runs_reports_unknown_and_wrong_status(service):
    service.rerun_run = lambda rid, **_: {"run_id": "n"}
    out = service.rerun_runs(["r4", "nope"])
    assert out["count"] == 0
    reasons = {s["run_id"]: s["reason"] for s in out["skipped"]}
    assert "状态不可重跑" in reasons["r4"]
    assert reasons["nope"] == "任务不存在"
