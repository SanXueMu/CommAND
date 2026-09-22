"""运行产物和 OCR 结果库的安全清理。"""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

from store.pipeline_repo import PipelineRepo


def _iter_output_strings(value: Any):
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for item in value.values():
            yield from _iter_output_strings(item)
    elif isinstance(value, (list, tuple)):
        for item in value:
            yield from _iter_output_strings(item)


class ArtifactCleanupService:
    def __init__(self, pipeline_repo: PipelineRepo, data_dir: Path | None) -> None:
        self._pipeline_repo = pipeline_repo
        self._data_dir = data_dir

    def purge_artifacts(self, handles: list[str]) -> dict[str, int]:
        empty = {"files_removed": 0, "bytes_freed": 0, "dirs_removed": 0}
        if self._data_dir is None or not handles:
            return empty
        root = self._data_dir / "outputs"
        if not root.is_dir():
            return empty
        root = root.resolve()
        files_removed = bytes_freed = dirs_removed = 0
        for handle in handles:
            target = (root / str(handle)).resolve()
            if root not in target.parents or not target.is_dir():
                continue
            for path in target.rglob("*"):
                if path.is_file():
                    try:
                        bytes_freed += path.stat().st_size
                    except OSError:
                        pass
                    files_removed += 1
            shutil.rmtree(target, ignore_errors=True)
            dirs_removed += 1
        return {"files_removed": files_removed, "bytes_freed": bytes_freed,
                "dirs_removed": dirs_removed}

    def purge_ocr_dbs(self, tree_ids: list[str]) -> dict[str, Any]:
        empty = {"dbs_removed": 0, "dbs_shared": []}
        if self._data_dir is None or not tree_ids:
            return empty
        root = self._data_dir.resolve()
        candidates: set[str] = set()
        for run_id in tree_ids:
            for output in (self._pipeline_repo.outputs_by_step(run_id) or {}).values():
                for text in _iter_output_strings(output):
                    if text.endswith(".ocr_results.db") or text.endswith(".ocr_results.db.raw.json"):
                        candidates.add(text)
        removed = 0
        shared: list[str] = []
        for raw_path in sorted(candidates):
            path = Path(raw_path)
            try:
                resolved = path.resolve()
            except OSError:
                continue
            if root != resolved and root not in resolved.parents:
                continue
            if self._pipeline_repo.db_referenced_outside(str(path), tree_ids):
                shared.append(str(path))
                continue
            try:
                resolved.unlink()
                removed += 1
            except OSError:
                pass
        return {"dbs_removed": removed, "dbs_shared": shared}
