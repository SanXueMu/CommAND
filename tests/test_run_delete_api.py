"""pipeline-runs 删除路由：purge_files 参数转发与返回体（零 DB，桩服务）。"""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import deps
from api import pipelines_router


class _StubService:
    def __init__(self) -> None:
        self.calls: list[tuple[str, bool]] = []

    def delete_run(self, run_id: str, purge_files: bool = True) -> dict:
        self.calls.append((run_id, purge_files))
        return {"id": run_id, "status": "deleted", "aborted": False, "pending_tasks": [],
                "purge_files": purge_files, "files_removed": 2, "bytes_freed": 30,
                "dirs_removed": 1}


@pytest.fixture
def client(monkeypatch):
    stub = _StubService()
    monkeypatch.setattr(deps, "get_pipeline_service", lambda: stub)
    app = FastAPI()
    app.include_router(pipelines_router.runs_router, prefix="/api")
    with TestClient(app) as c:
        yield c, stub


def test_delete_run_default_purges_files(client):
    c, stub = client
    resp = c.delete("/api/pipeline-runs/p_x")
    assert resp.status_code == 200
    assert resp.json()["files_removed"] == 2
    assert stub.calls == [("p_x", True)]


def test_delete_run_keep_files(client):
    c, stub = client
    resp = c.delete("/api/pipeline-runs/p_y?purge_files=false")
    assert resp.status_code == 200
    assert resp.json()["purge_files"] is False
    assert stub.calls == [("p_y", False)]
