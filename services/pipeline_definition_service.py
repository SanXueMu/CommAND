"""管线定义服务：校验、注册、查询和删除管线定义。"""

from __future__ import annotations

import re
from typing import Any

from core.errors import TaskNotFoundError, ToolNotFoundError, ToolUserError
from core.pipeline import validate_when
from store.key_repo import KeyRepo
from store.pipeline_repo import PipelineRepo
from store.tool_repo import ToolRepo

PIPELINE_ID_PATTERN = re.compile(r"^[a-z][a-z0-9_]*(\.[a-z][a-z0-9_]*)+$")


class PipelineDefinitionService:
    """管线定义的生命周期服务，不参与具体 run 的执行和推进。"""

    def __init__(self, pipeline_repo: PipelineRepo, tool_repo: ToolRepo,
                 key_repo: KeyRepo | None = None) -> None:
        self._pipeline_repo = pipeline_repo
        self._tool_repo = tool_repo
        self._key_repo = key_repo

    def register(self, pipeline_id: str, name: str, steps: list[dict[str, Any]],
                 doc_md: str | None = None, input_schema: dict[str, Any] | None = None,
                 on_failure: dict[str, Any] | None = None) -> dict[str, Any]:
        if not PIPELINE_ID_PATTERN.match(pipeline_id):
            raise ToolUserError(f"管线 id 须为点分多段（小写）: {pipeline_id}")
        if not steps or not isinstance(steps, list):
            raise ToolUserError("steps 须为非空数组")

        has_sub = False
        for i, step in enumerate(steps):
            if not isinstance(step, dict) or "input" not in step:
                raise ToolUserError(f"第 {i} 步须含 input")
            has_tool, has_pipeline = "tool" in step, "pipeline" in step
            if has_tool and has_pipeline:
                raise ToolUserError(f"第 {i} 步 tool 与 pipeline 只能其一")
            if not has_tool and not has_pipeline:
                raise ToolUserError(f"第 {i} 步须含 tool 或 pipeline")
            if has_pipeline:
                has_sub = True
                sub = self._pipeline_repo.get_definition(step["pipeline"])
                if sub is None:
                    raise ToolNotFoundError(f"第 {i} 步引用的流未注册: {step['pipeline']}")
                if sub.get("type") != "flow":
                    raise ToolUserError(
                        f"第 {i} 步只能引用普通流（flow），不可嵌套工作流: {step['pipeline']}")
            elif self._tool_repo.get(step["tool"]) is None:
                raise ToolNotFoundError(f"第 {i} 步工具未注册: {step['tool']}")
            if "when" in step:
                validate_when(step["when"])
            if not isinstance(step["input"], dict):
                raise ToolUserError(f"第 {i} 步 input 须为对象")

        pipeline_type = "workflow" if has_sub else "flow"
        existing = self._pipeline_repo.get_definition(pipeline_id)
        if existing is not None and existing.get("type") != pipeline_type:
            raise ToolUserError(
                f"流类型不可变更: {pipeline_id} 已是 {existing.get('type')}，新定义为 {pipeline_type}")

        fallback_flow = (on_failure or {}).get("fallback_flow")
        if fallback_flow and str(fallback_flow) == pipeline_id:
            raise ToolUserError("on_failure.fallback_flow 不能是自身（会无限降级）")
        self._pipeline_repo.upsert_definition(
            pipeline_id, name, steps, doc_md=doc_md, ptype=pipeline_type,
            input_schema=input_schema, on_failure=on_failure)
        return {"id": pipeline_id, "name": name, "type": pipeline_type, "steps": steps,
                "on_failure": on_failure, "status": "registered"}

    def list(self) -> list[dict[str, Any]]:
        return self._pipeline_repo.list_definitions()

    def get(self, pipeline_id: str) -> dict[str, Any]:
        definition = self._pipeline_repo.get_definition(pipeline_id)
        if definition is None:
            raise TaskNotFoundError(f"管线不存在: {pipeline_id}")
        return definition

    def delete(self, pipeline_id: str) -> dict[str, Any]:
        if self._pipeline_repo.get_definition(pipeline_id) is None:
            raise TaskNotFoundError(f"管线不存在: {pipeline_id}")
        active = self._pipeline_repo.count_active_runs(pipeline_id)
        if active:
            raise ToolUserError(f"管线有 {active} 个运行中/暂停的 run，先终止再删除")
        self._pipeline_repo.delete_definition(pipeline_id)
        return {"id": pipeline_id, "status": "deleted"}

    def validate_key_name(self, input_: dict[str, Any] | None) -> None:
        """校验可选 key_name，避免任务运行到工具步才发现密钥不存在。"""
        name = (input_ or {}).get("key_name")
        if not name or not isinstance(name, str) or self._key_repo is None:
            return
        known = {str(k.get("name")) for k in self._key_repo.list()}
        if name not in known:
            raise ToolUserError(
                f"密钥不存在: {name}（请先在「设置 → APIKey管理」注册该名称的密钥，"
                f"或留空使用默认密钥）")
