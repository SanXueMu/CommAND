"""批次清单（`data/batches/<batch_id>.json`）：上传即固化「相对路径 → 文件」的目录树。

导出按它还原**原目录结构**（不依赖 run 是否存在/成功）；替换原件时同步更新条目，
保证清单始终等于「当前批次里真实存在的文件」。上传端点（files_router）与
任务级替换原件（pipelines_router）共用本模块。
"""

from __future__ import annotations

import json
import time
from datetime import date
from pathlib import Path
from typing import Any

MANIFEST_TTL_DAYS = 30


def manifest_dir(data_dir: str | Path) -> Path:
    target = Path(data_dir) / "batches"
    target.mkdir(parents=True, exist_ok=True)
    return target


def prune(data_dir: str | Path, ttl_days: int = MANIFEST_TTL_DAYS) -> None:
    """清理过期清单，防止无限增长。"""
    cutoff = time.time() - ttl_days * 86400
    for old in manifest_dir(data_dir).glob("*.json"):
        try:
            if old.stat().st_mtime < cutoff:
                old.unlink()
        except OSError:
            pass


def path_of(data_dir: str | Path, batch_id: str) -> Path:
    return manifest_dir(data_dir) / f"{batch_id}.json"


def write(data_dir: str | Path, batch_id: str, root: str, batch_dir: str | Path,
          files: list[dict], skip_exts: set[str] | None = None,
          source: str | None = None) -> None:
    prune(data_dir)
    payload = {
        "batch_id": batch_id, "root": root, "dir": str(batch_dir),
        "created_at": date.today().isoformat(),
        "skip_exts": sorted(skip_exts or ()), "files": files,
        "source": source or "unknown",  # AF4：上传来源（translate/ocr 工作台）
    }
    path_of(data_dir, batch_id).write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def load(data_dir: str | Path, batch_id: str) -> dict[str, Any] | None:
    path = path_of(data_dir, batch_id)
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def replace_file(data_dir: str | Path, batch_id: str, old_path: str,
                 entry: dict) -> bool:
    """把清单里 `old_path` 的条目换成新文件（替换原件后调用）。返回是否命中。"""
    manifest = load(data_dir, batch_id)
    if manifest is None:
        return False
    hit = False
    for item in manifest.get("files") or []:
        if str(item.get("path")) == old_path:
            item.update(entry)
            hit = True
            break
    if hit:
        path_of(data_dir, batch_id).write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return hit
