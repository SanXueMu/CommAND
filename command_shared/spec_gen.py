"""LLM 识别模板三件套生成器（CommOCR 未实现、本次新增的能力模组）。

三件套 = task_spec（fields/rules/template/example/record_mode/lenient_fields）
       + postprocess（页级钩子源码）
       + view_spec（ViewSpec）
两条生成路线共用本模块的提示词与解析：
- spec.gen.textllm：非 LLM 布局分析（layout.analyze.pdf）+ 纯语言 LLM
- spec.gen.vl：多模态 LLM 直读样例图
产出必须能通过 spec.validate.ocrspec 校验（字段一致性/钩子可编译/视图可执行）。
"""
from __future__ import annotations

import json
import re

SPEC_BUILDER_SYSTEM = """你是「OCR 识别任务配置生成器」。根据用户需求（以及可选的文档布局分析或样例页图），产出 CommOCR 风格的三件套配置 JSON：
{"task_spec": {"fields": [...], "rules": "...", "template": "...", "example": "...", "record_mode": "page 或 record", "lenient_fields": [...]},
 "postprocess": [{"name": "...", "code": "def page_hook(fields, add_note): ..."}],
 "view_spec": {"name": "...", "columns": [...], "group": {...}, "aggregates": [...], "verdict": {...}, "sort": [...]}}

生成规则：
1. task_spec.fields：识别字段集，用中文短字段名；必须覆盖需求提到的全部业务要素；宁可多设字段也不遗漏
2. task_spec.template：视觉模型的角色设定一句话（人设 + 文档类型）
3. task_spec.rules：逐字段的取值规则（格式/单位/缺席写"未见"）
4. task_spec.example：单条记录的 JSON 对象示例（字段与 fields 完全一致）
5. record_mode：逐页多条明细用 page；整份文档一份信息（如合同/签单）用 record
6. lenient_fields：允许偶发缺席的字段（如备注类）
7. postprocess 钩子签名固定 def page_hook(fields, add_note):；只做确定性清洗与校验：
   金额去符号、日期归一、合计勾稽（不一致时 add_note('...待审')）；禁止网络/文件操作
8. view_spec.aggregates 算子只能用：group_key/page/page_start/page_end/page_count/first_value/last_value/count_values/join_values/evidence
9. view_spec.columns 每一列都必须由 aggregates 或 verdict.column 产生；group.mode 只能 none/value/value_run/record
10. 只输出 JSON，不要输出任何其他文字"""


def build_spec_user(requirement: str, layout_json: str | None = None) -> str:
    parts = [f"【需求描述】\n{requirement.strip()}"]
    if layout_json:
        parts.append(f"【文档布局分析（非 LLM 工具产出，仅供参考）】\n{layout_json}")
    parts.append("请生成三件套 JSON。")
    return "\n\n".join(parts)


def _strip_fence(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```[a-zA-Z0-9]*\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    return text.strip()


def parse_spec_json(raw: str) -> dict:
    """LLM 应答 → 三件套 dict（剥码块 + 提取首个 JSON 对象）。"""
    text = _strip_fence(raw)
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        start = text.find("{")
        end = text.rfind("}")
        if start < 0 or end <= start:
            raise ValueError("应答中未找到 JSON 对象")
        data = json.loads(text[start:end + 1])
    if not isinstance(data, dict) or "task_spec" not in data:
        raise ValueError("三件套缺少 task_spec")
    data.setdefault("postprocess", [])
    data.setdefault("view_spec", {})
    return data
