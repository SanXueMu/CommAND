"""批次失败项一键重跑（零 DB）：/pipeline-runs/rerun-batch 的取数与转发。"""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

import deps


class _StubService:
    def __init__(self):
        self.batch_failed = ["r1", "r2"]
        self.calls: list[list[str]] = []

    def failed_runs_of_batch(self, batch_id: str, limit: int = 500) -> list[str]:
        assert batch_id == "b1"
        return self.batch_failed[:limit]

    def rerun_runs(self, run_ids: list[str]) -> dict:
        self.calls.append(list(run_ids))
        return {"count": len(run_ids),
                "rerun": [{"from": r, "to": f"new_{r}"} for r in run_ids],
                "skipped": []}


import pytest


@pytest.fixture
def client(monkeypatch):
    from api import pipelines_router

    service = _StubService()
    monkeypatch.setattr(deps, "get_pipeline_service", lambda: service)
    app = FastAPI()
    app.include_router(pipelines_router.runs_router, prefix="/api")  # router 自带 /pipeline-runs
    with TestClient(app) as c:
        yield c, service


def test_rerun_batch_by_batch_id(client):
    c, service = client
    resp = c.post("/api/pipeline-runs/rerun-batch", json={"batch_id": "b1"})
    assert resp.status_code == 202
    body = resp.json()
    assert body["count"] == 2
    assert [r["from"] for r in body["rerun"]] == ["r1", "r2"]
    assert service.calls == [["r1", "r2"]]


def test_rerun_batch_by_explicit_run_ids(client):
    c, service = client
    resp = c.post("/api/pipeline-runs/rerun-batch", json={"run_ids": ["x1"]})
    assert resp.status_code == 202
    assert service.calls == [["x1"]]


def test_rerun_batch_empty_is_noop(client):
    c, service = client
    resp = c.post("/api/pipeline-runs/rerun-batch", json={})
    assert resp.status_code == 202
    assert resp.json() == {"count": 0, "rerun": [], "skipped": []}
    assert service.calls == []
