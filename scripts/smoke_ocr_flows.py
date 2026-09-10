"""CommOCR 移植管线冒烟（本地 mock LLM）：识别/视图导出/模板生成三族。

前置：server 已起（--api）、scripts/mock_llm.py 已起、mock key 已注册。
用法：uv run python scripts/smoke_ocr_flows.py --api http://127.0.0.1:8800
"""
from __future__ import annotations

import argparse
import json
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

import fitz
from PIL import Image

API = "http://127.0.0.1:8800"
VIEW_SPEC = {"name": "冒烟视图", "columns": ["标题", "金额"], "group": {"mode": "record"},
             "aggregates": [{"column": "标题", "op": "first_value", "field": "标题"},
                            {"column": "金额", "op": "join_values", "field": "金额"}]}


def api(path: str, method: str = "GET", body: dict | None = None) -> dict:
    request = urllib.request.Request(
        f"{API}{path}",
        data=json.dumps(body).encode() if body is not None else None,
        headers={"Content-Type": "application/json"}, method=method)
    with urllib.request.urlopen(request, timeout=300) as response:
        return json.loads(response.read())


def make_sample(tmp: Path) -> dict:
    pdf = tmp / "决算样例.pdf"
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 90), "项目送审金额表", fontsize=16, fontname="china-s")
    for row, text in enumerate(["甲项目 100.00", "乙项目 50.00"]):
        page.insert_text((72, 140 + row * 24), text, fontsize=11, fontname="china-s")
    doc.save(pdf)
    doc.close()
    image = tmp / "样例图.png"
    Image.new("RGB", (600, 400), "white").save(image)
    return {"pdf": pdf, "image": image}


def run_flow(flow_id: str, payload: dict) -> dict:
    started = time.time()
    run = api(f"/api/pipelines/{flow_id}/run", method="POST", body={"input": payload})
    run_id = run["run_id"]
    for _ in range(150):
        detail = api(f"/api/pipeline-runs/{run_id}")
        status = detail["run"].get("status")
        if status in ("succeeded", "failed", "failed_review", "cancelled"):
            elapsed = time.time() - started
            print(f"  [{'OK ' if status == 'succeeded' else 'FAIL'}] {flow_id}  {elapsed:.1f}s")
            if status != "succeeded":
                for task in detail.get("tasks", []):
                    if task.get("status") == "failed":
                        print("    ", task.get("tool_id"), "→",
                              str(task.get("error"))[:300])
            return detail
        time.sleep(2)
    raise RuntimeError(f"{flow_id} 超时")


def summarize(tag: str, detail: dict) -> None:
    last = (detail.get("tasks") or [{}])[-1]
    output = last.get("output") or {}
    keep = {k: output[k] for k in list(output)[:6]}
    print(f"    {tag}: {json.dumps(keep, ensure_ascii=False)[:300]}")


def main() -> None:
    global API
    parser = argparse.ArgumentParser()
    parser.add_argument("--api", default="http://127.0.0.1:8800")
    args = parser.parse_args()
    API = args.api.rstrip("/")
    tmp = Path(tempfile.mkdtemp(prefix="ocr_smoke_"))
    samples = make_sample(tmp)
    key = "mock"
    print(f"样例目录: {tmp}")

    print("== 1. 通用识别 flow.ocr.recognize")
    detail = run_flow("flow.ocr.recognize", {
        "file": str(samples["pdf"]), "output_db": str(tmp / "样例.ocrdb"),
        "key_name": key, "fields": ["标题", "金额"], "prompt": "识别表格",
        "record_mode": "page", "model": "", "rules": "", "example": "",
        "postprocess": None, "skip_text_pdf": False})
    summarize("vl", detail)

    print("== 2. 模板识别 flow.ocr.audit（固化提示词+钩子）")
    detail = run_flow("flow.ocr.audit", {
        "file": str(samples["pdf"]), "output_db": str(tmp / "审定表.ocrdb"),
        "key_name": key, "model": "", "skip_text_pdf": False})
    summarize("vl", detail)

    print("== 2b. 跨域批翻 flow.ocr.translate（vl→单元→分类→去重→翻译→回填）")
    detail = run_flow("flow.ocr.translate", {
        "file": str(samples["pdf"]), "output_db": str(tmp / "翻译.ocrdb"),
        "key_name": key, "fields": ["标题", "金额"], "prompt": "识别表格",
        "record_mode": "page", "skip_text_pdf": False,
        "translate_key_name": key, "target_lang": "中文"})
    summarize("backfill", detail)

    print("== 3. 视图导出 flow.ocrdb.view（读上一步库→视图→xlsx）")
    detail = run_flow("flow.ocrdb.view", {
        "db": str(tmp / "样例.ocrdb"), "view_spec": VIEW_SPEC, "name": "冒烟视图导出"})
    summarize("xlsx", detail)

    print("== 4. 模板生成 flow.specgen.pdf / flow.specgen.img")
    detail = run_flow("flow.specgen.pdf", {
        "file": str(samples["pdf"]), "requirement": "提取项目名称与金额",
        "key_name": key, "model": ""})
    summarize("validate", detail)
    detail = run_flow("flow.specgen.img", {
        "file": str(samples["image"]), "requirement": "提取标题与金额",
        "key_name": key, "model": ""})
    summarize("validate", detail)

    print("冒烟完成 ✓")


if __name__ == "__main__":
    sys.exit(main())
