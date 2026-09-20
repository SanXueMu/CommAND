"""L3 数据路由：DATA_DIR 内 OCR 结果库清点（结果浏览器选库用）。"""

from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, HTTPException

import deps
from core.errors import TaskConflictError, TaskNotFoundError, ToolUserError
from store.pipeline_repo import PipelineRepo

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


@router.delete("/dbs")
def delete_db(path: str, force: bool = False) -> dict:
    """AD3：删除结果库（连同其 .raw.json 留痕）。

    仅允许 data 目录内的 .ocr_results.db；被任务输出引用时默认拒绝并回报引用数
    （先在任务清单删除对应任务）。AP-D：`force=true` 时无视引用强删——引用它的任务
    详情会自动显示产物「已删除」（AF4），不再被卡死。 """
    try:
        return _delete_db_impl(path, force=force)
    except ToolUserError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except TaskNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except TaskConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


def _delete_db_impl(path: str, force: bool = False) -> dict:
    data_dir = Path(deps.get_config().data_dir).resolve()
    target = Path(path)
    try:
        resolved = target.resolve()
    except OSError:
        raise ToolUserError("路径无法解析") from None
    if resolved.suffix.lower() != ".db" or resolved.name.endswith(".raw.json"):
        raise ToolUserError("只允许删除 .ocr_results.db 结果库文件")
    if data_dir != resolved and data_dir not in resolved.parents:
        raise ToolUserError("路径不在数据目录内")
    if not resolved.is_file():
        raise TaskNotFoundError(f"结果库不存在: {target.name}")

    repo = PipelineRepo(deps.get_db())
    refs = repo.db_reference_count(str(target))
    if refs and not force:
        raise TaskConflictError(
            f"该结果库仍被 {refs} 个任务引用：可先在任务清单删除对应任务（选「并删除产物」），"
            "或改用强制删除")

    removed = [resolved]
    resolved.unlink()
    raw = resolved.with_name(resolved.name + ".raw.json")
    if raw.is_file():
        raw.unlink()
        removed.append(raw)
    return {"removed": [str(p) for p in removed], "forced": bool(force), "references": refs}
