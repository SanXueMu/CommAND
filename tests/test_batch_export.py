"""批次导出（清单驱动）测试：目录结构还原 / 根目录加后缀 / 源文件回退 / 未跑成功不混入（零 DB）。"""

import json
import zipfile
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import deps
from config import Config


class _StubService:
    """提供 best_runs_of_batch（**每文件最优 run，由服务端 SQL 决定**）与 collect_run_artifacts。

    注意：挑 run 的优先级（成功 > 暂停 > 其它，同级最新）现在在 `PipelineRepo.best_runs_by_batch`
    的 DISTINCT ON 里；这里只负责把「服务端会给的那条」交给路由（真 SQL 的测试见
    tests/test_best_runs_by_batch.py）。
    """

    def __init__(self):
        self.runs: dict[str, list] = {}
        self.artifacts: dict[str, list] = {}

    def best_runs_of_batch(self, batch_id: str) -> list:
        return list(self.runs.get(batch_id, []))

    def collect_run_artifacts(self, run_id: str, scope: str = "final") -> list:
        return list(self.artifacts.get(run_id, []))


@pytest.fixture
def batch(tmp_path: Path, monkeypatch):
    from api import files_router

    stub_cfg = Config(
        host="127.0.0.1", port=0, database_url="postgresql://x/x", worker_concurrency=1,
        heartbeat_interval_s=15, heartbeat_timeout_s=90, tools_dir=tmp_path, data_dir=tmp_path,
    )
    service = _StubService()
    monkeypatch.setattr(deps, "get_config", lambda: stub_cfg)
    monkeypatch.setattr(deps, "get_pipeline_service", lambda: service)
    app = FastAPI()
    app.include_router(files_router.router, prefix="/api")
    with TestClient(app) as c:
        yield c, tmp_path, service


def _manifest(tmp_path: Path, batch_id: str, entries: list[dict], root: str = "投标资料") -> None:
    d = tmp_path / "batches"
    d.mkdir(parents=True, exist_ok=True)
    (d / f"{batch_id}.json").write_text(json.dumps(
        {"batch_id": batch_id, "root": root, "dir": str(tmp_path / "uploads" / root),
         "created_at": "2026-09-14", "files": entries}, ensure_ascii=False), encoding="utf-8")


def _entry(tmp_path: Path, root: str, rel: str, payload: bytes = b"SRC", **extra) -> dict:
    """rel 是**相对批次根目录**的路径（上传端点会剥掉根目录前缀），path 是落盘绝对路径。"""
    p = tmp_path / "uploads" / root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(payload)
    return {"path": str(p), "name": p.name, "rel": rel, "size": len(payload), **extra}


def _artifact(tmp_path: Path, handle: str, name: str, payload: bytes) -> dict:
    target = tmp_path / "outputs" / handle / name
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(payload)
    return {"step": 5, "key": "path", "name": name, "path": str(target), "size": len(payload)}


def test_package_batch_restores_tree_and_suffixes_root(batch):
    """清单驱动：结构照原样，只有批次根目录加 _中文；无产物的文件回退源文件。"""
    c, tmp_path, service = batch
    _manifest(tmp_path, "b1", [
        _entry(tmp_path, "投标资料", "A/合同.pdf", b"PDF-A"),
        _entry(tmp_path, "投标资料", "B/说明.docx", b"PK-B"),
        _entry(tmp_path, "投标资料", "C/演讲.pptx", b"PK-PPT", skip=True, skip_reason="PPT 暂不支持"),
    ])
    service.runs["b1"] = [
        {"id": "r1", "status": "succeeded", "input": {"file": str(tmp_path / "uploads/投标资料/A/合同.pdf")}},
        {"id": "r2", "status": "succeeded", "input": {"file": str(tmp_path / "uploads/投标资料/B/说明.docx")}},
        {"id": "r3", "status": "paused", "input": {"file": str(tmp_path / "uploads/投标资料/C/演讲.pptx")}},
    ]
    service.artifacts = {"r1": [_artifact(tmp_path, "h1", "合同_中文.pdf", b"OUT-A")],
                         "r2": [_artifact(tmp_path, "h2", "说明_中文.docx", b"OUT-B")]}

    resp = c.post("/api/files/package_batch", json={"batch_id": "b1", "suffix": "_中文"})
    assert resp.status_code == 201
    body = resp.json()
    with zipfile.ZipFile(body["path"]) as z:
        names = sorted(z.namelist())
        assert names == ["投标资料_中文/A/合同_中文.pdf", "投标资料_中文/B/说明_中文.docx",
                         "投标资料_中文/C/演讲.pptx"]
        assert z.read("投标资料_中文/A/合同_中文.pdf") == b"OUT-A"
        assert z.read("投标资料_中文/C/演讲.pptx") == b"PK-PPT"
    assert len(body["translated"]) == 2
    assert [p["rel"] for p in body["passthrough"]] == ["C/演讲.pptx"]
    assert body["missing"] == []


