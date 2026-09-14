"""批量上传三端点测试：/files/list、/files/batch、/files/archive（纯文件系统，零外部依赖）。"""

import io
import zipfile
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import deps
from config import Config


@pytest.fixture
def client(tmp_path: Path, monkeypatch):
    from api import files_router

    stub = Config(
        host="127.0.0.1", port=0, database_url="postgresql://x/x", worker_concurrency=1,
        heartbeat_interval_s=15, heartbeat_timeout_s=90,
        tools_dir=tmp_path, data_dir=tmp_path,
    )
    monkeypatch.setattr(deps, "get_config", lambda: stub)
    app = FastAPI()
    app.include_router(files_router.router, prefix="/api")
    with TestClient(app) as c:
        yield c, tmp_path


def _zip(payload: dict[str, bytes], extra: list[zipfile.ZipInfo] | None = None) -> io.BytesIO:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for name, data in payload.items():
            zf.writestr(name, data)
        for info in extra or []:
            zf.writestr(info, b"x")
    buf.seek(0)
    return buf


def test_list_filters_and_lists(client):
    c, tmp_path = client
    (tmp_path / "批量" / "子目录").mkdir(parents=True)
    (tmp_path / "批量" / "a.pdf").write_bytes(b"%PDF-1")
    (tmp_path / "批量" / "子目录" / "b.docx").write_bytes(b"PK")
    (tmp_path / "批量" / "note.txt").write_text("x")

    body = c.get("/api/files/list", params={"path": str(tmp_path / "批量")}).json()
    assert body["count"] == 3 and body["truncated"] is False
    assert sorted(f["rel"] for f in body["files"]) == ["a.pdf", "note.txt", str(Path("子目录/b.docx"))]
    assert all(Path(f["path"]).exists() for f in body["files"])
    assert body["size"] == sum(f["size"] for f in body["files"])

    only_pdf = c.get("/api/files/list", params={"path": str(tmp_path / "批量"), "extensions": ".pdf"}).json()
    assert [f["name"] for f in only_pdf["files"]] == ["a.pdf"]

    top = c.get("/api/files/list", params={"path": str(tmp_path / "批量"), "recursive": False}).json()
    assert sorted(f["name"] for f in top["files"]) == ["a.pdf", "note.txt"]

    capped = c.get("/api/files/list", params={"path": str(tmp_path / "批量"), "limit": 1}).json()
    assert capped["count"] == 1 and capped["truncated"] is True


def test_list_blocks_traversal_and_missing(client):
    c, tmp_path = client
    assert c.get("/api/files/list", params={"path": str(tmp_path.parent)}).status_code == 403
    assert c.get("/api/files/list", params={"path": str(tmp_path / "没有这个目录")}).status_code == 404


def test_batch_upload_keeps_relative_paths(client):
    c, tmp_path = client
    resp = c.post("/api/files/batch", files=[
        ("files", ("合同样例/a.pdf", b"%PDF-1", "application/pdf")),
        ("files", ("合同样例/子目录/b.docx", b"PK", "application/octet-stream")),
        ("files", ("合同样例/note.txt", b"hello", "text/plain")),
    ])
    assert resp.status_code == 201
    body = resp.json()
    assert body["count"] == 3 and body["size"] == len(b"%PDF-1") + len(b"PK") + len(b"hello")
    base = Path(body["path"])
    assert tmp_path in base.parents and base.is_dir()
    assert base.name.endswith("_合同样例"), "批次目录以根目录名命名"
    assert sorted(f["rel"] for f in body["files"]) == ["a.pdf", "note.txt", "子目录/b.docx"]
    assert all(Path(f["path"]).is_file() for f in body["files"])
    assert (base / "子目录" / "b.docx").read_bytes() == b"PK"


