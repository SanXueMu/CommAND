"""运行创建与首步派发。"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from core.errors import ToolUserError
from core.pipeline import resolve_input
from store.pipeline_repo import PipelineRepo


class RunSubmissionService:
    def __init__(self, pipeline_repo: PipelineRepo,
                 get_definition: Callable[[str], dict[str, Any]],
                 validate_key_name: Callable[[dict[str, Any]], None],
                 audit: Callable[..., None],
                 submit: Callable[..., dict[str, Any]],
                 spawn_subrun: Callable[..., None],
                 finish_run: Callable[..., None]) -> None:
        self._pipeline_repo = pipeline_repo
        self._get_definition = get_definition
        self._validate_key_name = validate_key_name
        self._audit = audit
        self._submit = submit
        self._spawn_subrun = spawn_subrun
        self._finish_run = finish_run

    def start(self, pipeline_id: str, input: dict[str, Any],
              batch_id: str | None = None,
              fallback_of: str | None = None) -> dict[str, Any]:
        self._validate_key_name(input)
        definition = self._get_definition(pipeline_id)
        run_id = self._pipeline_repo.create_run(pipeline_id, input, batch_id=batch_id,
                                                 fallback_of=fallback_of)
        self._audit(run_id, None, "created", detail={"pipeline_id": pipeline_id})
        first = definition["steps"][0]
        try:
            if "pipeline" in first:
                self._spawn_subrun(run_id, 0, first, {"input": input}, None, {})
                first_handle = None
            else:
                resolved = resolve_input(first["input"], input, None, {})
                first_handle = self._submit(definition, run_id, 0, resolved)["handle"]
        except ToolUserError as exc:
            self._finish_run(run_id, "failed", error={"kind": "user", "message": str(exc)})
            raise
        return {"run_id": run_id, "status": "running", "pipeline_id": pipeline_id,
                "first_handle": first_handle}
