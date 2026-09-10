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
