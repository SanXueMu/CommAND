"""用户视图库（X5）：data/ocr/views/<id>.json 的单一存取点。

与模版库（command_shared/ocr_templates.TemplateStore）同构——文件三件套、
进程内锁、原子替换写、同名（同 id）覆盖保留 created_at。

区别：
- 视图只有 id/name/spec（ViewSpec JSON）三个字段，轻校验（spec 须为对象且 type 为字符串）；
- 内置视图由站点声明直发前端（不落本库），id 前缀 ``builtin.`` 保留，禁止占用。
"""
from __future__ import annotations

import json
import re
import threading
from datetime import datetime
from pathlib import Path

from core.errors import ToolDomainError, ToolNotFoundError

_ID_PATTERN = re.compile(r"^[a-z][a-z0-9_.]{2,63}$")
_RESERVED_PREFIX = "builtin."


def views_dir(data_dir: str | None = None) -> Path:
    root = Path(data_dir or __import__("os").environ.get("COMMAND_DATA_DIR", "data"))
    return root / "ocr" / "views"


class ViewStore:
    """用户视图库的单一存取点（进程内锁 + 原子替换写）。"""

    def __init__(self, data_dir: str | None = None) -> None:
        self._dir = views_dir(data_dir)
        self._lock = threading.Lock()

    def _path(self, view_id: str) -> Path:
        return self._dir / f"{view_id}.json"

    def _load(self, path: Path) -> dict:
        return json.loads(path.read_text(encoding="utf-8"))

    def list(self) -> list[dict]:
        with self._lock:
            items: list[dict] = []
            if not self._dir.exists():
                return items
            for path in sorted(self._dir.glob("*.json")):
                try:
                    item = self._load(path)
                except (json.JSONDecodeError, OSError):
                    continue  # 损坏条目跳过不炸列表
                items.append({
                    "id": item.get("id"), "name": item.get("name"),
                    "created_at": item.get("created_at"), "updated_at": item.get("updated_at"),
                })
            return items

    def get(self, view_id: str) -> dict:
        path = self._path(view_id)
        if not path.exists():
            raise ToolNotFoundError(f"视图不存在: {view_id}")
        with self._lock:
            return self._load(path)

    def upsert(self, view: dict) -> dict:
        vid = view.get("id") or ""
        if not _ID_PATTERN.match(vid):
            raise ToolDomainError(f"视图 id 须匹配 {_ID_PATTERN.pattern}: {vid}")
        if vid.startswith(_RESERVED_PREFIX):
            raise ToolDomainError(f"内置视图不可覆盖（id 前缀 {_RESERVED_PREFIX} 保留）")
        name = view.get("name")
        if not isinstance(name, str) or not name.strip():
            raise ToolDomainError("视图 name 须为非空字符串")
        spec = view.get("spec")
        if not isinstance(spec, dict) or not isinstance(spec.get("type"), str) or not spec.get("type"):
            raise ToolDomainError("spec 须为对象且含字符串 type（ViewSpec）")

        now = datetime.now().isoformat(timespec="seconds")
        existing = None
        with self._lock:
            if self._path(vid).exists():
                existing = self._load(self._path(vid))
            merged = {"id": vid, "name": name, "spec": spec,
                      "created_at": (existing or {}).get("created_at", now),
                      "updated_at": now}
            self._dir.mkdir(parents=True, exist_ok=True)
            tmp = self._path(vid).with_suffix(".json.tmp")
            tmp.write_text(json.dumps(merged, ensure_ascii=False, indent=2), encoding="utf-8")
            tmp.replace(self._path(vid))
        return {"id": vid, "status": "updated" if existing else "created"}

    def delete(self, view_id: str) -> dict:
        path = self._path(view_id)
        if not path.exists():
            raise ToolNotFoundError(f"视图不存在: {view_id}")
        with self._lock:
            path.unlink()
        return {"id": view_id, "status": "deleted"}
