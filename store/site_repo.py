"""站点视图声明仓库：/meta/site 的数据源（纯壳准则——声明是数据不是代码）。"""

from __future__ import annotations

import json
from typing import Any

from store.db import Db


class SiteRepo:
    def __init__(self, db: Db) -> None:
        self._db = db

    def list(self) -> list[dict[str, Any]]:
        with self._db.pool.connection() as conn:
            rows = conn.execute(
                "SELECT id, type, title, icon, when_capability, props, sort, is_default"
                " FROM site_views ORDER BY sort, id"
            ).fetchall()
        return [
            {
                "id": r[0],
                "type": r[1],
                "title": r[2],
                "icon": r[3],
                "when": {"capability": r[4]} if r[4] else None,
                "props": r[5] if isinstance(r[5], dict) else json.loads(r[5] or "{}"),
                "sort": r[6],
                "default": r[7],
            }
            for r in rows
        ]

    def upsert(self, view: dict[str, Any]) -> None:
        with self._db.pool.connection() as conn:
            conn.execute(
                """
                INSERT INTO site_views (id, type, title, icon, when_capability, props, sort, is_default)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (id) DO UPDATE SET
                    type = EXCLUDED.type,
                    title = EXCLUDED.title,
                    icon = EXCLUDED.icon,
                    when_capability = EXCLUDED.when_capability,
                    props = EXCLUDED.props,
                    sort = EXCLUDED.sort,
                    is_default = EXCLUDED.is_default,
                    updated_at = now()
                """,
                (
                    view["id"],
                    view["type"],
                    view["title"],
                    view.get("icon"),
                    (view.get("when") or {}).get("capability"),
                    json.dumps(view.get("props", {}), ensure_ascii=False),
                    view.get("sort", 100),
                    bool(view.get("default")),
                ),
            )

    def delete(self, view_id: str) -> bool:
        with self._db.pool.connection() as conn:
            cur = conn.execute("DELETE FROM site_views WHERE id = %s", (view_id,))
        return cur.rowcount > 0

    def seed(self, views: list[dict[str, Any]]) -> int:
        """幂等写入内置声明（启动/热部署时调用）；返回写入条数。"""
        for view in views:
            self.upsert(view)
        return len(views)
