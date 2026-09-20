"""用模型原文留痕（<结果库>.raw.json）修复被旧主键吞行的结果库（AE 免费恢复）。

背景（2026-09-20 AE 定案）：records 旧主键 (file_hash, source_path, row_number) 无页内序，
一页多条分录 INSERT OR IGNORE 只留第一条；AC 的 raw.json 存有模型逐页原文。
本脚本对每页原文重新 parse_records + 模版钩子 → 页级替换写回，零模型调用、不重复计费。

用法（command-api 容器内）：
    python scripts/heal_ocr_db_from_raw.py --db data/ocr/xxx.ocr_results.db \
        [--template tpl.invoice.voucher] [--api http://127.0.0.1:8800] [--dry-run]
    # 模版参数缺失时按裸 fields=raw 库内字段解析（跳过钩子）。
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from command_shared import ocr_storage, ocr_validate  # noqa: E402


def _load_template(template_id: str, api: str) -> dict | None:
    try:
        import urllib.request
        with urllib.request.urlopen(f"{api.rstrip('/')}/api/ocr/templates/{template_id}", timeout=10) as r:
            return json.load(r)
    except Exception as exc:  # noqa: BLE001
        print(f"[warn] 拉取模版失败（{exc}），按裸字段解析、跳过钩子")
        return None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", required=True, help="结果库路径（.ocr_results.db）")
    parser.add_argument("--template", default=None, help="模版 id（决定 fields/钩子/宽松集）")
    parser.add_argument("--api", default="http://127.0.0.1:8800")
    parser.add_argument("--dry-run", action="store_true", help="只统计不写库")
    args = parser.parse_args()

    db_path = Path(args.db)
    raw_path = Path(str(db_path) + ".raw.json")
    if not raw_path.is_file():
        print(f"[error] 找不到模型原文留痕: {raw_path}")
        return 2
    raw_doc = json.loads(raw_path.read_text(encoding="utf-8"))
    pages: dict[str, str] = raw_doc.get("pages") or {}

    template = _load_template(args.template, args.api) if args.template else None
    fields = (template or {}).get("fields") or None
    hooks = []
    if template and template.get("postprocess"):
        for spec in template["postprocess"]:
            try:
                hooks.append({"fn": ocr_validate.compile_page_hook(spec.get("name", "hook"), spec["code"]),
                              "name": spec.get("name", "hook")})
            except Exception as exc:  # noqa: BLE001
                print(f"[warn] 钩子 {spec.get('name')} 编译失败跳过: {exc}")
    lenient_fields = None
    if template and template.get("lenient"):
        lenient_fields = list(fields or [])

    connection = ocr_storage.connect(db_path)
    ocr_storage.initialize(connection)  # 触发旧库迁移（seq 主键）
    try:
        # 定位要修复的 (file_hash, source_path)：优先匹配原文文件名对应的库内既有行
        # （append 的页级替换按同键删除，键必须与旧行一致，否则旧行残留造成重复）。
        raw_name = Path(raw_doc.get("file", "")).name or db_path.stem.replace(".ocr_results", "")
        keys = connection.execute(
            "SELECT DISTINCT file_hash, source_path FROM records WHERE source_path = ?",
            (raw_name,)).fetchall()
        if len(keys) >= 1:
            file_hash, source_path = keys[0]["file_hash"], keys[0]["source_path"]
        elif Path(raw_doc.get("file", "")).is_file():
            from command_shared.ocr_render import calculate_file_hash
            file_hash = calculate_file_hash(Path(raw_doc["file"]))
            source_path = raw_name
        else:
            print(f"[error] 库内无 source_path={raw_name} 的行且原文件不可达，无法确定键")
            return 2

        existing = ocr_storage.read_records(connection)
        by_page: dict[int, int] = {}
        for row in existing:
            by_page[int(row.get("页码", 0) or 0)] = by_page.get(int(row.get("页码", 0) or 0), 0) + 1
        if fields is None:  # 无模版：用库内第一条记录的字段集
            fields = [k for k in (existing[0] if existing else {}).keys() if k not in ("页码", "行号")]
            if not fields:
                print("[error] 库为空且未指定模版，无法推断字段")
                return 2

        healed_pages, planned = 0, 0
        for page_str, raw_text in sorted(pages.items(), key=lambda kv: int(kv[0])):
            page_no = int(page_str)
            notes: list[str] = []
            try:
                records = ocr_validate.parse_records(raw_text, fields, lenient_fields, notes)
            except ValueError as exc:
                print(f"[skip] 第{page_no}页解析失败: {exc}")
                continue
            if records and hooks:
                records = ocr_validate.run_page_hooks(hooks, records, page_no, fields, notes)
            if not records:
                print(f"[skip] 第{page_no}页无记录")
                continue
            payload = [(page_no, {**r, "页码": page_no}) for r in records]
            healed_pages += 1
            if args.dry_run:
                print(f"[dry] 第{page_no}页 {by_page.get(page_no, 0)} 条 → {len(payload)} 条")
                planned += len(payload)
                continue
            ocr_storage.append_records(connection, file_hash, source_path, payload)
        final = planned if args.dry_run else len(ocr_storage.read_records(connection))
        print(f"\n完成：修复 {healed_pages}/{len(pages)} 页；全库记录 {len(existing)} → "
              f"{'(预计)' if args.dry_run else ''}{final} 条")
        return 0
    finally:
        connection.close()


if __name__ == "__main__":
    raise SystemExit(main())
