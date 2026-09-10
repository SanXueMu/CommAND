"""L5 协议：Tool Manifest 与调用信封的模型与校验（语义对齐 MCP 2026-07-28）。

Manifest 即户口：tool.toml 声明即工具的全部；schema 即契约，提交时即校验。
"""

import json
import re
import tomllib
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

ID_PATTERN = re.compile(r"^[a-z][a-z0-9_]*\.[a-z][a-z0-9_]*\.[a-z][a-z0-9_]*$")
TYPE_LABEL_PATTERN = re.compile(r"^[a-z][a-z0-9_]*(\.[a-z][a-z0-9_]*)*(\[\])?$")


class ToolSection(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    name: str
    version: str
    description: str = ""
    tags: list[str] = Field(default_factory=list)

    @field_validator("id")
    @classmethod
    def _validate_id(cls, value: str) -> str:
        if not ID_PATTERN.match(value):
            raise ValueError(f"tool.id 必须为点分三段 <域>.<对象>.<动作>（小写）: {value}")
        return value


class IoSection(BaseModel):
    model_config = ConfigDict(extra="forbid")

    input_schema: dict[str, Any]
    output_schema: dict[str, Any]
    input_types: list[str]
    output_types: list[str]

    @field_validator("input_schema", "output_schema")
    @classmethod
    def _validate_schema(cls, value: dict[str, Any]) -> dict[str, Any]:
        if "type" not in value:
            raise ValueError("schema 必须含 type 字段（JSON Schema 2020-12）")
        return value

    @field_validator("input_types", "output_types")
    @classmethod
    def _validate_types(cls, value: list[str]) -> list[str]:
        for item in value:
            if not TYPE_LABEL_PATTERN.match(item):
                raise ValueError(f"类型标签须为 <域>.<形态>（可带 [] 数组后缀）: {item}")
        return value


class RuntimeSection(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: Literal["inproc", "subprocess", "http"]
    entry: str
    sync: bool = False


class ResourcesSection(BaseModel):
    model_config = ConfigDict(extra="forbid")

    timeout_s: int = Field(gt=0)
    concurrency: int = Field(gt=0)
    max_attempts: int = Field(default=1, ge=1)


class ToolManifest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tool: ToolSection
    io: IoSection
    runtime: RuntimeSection
    resources: ResourcesSection
    # [ui] 呈现声明：宽松 dict，骨架只透传不解释（CommWEB ToolFace 消费）
    ui: dict[str, Any] = Field(default_factory=dict)

    @classmethod
    def from_toml(cls, path: Path) -> "ToolManifest":
        raw = tomllib.loads(Path(path).read_text(encoding="utf-8"))
        io = raw.get("io", {})
        for key in ("input_schema", "output_schema"):
            if isinstance(io.get(key), str):
                io[key] = json.loads((Path(path).parent / io[key]).read_text(encoding="utf-8"))
        return cls.model_validate(raw)


class Envelope(BaseModel):
    """调用信封：自包含（tool id + input），无会话无握手。"""

    tool: str
    input: dict[str, Any] = Field(default_factory=dict)


def validate_payload(schema: dict[str, Any], payload: Any, *, kind: str) -> None:
    """按 JSON Schema 2020-12 校验载荷；不过即用户错误，提交时拦截。"""
    from jsonschema import Draft202012Validator

    from core.errors import ToolUserError

    validator = Draft202012Validator(schema)
    errors = sorted(validator.iter_errors(payload), key=lambda e: e.json_path)
    if errors:
        first = errors[0]
        raise ToolUserError(f"{kind} 不符合 schema（{first.json_path}）: {first.message}")
