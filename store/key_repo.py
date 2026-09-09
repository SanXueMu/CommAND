"""L6 keys 表仓储：LLM 密钥命名管理（打码对外，运行时全量注入 ctx）。"""

from typing import Any

from store.db import Db

_MASK = "****"


def mask_key(value: str) -> str:
    """打码：只露末 4 位。"""
    return _MASK + value[-4:] if len(value) > 4 else _MASK


class KeyRepo:
    """密钥持久化：upsert by name；is_default 单一化由仓储事务保证。"""

    def __init__(self, db: Db) -> None:
        self._db = db

    def upsert(self, name: str, provider: str, base_url: str, api_key: str, is_default: bool) -> None:
        with self._db.pool.connection() as conn:
            with conn.transaction():
                if is_default:
                    conn.execute("UPDATE keys SET is_default = FALSE WHERE is_default")
                conn.execute(
                    """
                    INSERT INTO keys (name, provider, base_url, api_key, is_default)
                    VALUES (%s, %s, %s, %s, %s)
                    ON CONFLICT (name) DO UPDATE SET
                        provider = EXCLUDED.provider,
                        base_url = EXCLUDED.base_url,
                        api_key = EXCLUDED.api_key,
                        is_default = EXCLUDED.is_default,
                        updated_at = now()
                    """,
                    (name, provider, base_url, api_key, is_default),
                )

    def list(self) -> list[dict[str, Any]]:
        """打码列表：api_key 只露末 4 位。"""
        with self._db.pool.connection() as conn:
            rows = conn.execute(
                "SELECT name, provider, base_url, api_key, is_default, updated_at FROM keys ORDER BY name"
            ).fetchall()
        return [
            {
                "name": r[0],
                "provider": r[1],
                "base_url": r[2],
                "api_key": mask_key(r[3]),
                "is_default": r[4],
                "updated_at": r[5].isoformat(),
            }
            for r in rows
        ]

    def delete(self, name: str) -> bool:
        with self._db.pool.connection() as conn:
            cur = conn.execute("DELETE FROM keys WHERE name = %s", (name,))
            return cur.rowcount > 0

    def all_for_runtime(self) -> dict[str, dict[str, str]]:
        """运行时注入：{name: {provider, base_url, api_key}}；明文仅存在于 worker 进程内存。"""
        with self._db.pool.connection() as conn:
            rows = conn.execute(
                "SELECT name, provider, base_url, api_key, is_default FROM keys"
            ).fetchall()
        return {
            r[0]: {"provider": r[1], "base_url": r[2], "api_key": r[3], "is_default": r[4]}
            for r in rows
        }
