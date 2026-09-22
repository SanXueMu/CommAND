"""批次失败项筛选与批量重跑。"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

from store.pipeline_repo import PipelineRepo


class BatchRerunService:
    """按文件去重后批量调用整流重跑。"""

    RERUNNABLE_STATUSES = ("failed", "failed_review", "cancelled", "interrupted")

    def __init__(self, pipeline_repo: PipelineRepo,
                 rerun_run: Callable[[str], dict[str, Any]]) -> None:
        self._pipeline_repo = pipeline_repo
        self._rerun_run = rerun_run

    @staticmethod
    def dedupe_by_file(runs: list[dict[str, Any]]) -> list[dict[str, Any]]:
        seen: dict[str, dict[str, Any]] = {}
        for run in runs:
            key = str((run.get("input") or {}).get("file") or run.get("id"))
            seen.setdefault(key, run)
        return list(seen.values())

    def rerun_runs(self, run_ids: list[str]) -> dict[str, Any]:
        rerun: list[dict[str, Any]] = []
        skipped: list[dict[str, str]] = []
        fetched = {run_id: run for run_id in run_ids
                   if (run := self._pipeline_repo.get_run(run_id)) is not None}
        ordered = sorted(fetched.values(), key=lambda r: str(r.get("created_at") or ""),
                         reverse=True)
        keep = {r["id"] for r in self.dedupe_by_file(ordered)}
        for run_id in run_ids:
            run = fetched.get(run_id)
            if run is None:
                skipped.append({"run_id": run_id, "reason": "任务不存在"})
            elif str(run.get("status")) not in self.RERUNNABLE_STATUSES:
                skipped.append({"run_id": run_id,
                                "reason": f"状态不可重跑（{run.get('status')}）"})
            elif run_id not in keep:
                skipped.append({"run_id": run_id, "reason": "同一文件已有更新的失败任务，已跳过"})
            else:
                try:
                    created = self._rerun_run(run_id)
                    rerun.append({"from": run_id, "to": created["run_id"]})
                except Exception as exc:  # noqa: BLE001
                    skipped.append({"run_id": run_id,
                                    "reason": f"{type(exc).__name__}: {exc}"})
        return {"count": len(rerun), "rerun": rerun, "skipped": skipped}

    def failed_runs_of_batch(self, batch_id: str, limit: int = 500) -> list[str]:
        runs = self._pipeline_repo.list_runs(batch_id=batch_id, limit=limit)
        failed = [r for r in runs if str(r.get("status")) in self.RERUNNABLE_STATUSES]
        return [r["id"] for r in self.dedupe_by_file(failed)]

    def best_runs_of_batch(self, batch_id: str) -> list[dict[str, Any]]:
        return self._pipeline_repo.best_runs_by_batch(batch_id)

    def rerunnable_runs(self, batch_id: str | None = None, flow_ids: list[str] | None = None,
                        limit: int = 1000) -> dict[str, Any]:
        runs = self._pipeline_repo.list_runs(batch_id=batch_id, limit=limit)
        if flow_ids:
            wanted = set(flow_ids)
            runs = [r for r in runs if r.get("pipeline_id") in wanted]
        grouped: dict[str, list[dict[str, Any]]] = {}
        for run in runs:
            key = str((run.get("input") or {}).get("file") or run["id"])
            grouped.setdefault(key, []).append(run)
        files: list[dict[str, Any]] = []
        done: list[str] = []
        for key, history in grouped.items():
            if any(r.get("status") == "succeeded" for r in history):
                done.append(key)
                continue
            latest = history[0]
            if str(latest.get("status")) not in self.RERUNNABLE_STATUSES:
                continue
            files.append({"file": key, "name": Path(key).name, "run_id": latest["id"],
                          "status": latest.get("status"),
                          "error": (latest.get("error") or {}).get("message")})
        return {"count": len(files), "run_ids": [f["run_id"] for f in files],
                "files": files, "done_files": done}
