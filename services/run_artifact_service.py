"""运行产物查询与收集。"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

from core.errors import TaskNotFoundError
from store.pipeline_repo import PipelineRepo
from store.task_repo import TaskRepo

ARTIFACT_SUFFIXES = {".pdf", ".docx", ".xlsx", ".xls", ".txt", ".md", ".csv", ".zip"}


class RunArtifactService:
    def __init__(self, pipeline_repo: PipelineRepo, task_repo: TaskRepo,
                 data_dir: Path | None, run_tree_ids: Callable[[str], list[str]],
                 list_runs: Callable[..., dict[str, Any]]) -> None:
        self._pipeline_repo = pipeline_repo
        self._task_repo = task_repo
        self._data_dir = data_dir
        self._run_tree_ids = run_tree_ids
        self._list_runs = list_runs

    def collect(self, run_id: str, scope: str = "final") -> list[dict[str, Any]]:
        if self._pipeline_repo.get_run(run_id) is None:
            raise TaskNotFoundError(f"管线运行不存在: {run_id}")
        outputs = self._pipeline_repo.outputs_by_step(run_id)
        if scope == "final" and outputs:
            outputs = {max(outputs): outputs[max(outputs)]}
        root = self._data_dir.resolve() if self._data_dir is not None else None
        found: list[dict[str, Any]] = []
        seen: set[str] = set()
        for step in sorted(outputs):
            out = outputs[step]
            if not isinstance(out, dict):
                continue
            for key, value in out.items():
                if key == "name" or key.endswith("_name"):
                    continue
                if (not isinstance(value, str) or not value
                        or Path(value).suffix.lower() not in ARTIFACT_SUFFIXES):
                    continue
                try:
                    candidate = Path(value)
                    if not candidate.is_absolute() or not candidate.is_file():
                        continue
                    resolved = candidate.resolve()
                except OSError:
                    continue
                if root is not None and root not in resolved.parents:
                    continue
                if str(resolved) in seen:
                    continue
                seen.add(str(resolved))
                base = key[:-5] if key.endswith("_file") else key
                name = out.get(f"{base}_name") or out.get("name") or resolved.name
                found.append({"step": step, "key": key, "name": str(name),
                              "path": str(resolved), "size": resolved.stat().st_size})
        return found

    def usage(self, run_id: str) -> dict[str, int]:
        empty = {"files": 0, "bytes": 0, "dirs": 0}
        if self._data_dir is None:
            return empty
        root = (self._data_dir / "outputs").resolve()
        files = bytes_found = dirs = 0
        for rid in self._run_tree_ids(run_id):
            for task in self._task_repo.list_by_pipeline_run(rid):
                target = (root / str(task["handle"])).resolve()
                if root not in target.parents or not target.is_dir():
                    continue
                dirs += 1
                for path in target.rglob("*"):
                    if path.is_file():
                        files += 1
                        try:
                            bytes_found += path.stat().st_size
                        except OSError:
                            pass
        return {"files": files, "bytes": bytes_found, "dirs": dirs}

    def usage_report(self, run_ids: list[str] | None = None, pipeline_id: str | None = None,
                     limit: int = 50) -> dict[str, Any]:
        targets = (list(dict.fromkeys(str(r) for r in run_ids)) if run_ids else
                   [r["id"] for r in self._list_runs(pipeline_id=pipeline_id, limit=limit)["runs"]])
        rows: list[dict[str, Any]] = []
        missing: list[str] = []
        total = {"files": 0, "bytes": 0, "dirs": 0}
        for run_id in targets:
            run = self._pipeline_repo.get_run(run_id)
            if run is None:
                missing.append(run_id)
                continue
            usage = self.usage(run_id)
            rows.append({"run_id": run_id, "pipeline_id": run["pipeline_id"],
                         "status": run["status"], "created_at": str(run.get("created_at") or ""),
                         **usage})
            for key in total:
                total[key] += usage[key]
        return {"runs": rows, "total": total, "missing": missing}