def test_package_batch_failed_without_artifacts_passes_source_through(batch):
    """失败但**无任何产物**（入队即失败 / 降级前的原 run）→ 放回源文件，交付目录结构保持完整。"""
    c, tmp_path, service = batch
    _manifest(tmp_path, "b2", [_entry(tmp_path, "批次", "坏文件.pdf", b"PDF")])
    service.runs["b2"] = [{"id": "r1", "status": "failed",
                           "input": {"file": str(tmp_path / "uploads/批次/坏文件.pdf")}}]
    resp = c.post("/api/files/package_batch", json={"batch_id": "b2"})
    assert resp.status_code == 201
    body = resp.json()
    assert body["translated"] == [] and body["missing"] == []
    assert [p["rel"] for p in body["passthrough"]] == ["坏文件.pdf"]
    assert "任务失败" in body["passthrough"][0]["reason"]
    with zipfile.ZipFile(body["path"]) as z:
        assert z.namelist() == ["投标资料_中文/坏文件.pdf"]
        assert z.read("投标资料_中文/坏文件.pdf") == b"PDF"


def test_package_batch_failed_with_partial_artifacts_stays_missing(batch):
    """失败但**已有部分产物** → 不进交付目录（避免把半成品混进去），只报缺失。"""
    c, tmp_path, service = batch
    _manifest(tmp_path, "b5", [_entry(tmp_path, "批次", "半成品.pdf", b"PDF")])
    path = str(tmp_path / "uploads/批次/半成品.pdf")
    service.runs["b5"] = [{"id": "r1", "status": "failed", "input": {"file": path}}]
    service.artifacts = {"r1": [_artifact(tmp_path, "hp", "半成品_中间.pdf", b"HALF")]}
    resp = c.post("/api/files/package_batch", json={"batch_id": "b5"})
    body = resp.json()
    assert body["translated"] == [] and body["passthrough"] == []
    assert [m["rel"] for m in body["missing"]] == ["半成品.pdf"]
    with zipfile.ZipFile(body["path"]) as z:
        assert z.namelist() == []


def test_package_batch_unknown_batch_404(batch):
    c, _, _ = batch
    assert c.post("/api/files/package_batch", json={"batch_id": "nope"}).status_code == 404
    assert c.post("/api/files/package_batch", json={"batch_id": "nope"}).status_code != 500


def test_batch_upload_marks_skip_and_writes_manifest(batch):
    """后端过滤：skip 后缀照常落盘（导出要用），但标记 skip 并在响应/清单里回报。"""
    c, tmp_path, _ = batch
    resp = c.post("/api/files/batch",
                  files=[("files", ("批/A.pdf", b"%PDF-1", "application/pdf")),
                         ("files", ("批/B.pptx", b"PK-PPT", "application/octet-stream"))],
                  params={"skip": ".ppt,.pptx"})
    assert resp.status_code == 201
    body = resp.json()
    assert body["batch_id"] and [x["name"] for x in body["skipped"]] == ["B.pptx"]
    flags = {f["rel"]: f.get("skip") for f in body["files"]}
    assert flags == {"A.pdf": None, "B.pptx": True}
    manifest = json.loads((tmp_path / "batches" / f"{body['batch_id']}.json").read_text(encoding="utf-8"))
    assert manifest["root"] == "批"
    assert [f["rel"] for f in manifest["files"]] == ["A.pdf", "B.pptx"]
    assert manifest["files"][1]["skip"] is True


def test_package_batch_prefers_successful_run_over_older_failed(batch):
    """同一文件多条 run（失败降级 / 再运行）：导出必须取**成功**的那条产物，
    不能被更早的 failed run 盖成 missing（list_runs 是 created_at DESC，旧实现会取最旧）。"""
    c, tmp_path, service = batch
    _manifest(tmp_path, "b3", [_entry(tmp_path, "批次", "合同.pdf", b"PDF")])
    path = str(tmp_path / "uploads/批次/合同.pdf")
    # 最新在前：成功 run 在前，更早的 failed run 在后（模拟降级场景）
    service.runs["b3"] = [
        {"id": "r_fb", "status": "succeeded", "created_at": "2026-09-14T10:05:00",
         "input": {"file": path}, "fallback_of": "r_old"},
        {"id": "r_old", "status": "failed", "created_at": "2026-09-14T10:00:00",
         "input": {"file": path}},
    ]
    service.artifacts = {"r_fb": [_artifact(tmp_path, "h9", "合同_中文.pdf", b"OUT-FB")]}

    resp = c.post("/api/files/package_batch", json={"batch_id": "b3"})
    assert resp.status_code == 201
    body = resp.json()
    assert [t["rel"] for t in body["translated"]] == ["合同.pdf"]
    assert body["missing"] == []
    with zipfile.ZipFile(body["path"]) as z:
        assert z.read("投标资料_中文/合同_中文.pdf") == b"OUT-FB"


def test_package_batch_prefers_newest_when_same_status(batch):
    """同状态（都成功）取最新那条（再运行场景：以最后一次结果为准）。"""
    c, tmp_path, service = batch
    _manifest(tmp_path, "b4", [_entry(tmp_path, "批次", "x.pdf", b"PDF")])
    path = str(tmp_path / "uploads/批次/x.pdf")
    service.runs["b4"] = [
        {"id": "r_new", "status": "succeeded", "created_at": "2026-09-14T11:00:00",
         "input": {"file": path}},
        {"id": "r_old", "status": "succeeded", "created_at": "2026-09-14T09:00:00",
         "input": {"file": path}},
    ]
    service.artifacts = {"r_new": [_artifact(tmp_path, "hn", "x_中文.pdf", b"NEW")],
                         "r_old": [_artifact(tmp_path, "ho", "x_中文.pdf", b"OLD")]}
    resp = c.post("/api/files/package_batch", json={"batch_id": "b4"})
    with zipfile.ZipFile(resp.json()["path"]) as z:
        assert z.read("投标资料_中文/x_中文.pdf") == b"NEW"
