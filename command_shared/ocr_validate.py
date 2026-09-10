"""VL 输出解析校验 + 页级钩子（CommOCR validation.py + hooks.py 移植）。

记录协议：VL 应答 JSON 数组，每项键集 == fields（严格模式完全一致才收）。
钩子：TaskSpec.postprocess [{name, code}]，code 定义 page_hook(fields, add_note) -> dict|None。
"""
from __future__ import annotations

import hashlib
import json
import math
import re

_INTERNAL_KEYS = {"页码", "行号"}


class HookError(Exception):
    """钩子编译或运行失败。"""


def _strip_code_fence(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```[a-zA-Z0-9]*\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    return text.strip()


def _collect_json_values(text: str) -> list[str]:
    """从应答文本中抠出所有 JSON 数组/对象片段（模型偶发包裹文字时兜底）。"""
    values = []
    for pattern in (r"\[.*\]", r"\{.*\}"):
        for match in re.findall(pattern, text, re.DOTALL):
            values.append(match)
        if values:
            return values
    return []


def parse_records(raw: str, fields: list[str], lenient_fields: list[str] | None = None) -> list[dict]:
    """解析 VL 应答 → 记录列表（每条键集与 fields 一致）。

    严格：键集完全一致才收；宽松：允许缺 lenient_fields 内的键（补空串）。
    返回 [] 表示本页无记录。解析失败抛 ValueError。
    """
    text = _strip_code_fence(raw)
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        data = None
        for candidate in _collect_json_values(text):
            try:
                data = json.loads(candidate)
                break
            except json.JSONDecodeError:
                continue
        if data is None:
            raise ValueError("应答不是合法 JSON")

    if isinstance(data, dict):
        data = [data]
    if not isinstance(data, list):
        raise ValueError("应答 JSON 不是数组")

    lenient = set(lenient_fields or [])
    records: list[dict] = []
    for item in data:
        if not isinstance(item, dict):
            continue
        keys = set(item.keys())
        if keys == set(fields):
            records.append({k: item[k] for k in fields})
        elif keys <= set(fields) and lenient >= (set(fields) - keys):
            records.append({k: item.get(k, "") for k in fields})
    return records


_HOOK_CACHE: dict = {}


def compile_page_hook(name: str, code: str):
    """编译钩子源码 → transform_page 可调用（CommOCR 同款协议，sha256 缓存）。

    约定：code 必须定义 transform_page(records, ctx) -> records；
    命名空间预置 re/json/math；ctx={"page", "fields", "review"}。
    """
    digest = hashlib.sha256(code.encode("utf-8")).hexdigest()
    cached = _HOOK_CACHE.get(digest)
    if cached is not None:
        return cached
    namespace: dict = {
        "__name__": f"postprocess_{digest[:8]}",
        "re": re, "json": json, "math": math,
    }
    try:
        exec(compile(code, f"<postprocess:{name or digest[:8]}>", "exec"), namespace)  # noqa: S102 - 用户钩子按设计可执行
    except SyntaxError as exc:
        raise HookError(f"钩子[{name}]源码语法错误: {exc}") from exc
    except Exception as exc:
        raise HookError(f"钩子 {name} 编译失败: {exc}") from exc
    transform = namespace.get("transform_page")
    if not callable(transform):
        raise HookError(f"钩子[{name}]必须定义 transform_page(records, ctx) 函数")
    _HOOK_CACHE[digest] = transform
    return transform


def run_page_hooks(hooks: list[dict], records: list[dict], page_number: int,
                   fields: list[str], review=None) -> list[dict]:
    """按声明顺序执行页级钩子链；返回处理后的记录列表。

    hooks 元素支持 {"name","code"}（现场编译，带缓存）或 {"fn"}（已编译）。
    """
    for hook in hooks:
        transform = hook.get("fn") or compile_page_hook(hook.get("name", "hook"),
                                                        hook.get("code", ""))
        ctx = {"page": page_number, "fields": list(fields), "review": review}
        try:
            result = transform(records, ctx)
        except HookError:
            raise
        except Exception as exc:
            raise HookError(f"钩子[{hook.get('name', 'hook')}]执行失败: {exc}") from exc
        if not isinstance(result, list) or not all(isinstance(r, dict) for r in result):
            raise HookError(f"钩子[{hook.get('name', 'hook')}]必须返回记录列表（list[dict]）")
        records = result
    return records
