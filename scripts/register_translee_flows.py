"""注册 Translee 翻译流（协议 v3：幂等 upsert + 流级 input_schema + legacy 清理）。

用法：uv run python scripts/register_translee_flows.py [--api http://127.0.0.1:8800]
重复执行安全（管线同 id 覆盖注册）。

三级概念布局：
  工具（tools/ 目录 scan 注册）——translee 十件 + 共享基建
  普通流（FLOWS）——flow.translate.xlsx / pdf / txt（线性六步，每步 SSE 可观测）
  工作流——暂无（翻译多样性在输入文件，无需模板/嵌套）

已废弃（v1 验证期产物，脚本自动 DELETE）：dev.double.reverse / text.double_reverse /
text.broken。
"""
from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request

API = "http://127.0.0.1:8800"

# 06 C3：流级 input_schema——流表单声明驱动（中文 title/description，CommWEB
# resolveForm 直读；format: file 自动挂上传组件）。
INPUT_SCHEMAS: dict[str, dict] = {
    "flow.translate.xlsx": {
        "type": "object",
        "required": ["file", "key_name", "target_lang"],
        "properties": {
            "file": {"type": "string", "format": "file", "title": "表格文件", "description": "xlsx 工作簿，可译内容将被提取并翻译"},
            "key_name": {"type": "string", "title": "密钥名称", "description": "设置页已录入的 LLM 密钥名"},
            "target_lang": {"type": "string", "title": "目标语言", "description": "如：中文 / English"},
            "model": {"type": "string", "title": "翻译模型", "description": "留空用密钥默认模型"},
        },
    },
    "flow.translate.pdf": {
        "type": "object",
        "required": ["file", "key_name", "target_lang"],
        "properties": {
            "file": {"type": "string", "format": "file", "title": "文档文件", "description": "pdf 文档，按页提取整段翻译，产出双语 docx"},
            "key_name": {"type": "string", "title": "密钥名称", "description": "设置页已录入的 LLM 密钥名"},
            "target_lang": {"type": "string", "title": "目标语言", "description": "如：中文 / English"},
            "model": {"type": "string", "title": "翻译模型", "description": "留空用密钥默认模型"},
        },
    },
    "flow.translate.txt": {
        "type": "object",
        "required": ["file", "key_name", "target_lang"],
        "properties": {
            "file": {"type": "string", "format": "file", "title": "文本文件", "description": "txt/md 纯文本，逐段翻译，产出双语 docx"},
            "key_name": {"type": "string", "title": "密钥名称", "description": "设置页已录入的 LLM 密钥名"},
            "target_lang": {"type": "string", "title": "目标语言", "description": "如：中文 / English"},
            "model": {"type": "string", "title": "翻译模型", "description": "留空用密钥默认模型"},
        },
    },
}

