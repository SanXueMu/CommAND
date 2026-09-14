"""files 打包下载路由测试：zip 组装 / 命名清洗 / 同名去重 / 跳过原因 / 参数校验（零 DB）。"""

import zipfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import deps
from config import Config


class _StubService:
    """按 run_id 返回产物清单；记录 scope 以便断言。"""

    def __init__(self, mapping: dict | None = None, errors: dict | None = None):
        self.mapping = mapping or {}
        self.errors = errors or {}
        self.calls: list[tuple[str, str]] = []

    def collect_run_artifacts(self, run_id: str, scope: str = "final"):
        self.calls.append((run_id, scope))
        if run_id in self.errors:
            raise self.errors[run_id]
        return self.mapping.get(run_id, [])


@pytest.fixture
def pkg(tmp_path: Path, monkeypatch):
    from fastapi import FastAPI

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


def _artifact(tmp_path: Path, run_folder: str, name: str, payload: bytes, step: int = 5) -> dict:
    target = tmp_path / "outputs" / run_folder / name
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(payload)
    return {"step": step, "key": "path", "name": name, "path": str(target), "size": len(payload)}


def test_package_collects_artifacts_into_zip(pkg):
    c, tmp_path, service = pkg
    service.mapping = {
        "p_aaa": [_artifact(tmp_path, "h1", "报告_双语对照.docx", b"DOCX-AAA")],
        "p_bbb": [_artifact(tmp_path, "h2", "报告_原位译文.pdf", b"PDF-BBB"),
                  _artifact(tmp_path, "h2", "合同.docx", b"DOCX-BBB")],
    }
    resp = c.post("/api/files/package", json={"run_ids": ["p_aaa", "p_bbb"]})
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["count"] == 3 and body["runs"] == 2 and body["size"] > 0
    assert body["scope"] == "final", "默认只打包最终产物"
    assert service.calls == [("p_aaa", "final"), ("p_bbb", "final")]
    zip_path = Path(body["path"])
    assert zip_path.exists() and tmp_path in zip_path.parents
    with zipfile.ZipFile(zip_path) as zf:
        assert set(zf.namelist()) == {
            "p_aaa/报告_双语对照.docx", "p_bbb/报告_原位译文.pdf", "p_bbb/合同.docx"}
        assert zf.read("p_bbb/合同.docx") == b"DOCX-BBB"


def test_package_same_name_deduped_within_run(pkg):
    c, tmp_path, service = pkg
    service.mapping = {"p_aaa": [_artifact(tmp_path, "h1", "译文.docx", b"ONE"),
                                 _artifact(tmp_path, "h1", "译文.docx", b"TWO")]}
    body = c.post("/api/files/package", json={"run_ids": ["p_aaa"]}).json()
    assert body["count"] == 2
    with zipfile.ZipFile(Path(body["path"])) as zf:
        assert sorted(zf.namelist()) == ["p_aaa/译文-1.docx", "p_aaa/译文.docx"]


def test_package_scope_all_passed_through(pkg):
    c, tmp_path, service = pkg
    service.mapping = {"p_aaa": [_artifact(tmp_path, "h1", "中间产物.pdf", b"X", step=2),
                                 _artifact(tmp_path, "h1", "最终.docx", b"Y", step=5)]}
    body = c.post("/api/files/package", json={"run_ids": ["p_aaa"], "scope": "all"}).json()
    assert service.calls == [("p_aaa", "all")] and body["count"] == 2


def test_package_reports_skipped_and_rejects_empty(pkg):
    c, tmp_path, service = pkg
    # 全部无可打包产物 → 422 且不留空 zip
    service.mapping = {"p_aaa": []}
    resp = c.post("/api/files/package", json={"run_ids": ["p_aaa", "p_missing"]})
    assert resp.status_code == 422
    assert "没有可打包的产物" in resp.text
    assert list((tmp_path / "exports").glob("*.zip")) == [], "失败的包不得留档"

    # 部分失败：别的 run 正常打包，失败原因随包回报
    service.errors = {"p_boom": RuntimeError("boom")}
    service.mapping = {"p_ok": [_artifact(tmp_path, "h3", "好.docx", b"OK")]}
    body = c.post("/api/files/package", json={"run_ids": ["p_ok", "p_boom", "p_none"]}).json()
    assert body["count"] == 1
    reasons = {s["run_id"]: s["reason"] for s in body["skipped"]}
    assert "boom" in reasons["p_boom"] and reasons["p_none"] == "没有可打包的产物"


def test_package_name_is_sanitized_and_inside_exports(pkg):
    c, tmp_path, service = pkg
    service.mapping = {"p_aaa": [_artifact(tmp_path, "h1", "a.docx", b"A")]}
    body = c.post("/api/files/package", json={"run_ids": ["p_aaa"], "name": "../../etc/pa ss:wd"}).json()
    name = body["name"]
    assert "/" not in name and ".." not in name and name.endswith(".zip")
    assert Path(body["path"]).parent == tmp_path / "exports"


def test_package_param_guards(pkg):
    c, _, _ = pkg
    assert c.post("/api/files/package", json={"run_ids": []}).status_code == 422
    assert c.post("/api/files/package", json={"run_ids": "p_aaa"}).status_code == 422
    assert c.post("/api/files/package", json={"run_ids": ["p_aaa"], "scope": "weird"}).status_code == 422
    too_many = c.post("/api/files/package", json={"run_ids": [f"p_{i}" for i in range(201)]})
    assert too_many.status_code == 413
