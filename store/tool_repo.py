"""L6 tools 表仓储：manifest 快照读写（upsert by id）。"""

from typing import Any

from psycopg.types.json import Json

from core.protocol import ToolManifest
from store.db import Db

_COLUMNS = "id, name, version, description, input_types, output_types, runtime_kind, path, status, hidden"


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
                -- status/hidden 归 PATCH 管理（06 D1），注册 upsert 不覆盖运行时启停
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

    def list_active(self, include_hidden: bool = False) -> list[dict[str, Any]]:
        """列表瘦身：SQL 侧提取 tags，不下发整份 manifest（详情端点才带）。
        hidden 默认不返回（06 D1）；disabled 工具仍返回（前端置灰），由 enabled 字段区分。"""
        hidden_clause = "" if include_hidden else "AND hidden = false"
        with self._db.pool.connection() as conn:
            rows = conn.execute(
                f"SELECT {_COLUMNS}, manifest->'tool'->'tags' AS tags "
                f"FROM tools WHERE status IN ('active','disabled') {hidden_clause} ORDER BY id"
            ).fetchall()
        return [self._to_view(row) for row in rows]

    def get(self, tool_id: str, include_disabled: bool = False) -> dict[str, Any] | None:
        status_clause = "" if include_disabled else "AND status = 'active'"
        with self._db.pool.connection() as conn:
            row = conn.execute(
                f"SELECT {_COLUMNS}, manifest FROM tools WHERE id = %s {status_clause}",
                (tool_id,),
            ).fetchone()
        if row is None:
            return None
        view = self._with_manifest_extras(self._to_view(row), row[10])
        view["manifest"] = row[10]
        return view

    def set_availability(self, tool_id: str, *, enabled: bool | None = None,
                         hidden: bool | None = None) -> dict[str, Any] | None:
        """06 D1：启停/显隐 PATCH——只动 status/hidden 两列。"""
        sets, params = [], []
        if enabled is not None:
            sets.append("status = %s")
            params.append("active" if enabled else "disabled")
        if hidden is not None:
            sets.append("hidden = %s")
            params.append(hidden)
        if not sets:
            return self.get(tool_id, include_disabled=True)
        params.append(tool_id)
        with self._db.pool.connection() as conn:
            row = conn.execute(
                f"UPDATE tools SET {', '.join(sets)} WHERE id = %s RETURNING {_COLUMNS}",
                tuple(params),
            ).fetchone()
        return self._to_view(row) if row else None

    @staticmethod
    def _with_manifest_extras(view: dict[str, Any], manifest: dict[str, Any] | None) -> dict[str, Any]:
        """列表/详情视图附带 tags（存于 manifest JSONB，无需独立列）。"""
        view["tags"] = (manifest or {}).get("tool", {}).get("tags", [])
        return view

    @staticmethod
    def _to_view(row: tuple) -> dict[str, Any]:
        view = {
            "id": row[0],
            "name": row[1],
            "version": row[2],
            "description": row[3],
            "input_types": row[4],
            "output_types": row[5],
            "runtime_kind": row[6],
            "path": row[7],
            "enabled": row[8] != "disabled",
            "hidden": row[9],
        }
        return view
