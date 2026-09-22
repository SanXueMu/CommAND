"""运行删除与关联产物清理。"""

from __future__ import annotations

import time
from collections.abc import Callable
from typing import Any

from core.errors import TaskNotFoundError
from store.pipeline_repo import PipelineRepo
from store.task_repo import TaskRepo

DELETE_ABORT_WAIT_S = 10.0


class RunDeletionService:
    def __init__(self, pipeline_repo: PipelineRepo, task_repo: TaskRepo,
                 abort: Callable[[str], dict[str, Any]],
                 run_tree_ids: Callable[[str], list[str]],
                 purge_artifacts: Callable[[list[str]], dict[str, int]],
                 purge_ocr_dbs: Callable[[list[str]], dict[str, Any]]) -> None:
        self._pipeline_repo = pipeline_repo
        self._task_repo = task_repo
        self._abort = abort
        self._run_tree_ids = run_tree_ids
        self._purge_artifacts = purge_artifacts
        self._purge_ocr_dbs = purge_ocr_dbs

    def delete_run(self, run_id: str, purge_files: bool = True) -> dict[str, Any]:
        run = self._pipeline_repo.get_run(run_id)
        if run is None:
            raise TaskNotFoundError(f"管线运行不存在: {run_id}")
        aborted = False
        pending: list[str] = []
        if run["status"] in ("running", "paused"):
            self._abort(run_id)
            aborted = True
            deadline = time.monotonic() + DELETE_ABORT_WAIT_S
            while time.monotonic() < deadline:
                pending = self._pipeline_repo.active_task_handles(run_id)
                if not pending:
                    break
                time.sleep(0.5)
        tree_ids = self._run_tree_ids(run_id)
        handles = [t["handle"] for rid in tree_ids
                   for t in self._task_repo.list_by_pipeline_run(rid)]
        purged = self._purge_artifacts(handles) if purge_files else {
            "files_removed": 0, "bytes_freed": 0, "dirs_removed": 0}
        ocr_purged = self._purge_ocr_dbs(tree_ids) if purge_files else {
            "dbs_removed": 0, "dbs_shared": []}
        self._pipeline_repo.delete_run(run_id, drop_tasks=purge_files)

        removed_failed: list[dict] = []
        if purge_files:
            file_key = str((run.get("input") or {}).get("file") or "")
            if file_key:
                doomed = self._pipeline_repo.failed_runs_by_file(file_key, exclude_ids=tree_ids)
                for stale in doomed:
                    stale_tree = self._run_tree_ids(stale["id"])
                    stale_handles = [t["handle"] for rid in stale_tree
                                     for t in self._task_repo.list_by_pipeline_run(rid)]
                    stale_purged = self._purge_artifacts(stale_handles)
                    purged["files_removed"] += stale_purged.get("files_removed", 0)
                    purged["bytes_freed"] += stale_purged.get("bytes_freed", 0)
                    stale_ocr = self._purge_ocr_dbs(stale_tree)
                    ocr_purged["dbs_removed"] += stale_ocr.get("dbs_removed", 0)
                    ocr_purged["dbs_shared"].extend(stale_ocr.get("dbs_shared", []))
                    self._pipeline_repo.delete_run(stale["id"], drop_tasks=True)
                    removed_failed.append(stale)
        return {"id": run_id, "status": "deleted", "aborted": aborted,
                "pending_tasks": pending, "purge_files": purge_files, **purged, **ocr_purged,
                "removed_failed_attempts": removed_failed}