def test_batch_writes_manifest_and_marks_skipped(client):
    """上传即固化批次清单（导出按它还原目录结构）；skip 类型打标但不丢文件。"""
    import json

    c, tmp_path = client
    resp = c.post("/api/files/batch?skip=.ppt,.pptx", files=[
        ("files", ("投标资料/A/合同.pdf", b"%PDF-1", "application/pdf")),
        ("files", ("投标资料/C/演讲.pptx", b"PK", "application/octet-stream")),
    ])
    assert resp.status_code == 201
    body = resp.json()
    batch_id = body["batch_id"]
    assert batch_id.startswith("b_")
    manifest = tmp_path / "batches" / f"{batch_id}.json"
    assert manifest.is_file(), "批次清单必须落盘（导出结构的地基）"
    data = json.loads(manifest.read_text(encoding="utf-8"))
    assert data["root"] == "投标资料" and len(data["files"]) == 2
    by_rel = {e["rel"]: e for e in data["files"]}
    assert set(by_rel) == {"A/合同.pdf", "C/演讲.pptx"}
    assert not by_rel["A/合同.pdf"].get("skip")
    assert by_rel["C/演讲.pptx"]["skip"] is True and by_rel["C/演讲.pptx"]["skip_reason"]
    assert body["skipped"] == ["C/演讲.pptx"]
    # 文件本身照样落盘（导出要放原文件）
    assert Path(by_rel["C/演讲.pptx"]["path"]).is_file()


def test_batch_rejects_bad_input_and_rolls_back(client):
    c, tmp_path = client
    resp = c.post("/api/files/batch",
                  files=[("files", ("ok.pdf", b"x", "application/pdf"))],
                  params={"extensions": ".docx"})
    assert resp.status_code == 422 and "不支持的类型" in resp.json()["detail"]
    batches = list((tmp_path / "uploads").glob("*/*")) if (tmp_path / "uploads").exists() else []
    assert batches == [], "越界即整批回滚，不留半批脏数据"

    evil = c.post("/api/files/batch", files=[("files", ("../逃逸.pdf", b"x", "application/pdf"))])
    assert evil.status_code == 422

    empty = c.post("/api/files/batch", files=[("files", ("空.pdf", b"", "application/pdf"))])
    assert empty.status_code == 422

    many = c.post("/api/files/batch", files=[
        ("files", (f"f{i}.pdf", b"x", "application/pdf")) for i in range(201)])
    assert many.status_code == 413


def test_archive_extracts_and_skips_bad_entries(client):
    c, tmp_path = client
    symlink = zipfile.ZipInfo("链接.txt")
    symlink.external_attr = (0o120777 << 16) | 0o777
    buf = _zip({"合同/主文件.pdf": b"%PDF-1", "合同/附件/清单.xlsx": b"PK", "合同/说明.txt": b"hi"},
               extra=[zipfile.ZipInfo("../逃逸.txt"), symlink])
    resp = c.post("/api/files/archive", files={"file": ("批量包.zip", buf.read(), "application/zip")})
    assert resp.status_code == 201
    body = resp.json()
    assert body["count"] == 3 and body["skipped"] and len(body["skipped"]) == 2
    base = Path(body["path"])
    assert tmp_path in base.parents
    assert (base / "合同" / "附件" / "清单.xlsx").read_bytes() == b"PK"
    assert not (tmp_path / "逃逸.txt").exists(), "上跳条目不得写出批次目录"
    assert all("上跳" in s["reason"] or "软链" in s["reason"] for s in body["skipped"])


def test_archive_validations(client):
    c, tmp_path = client
    assert c.post("/api/files/archive", files={"file": ("不是压缩包.txt", b"x", "text/plain")}).status_code == 422
    assert c.post("/api/files/archive", files={"file": ("坏包.zip", b"not-a-zip", "application/zip")}).status_code == 422

    filtered = c.post("/api/files/archive",
                      files={"file": ("包.zip", _zip({"a.txt": b"x"}).read(), "application/zip")},
                      params={"extensions": ".docx"})
    assert filtered.status_code == 422 and "没有可用的文件" in filtered.json()["detail"]
    assert list((tmp_path / "uploads").glob("*/*")) == [], "无可解压文件时批次目录应清理"

    huge = c.post("/api/files/archive",
                  files={"file": ("多.zip", _zip({f"f{i}.txt": b"x" for i in range(1001)}).read(), "application/zip")})
    assert huge.status_code == 413 and "条目超上限" in huge.json()["detail"]
