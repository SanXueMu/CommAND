"""段落序列 → 日期归一去重（translee 唯一值收集机制，映射全部显式为数据）。

只翻唯一值——翻译量与行数无关，与去重后的唯一值数量成正比。
数字型日期 → [[DATE_n]] 占位符后去重；回插所需的 date_maps 按输入段对齐输出。
"""
from __future__ import annotations

from command_shared.normalize import normalize_dates


def run(input: dict, ctx, emit) -> dict:
    segments = input["segments"]
    unique: list[str] = []
    first_seen: dict[str, int] = {}
    index_map: list[int] = []
    date_maps: list[dict[str, str]] = []

    for seg in segments:
        norm, dates = normalize_dates(seg)
        idx = first_seen.get(norm)
        if idx is None:
            idx = len(unique)
            first_seen[norm] = idx
            unique.append(norm)
        index_map.append(idx)
        date_maps.append(dates)

    emit({"phase": "deduped", "input": len(segments), "unique": len(unique)})
    return {"unique": unique, "index_map": index_map, "date_maps": date_maps}
