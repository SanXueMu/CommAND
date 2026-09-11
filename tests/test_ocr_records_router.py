"""010/批次① OCR 结果库只读端点单测：库列表与记录查询（tmp 目录，不碰真实 data/）。"""

import json
import os
from pathlib import Path

import pytest

from api import ocr_records_router as router
from command_shared import ocr_storage


@pytest.fixture
def ocr_dir(tmp_path, monkeypatch):
    d = tmp_path / "ocr"
    d.mkdir()
    monkeypatch.setenv("COMMAND_DATA_DIR", str(tmp_path))
    return d


def _make_db(path, rows):
    conn = ocr_storage.connect(path)
    try:
        ocr_storage.initialize(conn)
        for r in rows:
            ocr_storage.append_records(conn, r["file_hash"], r["source_path"], [(1, r["record"])])
    finally:
        conn.close()


def test_list_dbs_and_records(ocr_dir):
    _make_db(ocr_dir / "a.ocr_results.db", [
        {"file_hash": "h1", "source_path": "a.pdf", "record": {"金额": "100", "日期": "2026-01-01"}},
    ])
    dbs = router.list_dbs()
    assert dbs["dbs"] and dbs["dbs"][0]["name"] == "a.ocr_results.db"
    assert dbs["dbs"][0]["records"] == 1
    assert str(ocr_dir) in dbs["dbs"][0]["path"]

    out = router.read_records(db="a.ocr_results.db", limit=50)
    assert out["total"] == 1
    assert out["rows"][0]["金额"] == "100"
    assert "金额" in out["columns"]


def test_records_rejects_path_escape(ocr_dir):
    with pytest.raises(router.HTTPException):
        router.read_records(db="../secret.db", limit=10)


def test_records_missing_db(ocr_dir):
    with pytest.raises(router.HTTPException):
        router.read_records(db="nope.db", limit=10)


def test_corrupt_db_listed_with_zero_count(ocr_dir):
    (ocr_dir / "bad.db").write_text("not sqlite")
    dbs = router.list_dbs()
    bad = [x for x in dbs["dbs"] if x["name"] == "bad.db"]
    assert bad and bad[0]["records"] == 0


def test_read_records_source_file_reverse_lookup(ocr_dir):
    """原页预览：source_path 是裸文件名，上传却是 <uuid>_<原名> —— 需反查才能拿到真实路径。"""
    uploads = ocr_dir.parent / "uploads" / "2026-09-11"
    uploads.mkdir(parents=True)
    (uploads / "ab12cd34_x.pdf").write_bytes(b"%PDF-")

    _make_db(ocr_dir / "c.ocr_results.db", [
        {"file_hash": "h1", "source_path": "x.pdf", "record": {"金额": "1"}},
        {"file_hash": "h2", "source_path": "ghost.pdf", "record": {"金额": "2"}},
    ])
    out = router.read_records(db="c.ocr_results.db", limit=50)
    by_src = {r["source_path"]: r for r in out["rows"]}
    assert by_src["x.pdf"]["source_file"].endswith("ab12cd34_x.pdf"), "须反查到带 uuid 前缀的落盘文件"
    assert by_src["ghost.pdf"]["source_file"] == "", "原文件已不在盘上时给空串（前端据此置灰）"
    # 该行 data 内无「页码」→ 由 page_number 兜底（本夹具未传页码，故为 0）
    assert by_src["x.pdf"]["页码"] == by_src["x.pdf"]["page_number"], "须兜底 records.view.query 的协议键"


def test_path_filter_escapes_wildcards(ocr_dir):
    """path 过滤走 LIKE，用户输入的 %/_ 必须转义，否则会退化为全库命中。"""
    _make_db(ocr_dir / "d.ocr_results.db", [
        {"file_hash": f"h{i}", "source_path": name, "record": {"v": name}}
        for i, name in enumerate(["a.pdf", "b.pdf"])
    ])
    # 未转义时 "%" 会命中全部 2 条；转义后须为 0
    assert router.read_records(db="d.ocr_results.db", path="%")["total"] == 0
    assert router.read_records(db="d.ocr_results.db", path="_")["total"] == 0


def test_read_records_path_filter_and_pagination(ocr_dir):
    """path 过滤单文件范围 + offset 分页，total 随过滤联动。"""
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from api import ocr_records_router

    _make_db(ocr_dir / "b.ocr_results.db", [
        {"file_hash": f"h{i}", "source_path": "x.pdf" if i < 2 else "y.pdf",
         "record": {"金额": str(i * 100)}}
        for i in range(4)
    ])
    app = FastAPI()
    app.include_router(ocr_records_router.router, prefix="/api")
    with TestClient(app) as c:
        full = c.get("/api/ocr/records", params={"db": "b.ocr_results.db"}).json()
        assert full["total"] == 4
        only_x = c.get("/api/ocr/records", params={"db": "b.ocr_results.db", "path": "x.pdf"}).json()
        assert only_x["total"] == 2 and all(r["source_path"] == "x.pdf" for r in only_x["rows"])
        paged = c.get("/api/ocr/records", params={"db": "b.ocr_results.db", "limit": 2, "offset": 2}).json()
        assert len(paged["rows"]) == 2 and paged["offset"] == 2
