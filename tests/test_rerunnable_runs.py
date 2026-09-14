"""K3：可重跑清单（全批次口径，按「从未成功过」判定）。

线上现象：任务清单只加载最新 100 条 run，界面「重跑失败项」计数被历史失败的尝试虚高
（用户实测 42，其中 100% 都已有成功 run；真实待处理 10 个）。
"""

from __future__ import annotations

import pytest

from services.pipeline_service import PipelineService


class _Repo:
    def __init__(self, runs: list[dict]):
        self._runs = runs

    def list_runs(self, pipeline_id=None, limit=50, offset=0, batch_id=None):
        rows = [r for r in self._runs if batch_id is None or r.get("batch_id") == batch_id]
        rows.sort(key=lambda r: str(r.get("created_at") or ""), reverse=True)
        return rows[:limit]


def _svc(runs: list[dict]) -> PipelineService:
    svc = object.__new__(PipelineService)
    svc._pipeline_repo = _Repo(runs)
    return svc


def _run(rid, file, status, ts, flow="flow.translate.xlsx", batch="b1", err=None):
    return {"id": rid, "status": status, "created_at": ts, "batch_id": batch,
            "pipeline_id": flow, "input": {"file": file}, "error": err}


def test_only_files_never_succeeded_are_rerunnable():
    """已成功过的文件不再列入（即便后来某次重跑失败）——这正是「42 虚高」的成因。"""
    svc = _svc([
        _run("r1", "/u/A.xlsx", "failed", "2026-09-14T12:00:00"),   # 最新失败，但曾成功
        _run("r2", "/u/A.xlsx", "succeeded", "2026-09-14T11:00:00"),
        _run("r3", "/u/B.xlsx", "failed", "2026-09-14T12:10:00"),   # 从未成功 → 应列入
    ])
    out = svc.rerunnable_runs(batch_id="b1")
    assert out["count"] == 1
    assert out["run_ids"] == ["r3"]
    assert out["files"][0]["name"] == "B.xlsx"


def test_latest_attempt_decides_and_paused_excluded():
    """同一文件从未成功：最新一次失败 → 列入；最新一次 paused → 不列入（走「继续」）。"""
    svc = _svc([
        _run("r1", "/u/C.pdf", "paused", "2026-09-14T13:00:00"),
        _run("r2", "/u/C.pdf", "failed", "2026-09-14T12:00:00"),
        _run("r3", "/u/D.pdf", "failed_review", "2026-09-14T13:00:00"),
    ])
    out = svc.rerunnable_runs(batch_id="b1")
    assert out["run_ids"] == ["r3"]
    assert out["files"][0]["status"] == "failed_review"


def test_flow_filter_and_batch_scope():
    svc = _svc([
        _run("r1", "/u/A.xlsx", "failed", "2026-09-14T12:00:00", flow="flow.translate.xlsx"),
        _run("r2", "/u/B.pdf", "failed", "2026-09-14T12:00:00", flow="flow.translate.pdf.image"),
        _run("r3", "/u/C.xlsx", "failed", "2026-09-14T12:00:00", batch="b2"),
    ])
    assert svc.rerunnable_runs(batch_id="b1", flow_ids=["flow.translate.xlsx"])["run_ids"] == ["r1"]
    assert svc.rerunnable_runs(batch_id="b1")["count"] == 2      # b2 的不算
    assert svc.rerunnable_runs()["count"] == 3                   # 不传批次 = 全部


def test_error_message_is_reported():
    svc = _svc([_run("r1", "/u/A.pdf", "failed", "2026-09-14T12:00:00",
                     err={"kind": "unavailable", "message": "模型未开通"})])
    assert svc.rerunnable_runs(batch_id="b1")["files"][0]["error"] == "模型未开通"


def test_done_files_marks_succeeded_even_when_latest_is_paused():
    """done_files = 已有成功译文的文件（**与最新状态无关**）。

    线上 PNG：降级到 skip 后最新一条是 paused，若前端用「待重跑清单」反推就会误判成
    「已有成功译文」→ 失败的原流「重跑」被置灰，用户无法重试（2026-09-14）。
    """
    svc = _svc([
        _run("r1", "/u/A.xlsx", "succeeded", "2026-09-14T12:00:00"),
        _run("r2", "/u/B.png", "paused", "2026-09-14T13:00:00"),   # 从未成功，最新暂停
        _run("r3", "/u/B.png", "failed", "2026-09-14T12:00:00"),
        _run("r4", "/u/C.pdf", "failed", "2026-09-14T13:00:00"),   # 从未成功，待重跑
    ])
    out = svc.rerunnable_runs(batch_id="b1")
    assert out["done_files"] == ["/u/A.xlsx"]
    assert "/u/B.png" not in out["done_files"]      # 从未成功 → 不该被当成已完成
    assert out["run_ids"] == ["r4"]                 # 最新 paused 的 B 不进待重跑清单（走「继续」）
