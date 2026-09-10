"""L6 tools 表仓储：manifest 快照读写（upsert by id）。"""

from typing import Any

from psycopg.types.json import Json

from core.protocol import ToolManifest
from store.db import Db

_COLUMNS = "id, name, version, description, input_types, output_types, runtime_kind, path"


class ToolRepo:
    """注册表持久化：upsert by id；查询返回视图 dict（get 另含完整 manifest）。"""

    def __init__(self, db: Db) -> None:
        self._db = db

    def upsert(self, manifest: ToolManifest, path: str | None = None) -> None:
        with self._db.pool.connection() as conn:
            conn.execute(
                """
                INSERT INTO tools (id, name, version, description, manifest, input_types, output_types, runtime_kind, path)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (id) DO UPDATE SET
                    name = EXCLUDED.name,
                    version = EXCLUDED.version,
                    description = EXCLUDED.description,
                    manifest = EXCLUDED.manifest,
                    input_types = EXCLUDED.input_types,
                    output_types = EXCLUDED.output_types,
                    runtime_kind = EXCLUDED.runtime_kind,
                    path = EXCLUDED.path,
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
                    path,
                ),
            )

    def list_active(self) -> list[dict[str, Any]]:
        """列表瘦身：SQL 侧提取 tags，不下发整份 manifest（详情端点才带）。"""
        with self._db.pool.connection() as conn:
            rows = conn.execute(
                f"SELECT {_COLUMNS}, manifest->'tool'->'tags' AS tags "
                "FROM tools WHERE status = 'active' ORDER BY id"
            ).fetchall()
        return [{**self._to_view(row[:8]), "tags": row[8] or []} for row in rows]

    def get(self, tool_id: str) -> dict[str, Any] | None:
        with self._db.pool.connection() as conn:
            row = conn.execute(
                f"SELECT {_COLUMNS}, manifest FROM tools WHERE id = %s AND status = 'active'",
                (tool_id,),
            ).fetchone()
        if row is None:
            return None
        view = self._with_manifest_extras(self._to_view(row[:8]), row[8])
        view["manifest"] = row[8]
        return view

    @staticmethod
    def _with_manifest_extras(view: dict[str, Any], manifest: dict[str, Any] | None) -> dict[str, Any]:
        """列表/详情视图附带 tags（存于 manifest JSONB，无需独立列）。"""
        view["tags"] = (manifest or {}).get("tool", {}).get("tags", [])
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
            "path": row[7],
        }
