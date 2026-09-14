"""N1：批次内「每个文件最优 run」的取数（真 DB / dev PG）。

线上事故：批次 341 条 run，而批次导出用 `list_runs(limit=200)` → 更早的**成功 run 被挤出
窗口** → 78 个已翻译的文件被当成「未翻译」，导出只能放回源文件（用户看到「导出全是没翻译的」）。
`best_runs_by_batch` 用 DISTINCT ON 一条 SQL 取「成功 > 暂停/跳过 > 其它，同级最新」。
"""

from __future__ import annotations

import secrets

import pytest

from store.db import Db
from store.pipeline_repo import PipelineRepo

from tests._dbutil import db_reachable

DB_URL = "postgresql://command_dev:root@192.168.8.41:5432/command_dev"
pytestmark = pytest.mark.skipif(not db_reachable(DB_URL), reason="dev PG 不可达，跳过集成测试")


@pytest.fixture
def repo():
    db = Db(DB_URL)
    db.apply_migrations()
    yield PipelineRepo(db)


def _add(repo, batch: str, file: str, status: str, ts: str, flow: str = "flow.translate.xlsx") -> str:
    rid = "p_" + secrets.token_hex(8)
    with repo._db.pool.connection() as conn:  # noqa: SLF001
        conn.execute(
            "INSERT INTO pipeline_runs (id, pipeline_id, input, status, batch_id, created_at) "
            "VALUES (%s, %s, %s, %s, %s, %s)",
            (rid, flow, __import__("psycopg.types.json", fromlist=["Json"]).Json({"file": file}),
             status, batch, ts))
    return rid


def test_prefers_success_even_when_it_is_older(repo):
    """成功 run 更早也优先于更晚的失败 run（这正是线上被窗口切掉的场景）。"""
    batch = "b_test_" + secrets.token_hex(4)
    old_ok = _add(repo, batch, "/u/A.xlsx", "succeeded", "2026-09-14T10:00:00")
    _add(repo, batch, "/u/A.xlsx", "failed", "2026-09-14T12:00:00")
    _add(repo, batch, "/u/B.xlsx", "failed", "2026-09-14T12:30:00")
    picked = {str(r["input"]["file"]): r for r in repo.best_runs_by_batch(batch)}
    assert len(picked) == 2
    assert picked["/u/A.xlsx"]["id"] == old_ok and picked["/u/A.xlsx"]["status"] == "succeeded"
    assert picked["/u/B.xlsx"]["status"] == "failed"
    _cleanup(repo, batch)


def test_paused_beats_failed_and_newest_wins_in_same_rank(repo):
    batch = "b_test_" + secrets.token_hex(4)
    _add(repo, batch, "/u/C.pdf", "failed", "2026-09-14T12:00:00")
    paused = _add(repo, batch, "/u/C.pdf", "paused", "2026-09-14T11:00:00")
    older = _add(repo, batch, "/u/D.pdf", "failed", "2026-09-14T09:00:00")
    newer = _add(repo, batch, "/u/D.pdf", "failed_review", "2026-09-14T13:00:00")
    picked = {str(r["input"]["file"]): r for r in repo.best_runs_by_batch(batch)}
    assert picked["/u/C.pdf"]["id"] == paused          # 暂停优于失败
    assert picked["/u/D.pdf"]["id"] == newer           # 同档取最新
    assert older != newer
    _cleanup(repo, batch)


def test_scales_beyond_any_page_window(repo):
    """300 条 run（> 旧窗口 200）：最早那条成功 run 仍必须被取到。"""
    batch = "b_test_" + secrets.token_hex(4)
    first = _add(repo, batch, "/u/early.xlsx", "succeeded", "2026-09-14T00:00:00")
    for i in range(299):
        _add(repo, batch, f"/u/fill{i}.xlsx", "failed", f"2026-09-14T01:00:{i % 60:02d}")
    picked = {str(r["input"]["file"]): r for r in repo.best_runs_by_batch(batch)}
    assert picked["/u/early.xlsx"]["id"] == first
    assert len(picked) == 300
    _cleanup(repo, batch)


def _cleanup(repo, batch: str) -> None:
    with repo._db.pool.connection() as conn:  # noqa: SLF001
        conn.execute("DELETE FROM pipeline_runs WHERE batch_id = %s", (batch,))