FLOWS: dict[str, dict] = {
    "flow.translate.xlsx": {
        "name": "表格翻译", "doc_md": "xlsx 翻译全自动流：提取→分类→归一去重→翻译→质检→回填（双语 xlsx + 对照字典）。",
        "steps": [
            {"tool": "xlsx.extract.values", "input": {"file": "{{ input.file }}"}},
            {"tool": "table.classify.columns", "input": {"units": "{{ prev.units }}"}},
            {"tool": "text.dedup.values", "input": {"segments": "{{ prev.segments }}"}},
            {"tool": "text.llm.translate", "input": {
                "segments": "{{ prev.unique }}",
                "key_name": "{{ input.key_name }}",
                "target_lang": "{{ input.target_lang }}",
                "model": "{{ input.model }}"}},
            {"tool": "text.verify.fidelity", "input": {
                "sources": "{{ step[2].output.unique }}",
                "translations": "{{ prev.translations }}"}},
            {"tool": "xlsx.backfill.dict", "input": {
                "units": "{{ step[0].output.units }}",
                "col_classes": "{{ step[1].output.col_classes }}",
                "ranges": "{{ step[1].output.ranges }}",
                "segments": "{{ step[1].output.segments }}",
                "index_map": "{{ step[2].output.index_map }}",
                "date_maps": "{{ step[2].output.date_maps }}",
                "translations": "{{ step[3].output.translations }}",
                "statuses": "{{ step[4].output.statuses }}",
                "file": "{{ input.file }}"}},
        ],
    },
    "flow.translate.pdf": {
        "name": "文档翻译", "doc_md": "pdf 翻译全自动流：按页提取→分类→归一去重→长文翻译→质检→双语 docx 渲染。",
        "steps": [
            {"tool": "pdf.extract.pages", "input": {"file": "{{ input.file }}"}},
            {"tool": "table.classify.columns", "input": {"units": "{{ prev.units }}"}},
            {"tool": "text.dedup.values", "input": {"segments": "{{ prev.segments }}"}},
            {"tool": "text.llm.translate", "input": {
                "segments": "{{ prev.unique }}",
                "key_name": "{{ input.key_name }}",
                "target_lang": "{{ input.target_lang }}",
                "model": "{{ input.model }}",
                "premium": True}},
            {"tool": "text.verify.fidelity", "input": {
                "sources": "{{ step[2].output.unique }}",
                "translations": "{{ prev.translations }}"}},
            {"tool": "docx.render.bilingual", "input": {
                "units": "{{ step[0].output.units }}",
                "ranges": "{{ step[1].output.ranges }}",
                "index_map": "{{ step[2].output.index_map }}",
                "date_maps": "{{ step[2].output.date_maps }}",
                "translations": "{{ step[3].output.translations }}",
                "statuses": "{{ step[4].output.statuses }}",
                "file": "{{ input.file }}"}},
        ],
    },
    "flow.translate.txt": {
        "name": "文本翻译", "doc_md": "txt/md 翻译全自动流：提取→分类→归一去重→翻译→质检→双语 docx 渲染。",
        "steps": [
            {"tool": "txt.extract.text", "input": {"file": "{{ input.file }}"}},
            {"tool": "table.classify.columns", "input": {"units": "{{ prev.units }}"}},
            {"tool": "text.dedup.values", "input": {"segments": "{{ prev.segments }}"}},
            {"tool": "text.llm.translate", "input": {
                "segments": "{{ prev.unique }}",
                "key_name": "{{ input.key_name }}",
                "target_lang": "{{ input.target_lang }}",
                "model": "{{ input.model }}"}},
            {"tool": "text.verify.fidelity", "input": {
                "sources": "{{ step[2].output.unique }}",
                "translations": "{{ prev.translations }}"}},
            {"tool": "docx.render.bilingual", "input": {
                "units": "{{ step[0].output.units }}",
                "ranges": "{{ step[1].output.ranges }}",
                "index_map": "{{ step[2].output.index_map }}",
                "date_maps": "{{ step[2].output.date_maps }}",
                "translations": "{{ step[3].output.translations }}",
                "statuses": "{{ step[4].output.statuses }}",
                "file": "{{ input.file }}"}},
        ],
    },
}

LEGACY_FLOWS = ["dev.double.reverse", "text.double_reverse", "text.broken"]


def api(path: str, method: str = "GET", body: dict | None = None) -> dict:
    request = urllib.request.Request(
        f"{API}{path}",
        data=json.dumps(body).encode() if body is not None else None,
        headers={"Content-Type": "application/json"}, method=method)
    with urllib.request.urlopen(request, timeout=60) as response:
        return json.loads(response.read())


def main() -> None:
    global API
    parser = argparse.ArgumentParser()
    parser.add_argument("--api", default="http://127.0.0.1:8800")
    parser.add_argument("--keep-legacy", action="store_true",
                        help="保留 v1 验证期遗留流（默认删除）")
    args = parser.parse_args()
    API = args.api.rstrip("/")

    tools = api("/api/tools/scan", method="POST")
    print(f"工具扫描响应: {json.dumps(tools, ensure_ascii=False)[:200]}")

    for legacy in LEGACY_FLOWS:
        if args.keep_legacy:
            continue
        try:
            api(f"/api/pipelines/{legacy}", method="DELETE")
            print(f"[删除] {legacy}（v1 验证期遗留）")
        except urllib.error.HTTPError as exc:
            if exc.code == 404:
                print(f"[跳过] {legacy}（不存在）")
            else:
                raise

    for pid, spec in FLOWS.items():
        body = {"id": pid, "name": spec["name"], "steps": spec["steps"],
                "doc_md": spec.get("doc_md"),
                "input_schema": INPUT_SCHEMAS.get(pid)}
        api("/api/pipelines", method="POST", body=body)
        print(f"[注册] {pid}（{spec['name']}，input_schema ✓）")

    pipelines = api("/api/pipelines").get("pipelines", [])
    print(f"当前管线 {len(pipelines)} 条: {[p['id'] for p in pipelines]}")


if __name__ == "__main__":
    main()
