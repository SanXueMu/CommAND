"""识别规则模版库（E1）：data/ocr/templates/<id>.json 三件套模版的存取与生命周期。

模版结构（category 字段为 E2 when 断言的数据基础）：
  {id, name, category, enabled, prompt_template, fields, rules, example,
   hooks, record_mode, lenient, view_spec, created_at, updated_at}
"""
from __future__ import annotations

import json
import os
import re
import threading
from pathlib import Path

from core.errors import ToolDomainError, ToolNotFoundError

_ID_PATTERN = re.compile(r"^[a-z][a-z0-9_.]{2,63}$")
CATEGORIES = ("invoice", "contract", "audit", "custom")


def templates_dir(data_dir: str | None = None) -> Path:
    root = Path(data_dir or os.environ.get("COMMAND_DATA_DIR", "data"))
    return root / "ocr" / "templates"


def render_prompt(template_text: str, fields: list[str], rules=None, example=None) -> str:
    """CommOCR 同款逐占位符替换（str.format 会被模板内 JSON 花括号炸掉）。"""
    prompt = template_text
    replacements = {
        "{field_count}": str(len(fields)),
        "{fields}": "、".join(fields),
        "{rules}": "\n".join(rules) if isinstance(rules, list) else (rules or ""),
        "{example}": json.dumps(example, ensure_ascii=False, indent=2) if example else "",
    }
    for placeholder, value in replacements.items():
        prompt = prompt.replace(placeholder, value)
    return prompt


class TemplateStore:
    """模版文件三件套的单一存取点（进程内锁 + 原子替换写）。"""

    def __init__(self, data_dir: str | None = None) -> None:
        self._dir = templates_dir(data_dir)
        self._lock = threading.Lock()

    def _path(self, template_id: str) -> Path:
        return self._dir / f"{template_id}.json"

    def _load(self, path: Path) -> dict:
        return json.loads(path.read_text(encoding="utf-8"))

    def list(self, enabled: bool | None = None, category: str | None = None,
             keyword: str | None = None) -> list[dict]:
        with self._lock:
            items = []
            if not self._dir.exists():
                return items
            for path in sorted(self._dir.glob("*.json")):
                try:
                    item = self._load(path)
                except (json.JSONDecodeError, OSError):
                    continue  # 损坏条目跳过不炸列表
                if enabled is not None and bool(item.get("enabled")) is not enabled:
                    continue
                if category and item.get("category") != category:
                    continue
                if keyword and keyword not in f"{item.get('id','')} {item.get('name','')}":
                    continue
                items.append({
                    "id": item.get("id"), "name": item.get("name"),
                    "category": item.get("category"), "enabled": bool(item.get("enabled")),
                    "fields_count": len(item.get("fields") or []),
                    "hooks_count": len(item.get("hooks") or []),
                    "record_mode": item.get("record_mode"), "lenient": bool(item.get("lenient")),
                    "updated_at": item.get("updated_at"),
                })
            return items

    def get(self, template_id: str) -> dict:
        path = self._path(template_id)
        if not path.exists():
            raise ToolNotFoundError(f"识别模版不存在: {template_id}")
        with self._lock:
            return self._load(path)

    def upsert(self, template: dict) -> dict:
        tid = template.get("id") or ""
        if not _ID_PATTERN.match(tid):
            raise ToolDomainError(f"模版 id 须匹配 {_ID_PATTERN.pattern}: {tid}")
        if template.get("category") not in CATEGORIES:
            raise ToolDomainError(f"category 须为 {CATEGORIES} 之一: {template.get('category')}")
        fields = template.get("fields")
        if not isinstance(fields, list) or not fields or not all(isinstance(f, str) and f for f in fields):
            raise ToolDomainError("fields 须为非空字符串数组")
        prompt_text = template.get("prompt_template")
        if not isinstance(prompt_text, str) or not prompt_text.strip():
            raise ToolDomainError("prompt_template 须为非空字符串")  # {fields} 占位可选（合同类固定提示词无占位）
        hooks = template.get("hooks") or []
        if not isinstance(hooks, list) or not all(isinstance(h, dict) and h.get("code") for h in hooks):
            raise ToolDomainError("hooks 须为含 code 的对象数组")
        record_mode = template.get("record_mode")
        if record_mode not in (None, "page", "record"):
            raise ToolDomainError(f"record_mode 只能 page/record: {record_mode}")
        input_schema = template.get("input_schema")
        if input_schema is not None and not isinstance(input_schema, dict):
            raise ToolDomainError("input_schema 须为对象（模版增量输入声明，级联表单数据源）")

        from datetime import datetime
        now = datetime.now().isoformat(timespec="seconds")
        existing = None
        with self._lock:
            if self._path(tid).exists():
                existing = self._load(self._path(tid))
            merged = {**(existing or {}), **template,
                      "id": tid, "enabled": bool(template.get("enabled", (existing or {}).get("enabled", True))),
                      "created_at": (existing or {}).get("created_at", now),
                      "updated_at": now}
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
            raise ToolNotFoundError(f"识别模版不存在: {template_id}")
        with self._lock:
            path.unlink()
        return {"id": template_id, "status": "deleted"}
