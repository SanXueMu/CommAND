"""协议控制面仓库：发布注册 / 原始映像 / 投影映像 / 同步运行。

分层语义（蓝图「飞升」）：
- provider_snapshot 不可变——只有 INSERT，采集即固化；
- provider_projection 可再生成——is_current 唯一（部分唯一索引），翻转原子；
- provider_sync_run 是状态机持久层，重放判定看 SUCCEEDED 凭据。
"""

from __future__ import annotations

import json
from typing import Any

from store.db import Db


def _canonical_json(value: Any) -> str:
    """键序无关的稳定序列化（与 CommWEB contentHash 同思路，checksum 可对账）。"""

    def ser(v: Any) -> str:
        if v is None or not isinstance(v, (dict, list)):
            return json.dumps(v, ensure_ascii=False)
        if isinstance(v, list):
            return "[" + ",".join(ser(i) for i in v) + "]"
        return "{" + ",".join(
            f"{json.dumps(k, ensure_ascii=False)}:{ser(v[k])}" for k in sorted(v)
        ) + "}"

    return ser(value)


class ProtocolRepo:
    def __init__(self, db: Db) -> None:
        self._db = db

    # ── 协议发布 ──────────────────────────────────────────────

    def list_releases(self) -> list[dict[str, Any]]:
        with self._db.pool.connection() as conn:
            rows = conn.execute(
                "SELECT id, core, extensions, snapshot_schema, notes, released_at"
                " FROM protocol_release ORDER BY id DESC"
            ).fetchall()
        return [
            {
                "id": r[0], "core": r[1], "extensions": r[2], "snapshot_schema": r[3],
                "notes": r[4], "released_at": r[5].isoformat() if r[5] else None,
            }
            for r in rows
        ]

    def latest_release(self) -> dict[str, Any] | None:
        releases = self.list_releases()
        return releases[0] if releases else None

    def release(self, release_id: int) -> dict[str, Any] | None:
        with self._db.pool.connection() as conn:
            row = conn.execute(
                "SELECT id, core, extensions, snapshot_schema, notes, released_at"
                " FROM protocol_release WHERE id = %s", (release_id,)
            ).fetchone()
        if not row:
            return None
        return {
            "id": row[0], "core": row[1], "extensions": row[2], "snapshot_schema": row[3],
            "notes": row[4], "released_at": row[5].isoformat() if row[5] else None,
        }

    def ensure_release(
        self, release_id: int, core: int, extensions: dict[str, int],
        snapshot_schema: int, notes: str | None = None,
    ) -> None:
        """幂等登记协议发布（启动 lifespan 调用；变更 = 新 id 追加，禁止改旧行）。"""
        with self._db.pool.connection() as conn:
            conn.execute(
                "INSERT INTO protocol_release (id, core, extensions, snapshot_schema, notes)"
                " VALUES (%s, %s, %s, %s, %s) ON CONFLICT (id) DO NOTHING",
                (release_id, core, json.dumps(extensions, ensure_ascii=False), snapshot_schema, notes),
            )

    # ── 会员原始映像（不可变） ────────────────────────────────

    def insert_snapshot(
        self, provider_id: str, release_id: int, schema_version: int,
        payload: dict[str, Any], checksum: str,
    ) -> int:
        with self._db.pool.connection() as conn:
            cur = conn.execute(
                "INSERT INTO provider_snapshot (provider_id, release_id, schema_version, payload, checksum)"
                " VALUES (%s, %s, %s, %s, %s) RETURNING id",
                (provider_id, release_id, schema_version, json.dumps(payload, ensure_ascii=False), checksum),
            )
            return int(cur.fetchone()[0])

    def latest_snapshot(self, provider_id: str) -> dict[str, Any] | None:
        with self._db.pool.connection() as conn:
            row = conn.execute(
                "SELECT id, release_id, schema_version, payload, checksum, captured_at"
                " FROM provider_snapshot WHERE provider_id = %s ORDER BY id DESC LIMIT 1",
                (provider_id,),
            ).fetchone()
        if not row:
            return None
        return {
            "id": row[0], "release_id": row[1], "schema_version": row[2],
            "payload": row[3] if isinstance(row[3], dict) else json.loads(row[3] or "{}"),
            "checksum": row[4], "captured_at": row[5].isoformat() if row[5] else None,
        }

    # ── 投影映像（可再生成） ──────────────────────────────────

    def set_current_projection(
        self, provider_id: str, snapshot_id: int, release_id: int,
        payload: dict[str, Any], checksum: str,
    ) -> int:
        """原子翻转：旧行 is_current=false + 新行 is_current=true（同事务）。"""
        with self._db.pool.connection() as conn:
            conn.execute(
                "UPDATE provider_projection SET is_current = FALSE WHERE provider_id = %s AND is_current",
                (provider_id,),
            )
            cur = conn.execute(
                "INSERT INTO provider_projection (provider_id, snapshot_id, release_id, payload, checksum, is_current)"
                " VALUES (%s, %s, %s, %s, %s, TRUE) RETURNING id",
                (provider_id, snapshot_id, release_id, json.dumps(payload, ensure_ascii=False), checksum),
            )
            return int(cur.fetchone()[0])

    def current_projection(self, provider_id: str) -> dict[str, Any] | None:
        with self._db.pool.connection() as conn:
            row = conn.execute(
                "SELECT id, snapshot_id, release_id, payload, checksum, generated_at"
                " FROM provider_projection WHERE provider_id = %s AND is_current",
                (provider_id,),
            ).fetchone()
        if not row:
            return None
        return {
            "id": row[0], "snapshot_id": row[1], "release_id": row[2],
            "payload": row[3] if isinstance(row[3], dict) else json.loads(row[3] or "{}"),
            "checksum": row[4], "generated_at": row[5].isoformat() if row[5] else None,
        }

    # ── 同步运行（状态机） ────────────────────────────────────

    def insert_sync_run(
        self, provider_id: str, snapshot_id: int, from_release_id: int | None, to_release_id: int,
    ) -> int:
        with self._db.pool.connection() as conn:
            cur = conn.execute(
                "INSERT INTO provider_sync_run (provider_id, snapshot_id, from_release_id, to_release_id)"
                " VALUES (%s, %s, %s, %s) RETURNING id",
                (provider_id, snapshot_id, from_release_id, to_release_id),
            )
            return int(cur.fetchone()[0])

    def update_sync_run(
        self, run_id: int, status: str, *, error: str | None = None, checksum: str | None = None,
    ) -> None:
        with self._db.pool.connection() as conn:
            conn.execute(
                "UPDATE provider_sync_run SET status = %s, error = %s, checksum = COALESCE(%s, checksum),"
                " finished_at = CASE WHEN %s IN ('SUCCEEDED','FAILED','INCOMPATIBLE') THEN now() ELSE finished_at END"
                " WHERE id = %s",
                (status, error, checksum, status, run_id),
            )

    def succeeded_run(self, provider_id: str, snapshot_id: int, to_release_id: int) -> dict[str, Any] | None:
        """幂等凭据：同映像 + 同目标 release 已成功 → 重放直接命中。"""
        with self._db.pool.connection() as conn:
            row = conn.execute(
                "SELECT id, status, checksum, finished_at FROM provider_sync_run"
                " WHERE provider_id = %s AND snapshot_id = %s AND to_release_id = %s AND status = 'SUCCEEDED'"
                " ORDER BY id DESC LIMIT 1",
                (provider_id, snapshot_id, to_release_id),
            ).fetchone()
        if not row:
            return None
        return {"id": row[0], "status": row[1], "checksum": row[2],
                "finished_at": row[3].isoformat() if row[3] else None}

    def list_sync_runs(self, provider_id: str, limit: int = 10) -> list[dict[str, Any]]:
        with self._db.pool.connection() as conn:
            rows = conn.execute(
                "SELECT id, snapshot_id, from_release_id, to_release_id, status, error, checksum, started_at, finished_at"
                " FROM provider_sync_run WHERE provider_id = %s ORDER BY id DESC LIMIT %s",
                (provider_id, limit),
            ).fetchall()
        return [
            {
                "id": r[0], "snapshot_id": r[1], "from_release_id": r[2], "to_release_id": r[3],
                "status": r[4], "error": r[5], "checksum": r[6],
                "started_at": r[7].isoformat() if r[7] else None,
                "finished_at": r[8].isoformat() if r[8] else None,
            }
            for r in rows
        ]
