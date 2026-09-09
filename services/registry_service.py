"""L4 注册编排：扫描 tools/ 落位区、协议合规性检查、manifest 入库。"""

import json
from pathlib import Path
from typing import Any

from core.protocol import ToolManifest
from store.db import Db
from store.tool_repo import ToolRepo


class RegistryService:
    """扫描 tool.toml → ToolManifest 校验 → ToolRepo upsert；查询发现。"""

    def __init__(self, db: Db, tools_dir: Path, tool_repo: ToolRepo) -> None:
        self._db = db
        self._tools_dir = tools_dir
        self._tool_repo = tool_repo

    def scan(self) -> dict[str, Any]:
        found: list[Path] = sorted(self._tools_dir.glob("*/*/tool.toml"))
        valid: list[str] = []
        invalid: list[dict[str, str]] = []
        for path in found:
            try:
                manifest = ToolManifest.from_toml(path)
            except Exception as exc:
                invalid.append({"path": str(path), "error": str(exc)})
                continue
            self._tool_repo.upsert(manifest, path=str(path.parent))
            valid.append(manifest.tool.id)
        return {
            "found": len(found),
            "registered": valid,
            "invalid": invalid,
            "note": "" if valid or invalid else "tools/ 落位区暂无工具",
        }

    def list_tools(self) -> list[dict[str, Any]]:
        return self._tool_repo.list_active()

    def get_tool(self, tool_id: str) -> dict[str, Any] | None:
        return self._tool_repo.get(tool_id)
