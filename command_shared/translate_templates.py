"""翻译模版库（translee 体验还原）：data/translate/templates/<id>.json 的存取与生命周期。

模版结构（translee templates.json 对齐）：
  {id, name, desc, source_lang, target_lang, model, terms: [[src, tgt], ...],
   enabled, created_at, updated_at}
术语表内嵌于模版：翻译时由引擎作为 glossary_clause 注入，术语原文不走缓存。
"""
from __future__ import annotations

import json
import os
import re
import threading
from datetime import datetime
from pathlib import Path

from core.errors import ToolDomainError, ToolNotFoundError

_ID_PATTERN = re.compile(r"^[a-z][a-z0-9_.]{2,63}$")


def templates_dir(data_dir: str | None = None) -> Path:
    root = Path(data_dir or os.environ.get("COMMAND_DATA_DIR", "data"))
    return root / "translate" / "templates"


def _norm_terms(terms) -> list[list[str]]:
    if terms is None:
        return []
    if not isinstance(terms, list):
        raise ToolDomainError("terms 须为 [[原文, 译文], ...] 数组")
    out: list[list[str]] = []
    for pair in terms:
        if not isinstance(pair, (list, tuple)) or len(pair) != 2:
            raise ToolDomainError("terms 每项须为 [原文, 译文] 二元组")
        src, tgt = str(pair[0]).strip(), str(pair[1]).strip()
        if src:
            out.append([src, tgt])
    return out


class TranslateTemplateStore:
    """翻译模版文件存取（进程内锁 + 原子替换写）。"""

    def __init__(self, data_dir: str | None = None) -> None:
        self._dir = templates_dir(data_dir)
        self._lock = threading.Lock()

    def _path(self, template_id: str) -> Path:
        return self._dir / f"{template_id}.json"

    def _load(self, path: Path) -> dict:
        return json.loads(path.read_text(encoding="utf-8"))

    def list(self, enabled: bool | None = None, keyword: str | None = None) -> list[dict]:
        with self._lock:
            items = []
            if not self._dir.exists():
                return items
            for path in sorted(self._dir.glob("*.json")):
                try:
                    item = self._load(path)
                except (json.JSONDecodeError, OSError):
                    continue
                if enabled is not None and bool(item.get("enabled")) is not enabled:
                    continue
                if keyword and keyword not in f"{item.get('id','')} {item.get('name','')}":
                    continue
                items.append({
                    "id": item.get("id"), "name": item.get("name"), "desc": item.get("desc"),
                    "source_lang": item.get("source_lang"), "target_lang": item.get("target_lang"),
                    "model": item.get("model"), "terms_count": len(item.get("terms") or []),
                    "enabled": bool(item.get("enabled")), "updated_at": item.get("updated_at"),
                })
            return items

    def exists(self, template_id: str) -> bool:
        return self._path(template_id).exists()

    def get(self, template_id: str) -> dict:
        path = self._path(template_id)
        if not path.exists():
            raise ToolNotFoundError(f"翻译模版不存在: {template_id}")
        with self._lock:
            return self._load(path)

    def upsert(self, template: dict) -> dict:
        tid = template.get("id") or ""
        if not _ID_PATTERN.match(tid):
            raise ToolDomainError(f"模版 id 须匹配 {_ID_PATTERN.pattern}: {tid}")
        name = template.get("name")
        if not isinstance(name, str) or not name.strip():
            raise ToolDomainError("name 须为非空字符串")
        for field in ("source_lang", "target_lang"):
            value = template.get(field)
            if not isinstance(value, str) or not value.strip():
                raise ToolDomainError(f"{field} 须为非空字符串（如 原文=auto / 译文=Chinese）")
        model = template.get("model")
        if model is not None and not isinstance(model, str):
            raise ToolDomainError("model 须为字符串或省略")

        now = datetime.now().isoformat(timespec="seconds")
        with self._lock:
            existing = self._load(self._path(tid)) if self._path(tid).exists() else None
            merged = {
                **(existing or {}), **template,
                "id": tid, "terms": _norm_terms(template.get("terms", (existing or {}).get("terms"))),
                "enabled": bool(template.get("enabled", (existing or {}).get("enabled", True))),
                "created_at": (existing or {}).get("created_at", now), "updated_at": now,
            }
            self._dir.mkdir(parents=True, exist_ok=True)
            tmp = self._path(tid).with_suffix(".json.tmp")
            tmp.write_text(json.dumps(merged, ensure_ascii=False, indent=2), encoding="utf-8")
            tmp.replace(self._path(tid))
        return {"id": tid, "status": "updated" if existing else "created"}

    def set_enabled(self, template_id: str, enabled: bool) -> dict:
        item = self.get(template_id)
        item["enabled"] = enabled
        self.upsert(item)
        return {"id": template_id, "enabled": enabled}

    def delete(self, template_id: str) -> dict:
        path = self._path(template_id)
        if not path.exists():
            raise ToolNotFoundError(f"翻译模版不存在: {template_id}")
        with self._lock:
            path.unlink()
        return {"id": template_id, "status": "deleted"}
