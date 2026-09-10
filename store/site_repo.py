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

    def upsert(self, view: dict[str, Any], *, is_builtin: bool = True) -> None:
        with self._db.pool.connection() as conn:
            conn.execute(
                """
                INSERT INTO site_views (id, type, title, icon, when_capability, props, sort, is_default, is_builtin)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (id) DO UPDATE SET
                    type = EXCLUDED.type,
                    title = EXCLUDED.title,
                    icon = EXCLUDED.icon,
                    when_capability = EXCLUDED.when_capability,
                    props = EXCLUDED.props,
                    sort = EXCLUDED.sort,
                    is_default = EXCLUDED.is_default,
                    is_builtin = EXCLUDED.is_builtin,
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
                    is_builtin,
                ),
            )

    def delete(self, view_id: str) -> bool:
        with self._db.pool.connection() as conn:
            cur = conn.execute("DELETE FROM site_views WHERE id = %s", (view_id,))
        return cur.rowcount > 0

    def seed(self, views: list[dict[str, Any]]) -> int:
        """幂等写入内置声明，并同步删除已不在清单内的内置视图（启动/热部署时调用）。

        同步化语义：内置声明以代码清单为准——代码删掉的视图（如旧 OCR 四 Tab），
        已部署库中的残留行在本次 seed 一并清除。全量对账（id NOT IN 清单）而非
        仅 is_builtin 行：010 之前旧 seed 写入的行 is_builtin 全为 FALSE，按标记
        删不到；当前无自建视图渠道，全量对账安全。将来若开放自建视图 API，
        须把 is_builtin = FALSE 的行排除出删除条件。
        """
        for view in views:
            self.upsert(view)
        builtin_ids = [v["id"] for v in views]
        placeholders = ", ".join("%s" for _ in builtin_ids)
        with self._db.pool.connection() as conn:
            cur = conn.execute(
                f"DELETE FROM site_views WHERE id NOT IN ({placeholders})",
                builtin_ids,
            )
            removed = cur.rowcount
        return len(views) + removed
