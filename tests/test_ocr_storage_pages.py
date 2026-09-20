"""AE 批次：records 表主键含 seq（一页多条分录）+ 页级替换 + 旧库自动迁移。"""
from __future__ import annotations

import sqlite3

import pytest

from command_shared import ocr_storage


def _r(subject: str, amount: str = "100") -> dict:
    return {"总账科目": subject, "借方金额": amount, "页码": 1}


@pytest.fixture
def db(tmp_path):
    connection = ocr_storage.connect(tmp_path / "x.ocr_results.db")
    ocr_storage.initialize(connection)
    yield connection
    connection.close()


def test_multi_records_per_page_all_persisted(db):
    """一页多条分录全部入库（旧 OR IGNORE 主键会静默吞掉第 2 条起——本批根因）。"""
    written = ocr_storage.append_records(db, "h", "a.pdf", [(1, _r("现金")), (1, _r("银行存款")), (1, _r("管理费用"))])
    assert written == 3
    rows = ocr_storage.read_records(db)
    assert len(rows) == 3 and [r["总账科目"] for r in rows] == ["现金", "银行存款", "管理费用"]
    cached = ocr_storage.get_cached_rows(db, "h", "a.pdf")
    assert list(cached) == [1] and len(cached[1]) == 3  # 缓存键仍是页维度


def test_page_replace_on_retry(db):
    """失败页重跑 = 页级替换：旧内容整页删除后写入新全量（不是叠加 5 条）。"""
    ocr_storage.append_records(db, "h", "a.pdf", [(1, _r("现金", "1"))])
    ocr_storage.append_records(db, "h", "a.pdf", [(1, _r("现金", "2")), (1, _r("银行存款", "2"))])
    rows = ocr_storage.read_records(db)
    assert len(rows) == 2 and rows[0]["借方金额"] == "2"  # 新内容生效


def test_record_mode_overwrites(db):
    """record 模式（整文件一条，row=1）：重跑覆盖旧记录。"""
    ocr_storage.append_records(db, "h", "a.pdf", [(1, {"x": "old"})])
    ocr_storage.append_records(db, "h", "a.pdf", [(1, {"x": "new"})])
    rows = ocr_storage.read_records(db)
    assert len(rows) == 1 and rows[0]["x"] == "new"


def test_pages_ordered_by_seq(db):
    """跨页顺序：页码优先，页内按 seq；write_records 式全新行号不受替换影响。"""
    ocr_storage.append_records(db, "h", "a.pdf", [
        (2, _r("p2a")), (2, _r("p2b")), (3, _r("p3")), (1, _r("p1"))])
    rows = ocr_storage.read_records(db)
    assert [r["总账科目"] for r in rows] == ["p1", "p2a", "p2b", "p3"]


def test_legacy_db_auto_migration(tmp_path):
    """旧库（主键无 seq）首触自动迁移：旧行 seq=0 保留，新写入多条正常。"""
    path = tmp_path / "legacy.ocr_results.db"
    connection = sqlite3.connect(path)
    connection.executescript(
        """
        CREATE TABLE records (
            file_hash TEXT NOT NULL, source_path TEXT NOT NULL,
            row_number INTEGER NOT NULL, page_number INTEGER NOT NULL, data TEXT NOT NULL,
            PRIMARY KEY (file_hash, source_path, row_number));
        INSERT INTO records VALUES ('h', 'old.pdf', 1, 1, '{"旧": true}');
        """)
    connection.commit()
    connection.close()

    connection = ocr_storage.connect(path)  # initialize 触发迁移
    ocr_storage.initialize(connection)
    try:
        cols = [r["name"] for r in connection.execute("PRAGMA table_info(records)")]
        assert "seq" in cols
        assert len(ocr_storage.read_records(connection)) == 1  # 旧行保留
        ocr_storage.append_records(connection, "h2", "new.pdf",
                                   [(1, _r("现金")), (1, _r("银行存款"))])
        rows = [r for r in ocr_storage.read_records(connection) if r.get("旧") is None]
        assert len(rows) == 2
    finally:
        connection.close()


# ---------- AP：页级缓存指纹 + 强制重识别 + 默认库名归属 ----------

def test_cache_requires_matching_fingerprint(db):
    """AP-A：只有指纹一致的行算命中；换指纹（改了模版/模型）即失效。"""
    ocr_storage.append_records(db, "h", "a.pdf", [(1, _r("现金"))], fingerprint="fp1")
    assert list(ocr_storage.get_cached_rows(db, "h", "a.pdf", "fp1")) == [1]
    assert ocr_storage.get_cached_rows(db, "h", "a.pdf", "fp2") == {}
    assert list(ocr_storage.get_cached_rows(db, "h", "a.pdf")) == [1], "不传指纹保持兼容"


def test_legacy_db_gains_fingerprint_column(tmp_path):
    """更旧库（有 seq 无 fingerprint）自动补列；旧行 '' → 与任何新指纹都不匹配。"""
    connection = ocr_storage.connect(tmp_path / "old.db")
    connection.executescript(
        """
        CREATE TABLE records (
            file_hash TEXT NOT NULL, source_path TEXT NOT NULL, row_number INTEGER NOT NULL,
            seq INTEGER NOT NULL DEFAULT 0, page_number INTEGER NOT NULL, data TEXT NOT NULL,
            PRIMARY KEY (file_hash, source_path, row_number, seq));
        INSERT INTO records VALUES ('h', 'a.pdf', 1, 0, 1, '{"总账科目":"现金"}');
        """)
    ocr_storage.initialize(connection)
    columns = [r["name"] for r in connection.execute("PRAGMA table_info(records)")]
    assert "fingerprint" in columns
    assert ocr_storage.get_cached_rows(connection, "h", "a.pdf", "anything") == {}
    assert len(ocr_storage.get_cached_rows(connection, "h", "a.pdf", "")) == 1
    connection.close()


def test_delete_file_rows_is_force_reset(db):
    """AP-B：force 用——清掉该文件全部行（其它文件不动）。"""
    ocr_storage.append_records(db, "h", "a.pdf", [(1, _r("现金")), (2, _r("银行存款"))])
    ocr_storage.append_records(db, "h", "b.pdf", [(1, _r("管理费用"))])
    assert ocr_storage.delete_file_rows(db, "h", "a.pdf") == 2
    assert ocr_storage.get_cached_rows(db, "h", "a.pdf") == {}
    assert list(ocr_storage.get_cached_rows(db, "h", "b.pdf")) == [1]


def test_default_db_path_scopes_to_upload():
    """AP-C：库名带本次上传的 uuid8——同一次上传稳定、不同批次各自独立。"""
    batch_a = "/data/uploads/2026-09-20/aa11bb22_合同档案/8._Agreement/2002年2月记账凭证.pdf"
    batch_b = "/data/uploads/2026-09-21/cc33dd44_合同档案/8._Agreement/2002年2月记账凭证.pdf"
    single = "/data/uploads/2026-09-20/ee55ff66_2002年2月记账凭证.pdf"

    a = ocr_storage.default_db_path(batch_a)
    assert a.name == "aa11bb22_2002年2月记账凭证.ocr_results.db"
    assert ocr_storage.default_db_path(batch_a) == a, "同一上传路径稳定（重跑命中缓存）"
    assert ocr_storage.default_db_path(batch_b).name != a.name, "换批次必须换库"
    assert ocr_storage.default_db_path(single).name == "ee55ff66_2002年2月记账凭证.ocr_results.db", \
        "单文件上传的文件名已带 uuid8，不重复加前缀"
