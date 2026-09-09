"""L6 tools 表仓储：manifest 快照读写（upsert by id）。"""

from typing import Any

from psycopg.types.json import Json

from core.protocol import ToolManifest
from store.db import Db

_COLUMNS = "id, name, version, description, input_types, output_types, runtime_kind"


class ToolRepo:
    """注册表持久化：upsert by id；查询返回视图 dict（get 另含完整 manifest）。"""

    def __init__(self, db: Db) -> None:
        self._db = db

    def upsert(self, manifest: ToolManifest) -> None:
        with self._db.pool.connection() as conn:
            conn.execute(
                """
                INSERT INTO tools (id, name, version, description, manifest, input_types, output_types, runtime_kind)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (id) DO UPDATE SET
                    name = EXCLUDED.name,
                    version = EXCLUDED.version,
                    description = EXCLUDED.description,
                    manifest = EXCLUDED.manifest,
                    input_types = EXCLUDED.input_types,
                    output_types = EXCLUDED.output_types,
                    runtime_kind = EXCLUDED.runtime_kind,
                    updated_at = now()
                """,
                (
                    manifest.tool.id,
                    manifest.tool.name,
                    manifest.tool.version,
                    manifest.tool.description,
                    Json(manifest.model_dump(mode="json")),
                    manifest.io.input_types,
                    manifest.io.output_types,
                    manifest.runtime.kind,
                ),
            )

    def list_active(self) -> list[dict[str, Any]]:
        with self._db.pool.connection() as conn:
            rows = conn.execute(
                f"SELECT {_COLUMNS} FROM tools WHERE status = 'active' ORDER BY id"
            ).fetchall()
        return [self._to_view(row) for row in rows]

    def get(self, tool_id: str) -> dict[str, Any] | None:
        with self._db.pool.connection() as conn:
            row = conn.execute(
                f"SELECT {_COLUMNS}, manifest FROM tools WHERE id = %s AND status = 'active'",
                (tool_id,),
            ).fetchone()
        if row is None:
            return None
        view = self._to_view(row[:7])
        view["manifest"] = row[7]
        return view

    @staticmethod
    def _to_view(row: tuple) -> dict[str, Any]:
        return {
            "id": row[0],
            "name": row[1],
            "version": row[2],
            "description": row[3],
            "input_types": row[4],
            "output_types": row[5],
            "runtime_kind": row[6],
        }
