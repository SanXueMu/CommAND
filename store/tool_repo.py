"""L6 tools 表仓储：manifest 快照 upsert 与查询（S1 实现完整入库）。"""

from typing import Any

from core.protocol import ToolManifest
from store.db import Db


class ToolRepo:
    """注册表持久化：upsert by id；input/output_types 与 runtime_kind 冗余列供检索。"""

    def __init__(self, db: Db) -> None:
        self._db = db

    def upsert(self, manifest: ToolManifest) -> None:
        raise NotImplementedError("S1 里程碑实现")

    def list_active(self) -> list[dict[str, Any]]:
        return []

    def get(self, tool_id: str) -> dict[str, Any] | None:
        return None
