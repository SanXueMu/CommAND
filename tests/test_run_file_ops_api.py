"""N3：替换任务原件 / 就地修正任务参数（零 DB，stub 掉 repo 与事件表）。"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import deps
from config import Config
from services import batch_manifest


class _Repo:
    def __init__(self, runs: dict[str, dict]):
        self.runs = runs
        self.updated: list[tuple[str, dict]] = []

    def get_run(self, run_id: str):
        return self.runs.get(run_id)

    def update_run_input(self, run_id: str, input: dict) -> bool:
        self.updated.append((run_id, input))
        if run_id in self.runs:
            self.runs[run_id]["input"] = input
            return True
        return False


class _Events:
    def __init__(self):
        self.appended: list[tuple] = []

    def append(self, run_id, handle, kind, actor="console", detail=None):
        self.appended.append((run_id, kind, detail))


@pytest.fixture
def env(tmp_path: Path, monkeypatch):
    from api import pipelines_router

    old = tmp_path / "uploads" / "批" / "合同.doc"
    old.parent.mkdir(parents=True, exist_ok=True)
    old.write_bytes(b"OLD-DOC")
    repo = _Repo({"p1": {"id": "p1", "status": "paused", "batch_id": "b1",
                         "input": {"file": str(old), "key_name": "k1"}},
                  "p2": {"id": "p2", "status": "running", "batch_id": "b1",
                         "input": {"file": str(old)}}})
    events = _Events()
    cfg = Config(host="127.0.0.1", port=0, database_url="postgresql://x/x",
                 worker_concurrency=1, heartbeat_interval_s=15, heartbeat_timeout_s=90,
                 tools_dir=tmp_path, data_dir=tmp_path)
    monkeypatch.setattr(deps, "get_config", lambda: cfg)
    monkeypatch.setattr(deps, "get_pipeline_repo", lambda: repo)
    monkeypatch.setattr(deps, "get_run_event_repo", lambda: events)
    batch_manifest.write(tmp_path, "b1", "批", old.parent,
                         [{"path": str(old), "name": old.name, "rel": old.name,
                           "size": old.stat().st_size}])
    app = FastAPI()
    app.include_router(pipelines_router.runs_router, prefix="/api")
    with TestClient(app) as c:
        yield c, tmp_path, repo, events, old


def test_replace_file_updates_disk_run_input_and_manifest(env):
    c, tmp_path, repo, events, old = env
    resp = c.post("/api/pipeline-runs/p1/replace-file",
                  files={"file": ("合同.docx", b"NEW-DOCX", "application/octet-stream")})
    assert resp.status_code == 201
    body = resp.json()
    new = Path(body["file"])
    assert new.name == "合同.docx" and new.parent == old.parent   # 落在同目录
    assert new.read_bytes() == b"NEW-DOCX"
    assert repo.runs["p1"]["input"]["file"] == str(new)            # run 的 input 已更新
    assert repo.runs["p1"]["input"]["key_name"] == "k1"            # 其它参数保留
    assert body["manifest_updated"] is True
    manifest = batch_manifest.load(tmp_path, "b1")
    entry = manifest["files"][0]
    assert entry["name"] == "合同.docx" and entry["path"] == str(new) and entry["rel"] == "合同.docx"
    assert ("p1", "file_replaced") == (events.appended[0][0], events.appended[0][1])


def test_replace_file_rejects_running_and_empty(env):
    c, _, _, _, _ = env
    assert c.post("/api/pipeline-runs/p2/replace-file",
                  files={"file": ("x.docx", b"X", "application/octet-stream")}).status_code == 409
    assert c.post("/api/pipeline-runs/nope/replace-file",
                  files={"file": ("x.docx", b"X", "application/octet-stream")}).status_code == 404
    assert c.post("/api/pipeline-runs/p1/replace-file",
                  files={"file": ("empty.docx", b"", "application/octet-stream")}).status_code == 422


def test_patch_input_merges_and_rejects_file(env):
    c, _, repo, events, _ = env
    resp = c.patch("/api/pipeline-runs/p1/input",
                   json={"input": {"key_name": "真实密钥", "model": "qwen-mt-flash"}})
    assert resp.status_code == 200
    assert repo.runs["p1"]["input"]["key_name"] == "真实密钥"
    assert repo.runs["p1"]["input"]["model"] == "qwen-mt-flash"
    assert events.appended[-1][1] == "input_updated"

    bad = c.patch("/api/pipeline-runs/p1/input", json={"input": {"file": "/tmp/x.docx"}})
    assert bad.status_code == 422 and "替换原件" in bad.json()["detail"]
    assert c.patch("/api/pipeline-runs/p2/input", json={"input": {"model": "m"}}).status_code == 409
