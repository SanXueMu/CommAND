"""L3 数据路由：DATA_DIR 内 OCR 结果库清点（结果浏览器选库用）。"""

from datetime import datetime
from pathlib import Path

from fastapi import APIRouter

import deps

router = APIRouter(prefix="/data", tags=["data"])

_DB_SUFFIXES = {".ocrdb", ".db"}


@router.get("/dbs")
def list_dbs() -> dict:
    data_dir = Path(deps.get_config().data_dir)
    if not data_dir.exists():
        return {"dbs": []}
    dbs = []
    for path in sorted(data_dir.rglob("*")):
        if not path.is_file() or path.suffix.lower() not in _DB_SUFFIXES:
            continue
        if path.name.startswith("."):
            continue
        stat = path.stat()
        dbs.append({
            "path": str(path),
            "name": path.name,
            "size": stat.st_size,
            "modified": datetime.fromtimestamp(stat.st_mtime).isoformat(timespec="seconds"),
        })
    return {"dbs": dbs}
