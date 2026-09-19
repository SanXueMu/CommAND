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
    assert [x["name"] for x in body["skipped"]] == ["C/演讲.pptx"]
    assert body["skipped"][0]["reason"]
    # 文件本身照样落盘（导出要放原文件）
    assert Path(by_rel["C/演讲.pptx"]["path"]).is_file()


def test_batch_rejects_bad_input_and_rolls_back(client):
    """真正的越界（路径穿越/超量）仍整批失败并回滚；空文件/白名单外改为留档跳过。"""
    c, tmp_path = client
    evil = c.post("/api/files/batch", files=[("files", ("../逃逸.pdf", b"x", "application/pdf"))])
    assert evil.status_code == 422
    batches = list((tmp_path / "uploads").glob("*/*")) if (tmp_path / "uploads").exists() else []
    assert batches == [], "越界即整批回滚，不留半批脏数据"

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

    # 白名单外改为留档跳过（导出要放源文件）；只有「没有任何可用条目」才 422
    foreign = c.post("/api/files/archive",
                     files={"file": ("包.zip", _zip({"a.txt": b"x"}).read(), "application/zip")},
                     params={"extensions": ".docx"})
    assert foreign.status_code == 201
    fb = foreign.json()
    assert fb["files"][0]["skip"] is True and fb["skipped"][0]["name"] == "a.txt"

    only_junk = c.post("/api/files/archive", files={"file": ("空包.zip", _zip({}).read(), "application/zip")})
    assert only_junk.status_code == 422 and "没有可用的文件" in only_junk.json()["detail"]

    huge = c.post("/api/files/archive",
                  files={"file": ("多.zip", _zip({f"f{i}.txt": b"x" for i in range(1001)}).read(), "application/zip")})
    assert huge.status_code == 413 and "条目超上限" in huge.json()["detail"]


def test_batch_manifests_lookup(client):
    """批次名查询：刷新后仍能显示根目录名（未知 id 静默跳过）。"""
    c, tmp_path = client
    up = c.post("/api/files/batch", files=[("files", ("投标资料/A/合同.pdf", b"%PDF", "application/pdf"))])
    bid = up.json()["batch_id"]
    resp = c.get(f"/api/files/batches?ids={bid},b_deadbeef,not-an-id")
    assert resp.status_code == 200
    body = resp.json()
    assert body["names"] == {bid: "投标资料"} and body["count"] == {bid: 1}


def test_list_batches_returns_all_without_ids(client):
    """批次下拉数据源：不带 ids 时返回全部批次（无窗口），含根目录名与文件数。"""
    c, tmp_path = client
    up1 = c.post("/api/files/batch", files=[("files", ("批次一/A/合同.pdf", b"%PDF", "application/pdf"))])
    up2 = c.post("/api/files/batch", files=[("files", ("批次二/B/报告.docx", b"PK", "application/vnd.openxmlformats-officedocument.wordprocessingml.document"))])
    resp = c.get("/api/files/batches")
    assert resp.status_code == 200
    batches = resp.json()["batches"]
    ids = [b["id"] for b in batches]
    assert up1.json()["batch_id"] in ids and up2.json()["batch_id"] in ids
    by_id = {b["id"]: b for b in batches}
    assert by_id[up2.json()["batch_id"]]["root"] == "批次二"
    assert by_id[up2.json()["batch_id"]]["files"] == 1
    assert by_id[up2.json()["batch_id"]]["created_at"]
    # 新批次在前（created_at 倒序）
    assert ids.index(up2.json()["batch_id"]) < ids.index(up1.json()["batch_id"])


def test_batch_empty_and_foreign_files_do_not_kill_batch(client):
    """空文件 / 白名单外文件（PPT）不再 422 整批回滚：留档 + 打标跳过（导出能放回源文件）。"""
    c, tmp_path = client
    resp = c.post("/api/files/batch?extensions=.pdf,.txt", files=[
        ("files", ("资料/A/正文.pdf", b"%PDF-1", "application/pdf")),
        ("files", ("资料/B/占位.txt", b"", "text/plain")),        # 0 字节
        ("files", ("资料/C/演讲.pptx", b"PK", "application/octet-stream")),  # 白名单外
    ])
    assert resp.status_code == 201, resp.text
    body = resp.json()
    by_rel = {f["rel"]: f for f in body["files"]}
    assert set(by_rel) == {"A/正文.pdf", "B/占位.txt", "C/演讲.pptx"}
    assert not by_rel["A/正文.pdf"].get("skip")
    assert by_rel["B/占位.txt"]["skip"] is True and by_rel["B/占位.txt"]["empty"] is True
    assert by_rel["C/演讲.pptx"]["skip"] is True and "empty" not in by_rel["C/演讲.pptx"]
    assert {x["name"] for x in body["skipped"]} == {"B/占位.txt", "C/演讲.pptx"}
    # 留档：空文件与 PPT 都还在盘上（导出按原结构放回）
    assert Path(by_rel["B/占位.txt"]["path"]).is_file()
    assert Path(by_rel["C/演讲.pptx"]["path"]).is_file()


def test_batch_skips_os_junk_files(client):
    """系统临时文件（.DS_Store / ~$xxx.docx）不落盘、不进清单、不占配额（服务端兜底）。"""
    client, _ = client
    resp = client.post("/api/files/batch", data={"paths": ["d/合同.docx", "d/.DS_Store", "d/~$合同.docx"]},
                       files=[("files", ("d/合同.docx", b"DOCX", "application/octet-stream")),
                              ("files", ("d/.DS_Store", b"JUNK", "application/octet-stream")),
                              ("files", ("d/~$合同.docx", b"JUNK", "application/octet-stream"))])
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert [f["name"] for f in body["files"]] == ["合同.docx"]
    assert {s["name"] for s in body["skipped"]} == {".DS_Store", "~$合同.docx"}
    assert not (Path(body["path"]) / ".DS_Store").exists()
    assert not (Path(body["path"]) / "~$合同.docx").exists()


def test_batches_domain_filter(client, monkeypatch):
    """X2：flow_ids 只返回对应流域的批次（翻译/OCR 下拉互不可见）。"""
    import deps
    c, tmp_path = client
    up1 = c.post("/api/files/batch", files=[("files", ("翻译批/a.docx", b"PK", "application/octet-stream"))])
    b1 = up1.json()["batch_id"]
    up2 = c.post("/api/files/batch", files=[("files", ("识别批/b.pdf", b"%PDF", "application/pdf"))])
    b2 = up2.json()["batch_id"]

    # 桩掉 run 查询（SQL 是平凡 DISTINCT；此处验端点参数解析×清单过滤的接线）
    class _Repo:
        @staticmethod
        def batch_ids_of_flows(flow_ids):
            table = {"flow.ocr.smart": {b2}, "flow.translate.image": {b1}}
            return set().union(*(table[f] for f in flow_ids if f in table))
    monkeypatch.setattr(deps, "get_pipeline_repo", lambda: _Repo())

    all_b = c.get("/api/files/batches").json()["batches"]
    assert {x["id"] for x in all_b} >= {b1, b2}
    ocr_only = c.get(f"/api/files/batches?flow_ids=flow.ocr.smart").json()["batches"]
    assert [x["id"] for x in ocr_only] == [b2]
    tr_only = c.get(f"/api/files/batches?flow_ids=flow.translate.image").json()["batches"]
    assert [x["id"] for x in tr_only] == [b1]
