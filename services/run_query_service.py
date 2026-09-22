"""运行查询、步骤快照和列表汇总。"""

from __future__ import annotations

from typing import Any

from core.errors import TaskNotFoundError
from store.pipeline_repo import PipelineRepo
from store.run_event_repo import RunEventRepo
from store.task_repo import TaskRepo


class RunQueryService:
    """只读运行视图，集中维护列表和详情的同一套摘要口径。"""

    def __init__(self, pipeline_repo: PipelineRepo, task_repo: TaskRepo,
                 run_event_repo: RunEventRepo | None) -> None:
        self._pipeline_repo = pipeline_repo
        self._task_repo = task_repo
        self._run_events = run_event_repo

    def run_snapshot(self, run_id: str) -> dict[str, Any]:
        run = self._pipeline_repo.get_run(run_id)
        if run is None:
            raise TaskNotFoundError(f"管线运行不存在: {run_id}")
        definition = self._pipeline_repo.get_definition(run["pipeline_id"])
        latest = self._pipeline_repo.latest_task_by_step(run_id)
        skipped = self._run_events.skipped_steps(run_id) if self._run_events else set()
        subruns = self._pipeline_repo.get_subruns(run_id)
        steps = []
        for n, step in enumerate(definition["steps"]):
            entry: dict[str, Any] = {
                "step_index": n, "tool": step.get("tool"), "pipeline": step.get("pipeline"),
                "latest": latest.get(n), "skipped": n in skipped,
            }
            if "pipeline" in step and n in subruns:
                sub = subruns[n]
                entry["subrun"] = {"run_id": sub["id"], "status": sub["status"],
                                   "pipeline_id": sub["pipeline_id"]}
            steps.append(entry)
        return {"run": run, "steps": steps, "summary": self._run_summary(run)}

    def list_run_events(self, run_id: str, limit: int = 200) -> list[dict[str, Any]]:
        self._require_run(run_id)
        return self._run_events.list(run_id, limit) if self._run_events else []

    def get_run_tasks(self, run_id: str) -> list[dict[str, Any]]:
        self._require_run(run_id)
        return self._task_repo.list_by_pipeline_run(run_id)

    def list_runs(self, pipeline_id: str | None = None, limit: int = 50,
                  offset: int = 0, batch_id: str | None = None) -> dict[str, Any]:
        runs = self._pipeline_repo.list_runs(pipeline_id=pipeline_id, limit=limit, offset=offset,
                                              batch_id=batch_id)
        summaries = self._summaries(runs)
        for run in runs:
            run["summary"] = summaries[run["id"]]
        return {"runs": runs, "total": self._pipeline_repo.count_runs(pipeline_id)}

    def detail_summary(self, run_id: str) -> dict[str, Any] | None:
        run = self._pipeline_repo.get_run(run_id)
        return self._run_summary(run) if run is not None else None

    def _run_summary(self, run: dict[str, Any]) -> dict[str, Any]:
        return self._summaries([run])[run["id"]]

    def _summaries(self, runs: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
        run_ids = [r["id"] for r in runs]
        statuses = self._pipeline_repo.light_step_statuses(run_ids)
        outputs = self._pipeline_repo.light_step_outputs(run_ids)
        totals = self._pipeline_repo.steps_total_by_pipeline(
            [r.get("pipeline_id") or "" for r in runs])
        skipped = (self._run_events.skipped_steps_bulk(run_ids)
                   if self._run_events is not None else {})
        titles = {
            d["id"]: {k: v.get("title") or k
                      for k, v in (d.get("input_schema") or {}).get("properties", {}).items()}
            for d in self._pipeline_repo.list_definitions()
        }
        progress = (self._run_events.latest_progress_bulk(
            [r["id"] for r in runs if r.get("status") in ("running", "queued")])
                    if self._run_events is not None else {})
        result: dict[str, dict[str, Any]] = {}
        for run in runs:
            summary = self._assemble_summary(
                statuses.get(run["id"], {}), outputs.get(run["id"], {}),
                totals.get(run.get("pipeline_id") or ""), skipped.get(run["id"], []),
                titles.get(run.get("pipeline_id") or ""))
            if progress.get(run["id"]):
                summary["latest_note"] = progress[run["id"]]
            result[run["id"]] = summary
        return result

    @staticmethod
    def _assemble_summary(step_statuses: dict[int, str], step_outputs: dict[int, dict[str, Any]],
                           steps_total: int | None, skipped: list[dict[str, Any]] | None = None,
                           param_titles: dict[str, str] | None = None) -> dict[str, Any]:
        artifacts: list[dict[str, Any]] = []
        translate: dict[str, Any] | None = None
        verify: dict[str, Any] | None = None
        for output in step_outputs.values():
            if not isinstance(output, dict):
                continue
            if output.get("path"):
                artifacts.append({"name": output.get("name"), "path": output.get("path")})
            if output.get("layered_file"):
                artifacts.append({"name": output.get("layered_name") or "可搜索.pdf",
                                  "path": output.get("layered_file")})
            if output.get("usage_by_model") is not None or output.get("usage") is not None:
                translate = output
            if output.get("statuses_len") is not None or output.get("review_count") is not None:
                verify = output
        summary: dict[str, Any] = {
            "artifacts": artifacts, "steps_total": steps_total,
            "steps_done": sum(1 for s in step_statuses.values() if s in ("succeeded", "skipped"))
                          + len(skipped or []),
        }
        if translate is not None or verify is not None:
            counts = verify or translate or {}
            statuses_len = counts.get("statuses_len")
            review = counts.get("review_count")
            if review is None:
                review = (translate or {}).get("review_count") or 0
            summary.update({"usage": (translate or {}).get("usage"),
                            "usage_by_model": (translate or {}).get("usage_by_model"),
                            "calls": (translate or {}).get("calls"),
                            "cache_hits": (translate or {}).get("cache_hits"),
                            "review_count": review,
                            "ok_count": max(statuses_len - review, 0)
                            if statuses_len is not None else None})
        failed_pages = sum(o.get("failed_pages") or 0 for o in step_outputs.values()
                           if isinstance(o, dict))
        if failed_pages:
            summary["failed_pages"] = failed_pages
        review_notes = [o.get("review_notes_count") for o in step_outputs.values()
                        if isinstance(o, dict) and o.get("review_notes_count")]
        if review_notes:
            summary["review_notes_count"] = sum(review_notes)
        records = [o.get("records_count") for o in step_outputs.values()
                   if isinstance(o, dict) and o.get("records_count") is not None]
        if records:
            summary["records_count"] = records[-1]
        if skipped:
            summary["steps_skipped"] = [
                {"step_index": sk.get("step_index"),
                 "reason": RunQueryService._skip_reason(sk.get("when") or {}, param_titles or {})}
                for sk in skipped]
        return summary

    @staticmethod
    def _skip_reason(when: dict[str, Any], titles: dict[str, str]) -> str:
        parts: list[str] = []
        for key, expected in when.items():
            name = titles.get(key[6:]) if key.startswith("input.") else None
            name = name or key
            if expected == "@exists":
                parts.append(f"「{name}」无值（该步需要它）")
            elif expected is True:
                parts.append(f"未开启「{name}」")
            elif expected is False:
                parts.append(f"「{name}」需关闭")
            else:
                parts.append(f"「{name}」需为 {expected}")
        return "；".join(parts) or "条件未满足"

    def _require_run(self, run_id: str) -> None:
        if self._pipeline_repo.get_run(run_id) is None:
            raise TaskNotFoundError(f"管线运行不存在: {run_id}")
