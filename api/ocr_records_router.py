"""OCR 结果库只读 REST 端点（工作台左栏数据面）。

与 ocr_templates_router 同款取舍：库写入/查询编排走 ocrdb.* 工具异步任务链路，
本 router 提供同步只读，供 CommWEB 工作台直读（库列表 + 库内记录分页）。
安全：db 参数仅接受库目录下的文件名（拒绝任何路径分隔符）。
"""
import json
import os
from pathlib import Path

from fastapi import APIRouter, HTTPException

from command_shared import ocr_storage

router = APIRouter(prefix="/ocr/records", tags=["ocr-records"])


def _ocr_dir() -> Path:
    base = Path(os.environ.get("COMMAND_DATA_DIR", "data"))
    return base / "ocr"


def _resolve_db(name: str) -> Path:
    if not name or "/" in name or "\\" in name or ".." in name:
        raise HTTPException(status_code=400, detail=f"invalid db name: {name}")
    path = _ocr_dir() / name
    if not path.exists():
        raise HTTPException(status_code=404, detail=f"db not found: {name}")
    return path


@router.get("/dbs")
def list_dbs() -> dict:
    """结果库列表：库目录下的 .db 文件，附记录数与最近更新时间。"""
    ocr_dir = _ocr_dir()
    dbs = []
    if ocr_dir.exists():
        for path in sorted(ocr_dir.glob("*.db"), key=lambda p: p.stat().st_mtime, reverse=True):
            count, updated = 0, None
            try:
                connection = ocr_storage.connect(path)
                try:
                    row = connection.execute("SELECT COUNT(*) FROM records").fetchone()
                    count = int(row[0])
                    updated = int(path.stat().st_mtime)
                finally:
                    connection.close()
            except Exception:
                pass  # 空库/损坏库照常列出，计数缺省
            dbs.append({"name": path.name, "records": count, "updated_at": updated,
                        "path": str(path.resolve())})
    return {"dbs": dbs}


@router.get("")
def read_records(db: str, limit: int = 200, offset: int = 0, path: str | None = None) -> dict:
    """库内记录分页读取：data JSON 逐行展开，columns 为字段并集（稳定排序）；path 过滤单文件范围。"""
    p = _resolve_db(db)
    columns: list[str] = []
    rows: list[dict] = []
    connection = ocr_storage.connect(p)
    try:
        ocr_storage.initialize(connection)
        where, params = "", []
        if path:
            where = " WHERE source_path LIKE ? ESCAPE '\\'"
            params = ["%" + path.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"]
        total = connection.execute(f"SELECT COUNT(*) FROM records{where}", params).fetchone()[0]
        cursor = connection.execute(
            "SELECT file_hash, source_path, row_number, page_number, data"
            f" FROM records{where} ORDER BY source_path, row_number LIMIT ? OFFSET ?",
            [*params, limit, offset],
        )
        for r in cursor:
            data = json.loads(r[4] or "{}")
            for key in data:
                if key not in columns:
                    columns.append(key)
            rows.append({
                "source_path": r[1], "row_number": r[2], "page_number": r[3], **data,
            })
    finally:
        connection.close()
    return {"columns": columns, "rows": rows, "total": int(total),
            "limit": limit, "offset": offset}
