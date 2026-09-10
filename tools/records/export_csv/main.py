"""视图行导出 CSV（utf-8-sig，Excel 直开）：columns/rows(+splits) → 文件。

导出服务端化裁定：工具落盘 DATA_DIR/outputs/exports/，前端经下载端点取。
"""
from __future__ import annotations

import csv
import re
from pathlib import Path

from core.errors import ToolDomainError


def _safe_name(name: str, fallback: str) -> str:
    cleaned = re.sub(r'[\\/:*?"<>|]+', "_", (name or "").strip())
    return cleaned or fallback


def run(input: dict, ctx, emit) -> dict:
    rows = input.get("rows")
    columns = input.get("columns") or []
    if rows is None:
        raise ToolDomainError("rows 必填（records.view.query 产出）")

    data_dir = Path(__import__("os").environ.get("COMMAND_DATA_DIR", "data"))
    out_dir = data_dir / "outputs" / "exports"
    out_dir.mkdir(parents=True, exist_ok=True)
    target = out_dir / f"{_safe_name(input.get('name'), '视图导出')}.csv"

    with target.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.writer(handle)
        writer.writerow(columns)
        for row in rows:
            writer.writerow([row.get(c, "") if isinstance(row, dict) else row for c in columns])

    emit({"type": "progress", "phase": "export",
          "message": f"导出 {len(rows)} 行 → {target.name}"})
    return {"file": str(target), "rows_count": len(rows), "columns": columns}
