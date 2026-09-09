"""注册 Translee v2 流水线（幂等）：扫描工具 → 注册 3 条 flow 管线。

用法：uv run python scripts/register_translee_flows.py [--api http://127.0.0.1:8000]
重复执行安全：管线同 id 覆盖注册（server 端 upsert 语义）。
"""
from __future__ import annotations

import argparse
import json
import sys
import urllib.request

FLOWS = {
    "flow.translate.xlsx": {
        "name": "xlsx 翻译全自动流（提取→分类→归一去重→翻译→质检→回填）",
        "steps": [
            {"tool": "xlsx.extract.values", "input": {"file": "{{ input.file }}"}},
            {"tool": "table.classify.columns", "input": {"units": "{{ prev.units }}"}},
            {"tool": "text.dedup.values", "input": {"segments": "{{ prev.segments }}"}},
            {"tool": "text.llm.translate", "input": {
                "segments": "{{ prev.unique }}",
                "key_name": "{{ input.key_name }}",
                "target_lang": "{{ input.target_lang }}",
            }},
            {"tool": "text.verify.fidelity", "input": {
                "sources": "{{ step[2].output.unique }}",
                "translations": "{{ prev.translations }}",
            }},
            {"tool": "xlsx.backfill.dict", "input": {
                "units": "{{ step[0].output.units }}",
                "col_classes": "{{ step[1].output.col_classes }}",
                "ranges": "{{ step[1].output.ranges }}",
                "segments": "{{ step[1].output.segments }}",
                "index_map": "{{ step[2].output.index_map }}",
                "date_maps": "{{ step[2].output.date_maps }}",
                "translations": "{{ step[3].output.translations }}",
                "statuses": "{{ step[4].output.statuses }}",
                "file": "{{ input.file }}",
            }},
        ],
    },
    "flow.translate.pdf": {
        "name": "pdf 翻译全自动流（按页提取→分类→归一去重→长文翻译→质检→docx 渲染）",
        "steps": [
            {"tool": "pdf.extract.pages", "input": {"file": "{{ input.file }}"}},
            {"tool": "table.classify.columns", "input": {"units": "{{ prev.units }}"}},
            {"tool": "text.dedup.values", "input": {"segments": "{{ prev.segments }}"}},
            {"tool": "text.llm.translate", "input": {
                "segments": "{{ prev.unique }}",
                "key_name": "{{ input.key_name }}",
                "target_lang": "{{ input.target_lang }}",
                "premium": True,
            }},
            {"tool": "text.verify.fidelity", "input": {
                "sources": "{{ step[2].output.unique }}",
                "translations": "{{ prev.translations }}",
            }},
            {"tool": "docx.render.bilingual", "input": {
                "units": "{{ step[0].output.units }}",
                "ranges": "{{ step[1].output.ranges }}",
                "index_map": "{{ step[2].output.index_map }}",
                "date_maps": "{{ step[2].output.date_maps }}",
                "translations": "{{ step[3].output.translations }}",
                "statuses": "{{ step[4].output.statuses }}",
                "file": "{{ input.file }}",
            }},
        ],
    },
    "flow.translate.txt": {
        "name": "txt/md 翻译全自动流（提取→分类→归一去重→翻译→质检→docx 渲染）",
        "steps": [
            {"tool": "txt.extract.text", "input": {"file": "{{ input.file }}"}},
            {"tool": "table.classify.columns", "input": {"units": "{{ prev.units }}"}},
            {"tool": "text.dedup.values", "input": {"segments": "{{ prev.segments }}"}},
            {"tool": "text.llm.translate", "input": {
                "segments": "{{ prev.unique }}",
                "key_name": "{{ input.key_name }}",
                "target_lang": "{{ input.target_lang }}",
            }},
            {"tool": "text.verify.fidelity", "input": {
                "sources": "{{ step[2].output.unique }}",
                "translations": "{{ prev.translations }}",
            }},
            {"tool": "docx.render.bilingual", "input": {
                "units": "{{ step[0].output.units }}",
                "ranges": "{{ step[1].output.ranges }}",
                "index_map": "{{ step[2].output.index_map }}",
                "date_maps": "{{ step[2].output.date_maps }}",
                "translations": "{{ step[3].output.translations }}",
                "statuses": "{{ step[4].output.statuses }}",
                "file": "{{ input.file }}",
            }},
        ],
    },
}


def call(api: str, method: str, path: str, body: dict | None = None) -> dict:
    req = urllib.request.Request(
        f"{api}{path}",
        data=json.dumps(body).encode() if body is not None else None,
        method=method,
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read())


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--api", default="http://127.0.0.1:8000")
    args = ap.parse_args()

    scan = call(args.api, "POST", "/api/tools/scan")
    print(f"工具扫描: {json.dumps(scan, ensure_ascii=False)[:300]}")

    for pid, spec in FLOWS.items():
        call(args.api, "POST", "/api/pipelines", {"id": pid, "name": spec["name"], "steps": spec["steps"]})
        print(f"管线已注册: {pid}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
