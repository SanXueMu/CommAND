"""L3 files 路由：文件上传 → DATA_DIR 落盘 → 返回容器内路径（供工具 path 类输入引用）；产物受控下载。"""

import re
import uuid
from datetime import date
from pathlib import Path

from fastapi import APIRouter, HTTPException, UploadFile
from fastapi.responses import FileResponse

import deps

router = APIRouter(prefix="/files", tags=["files"])

_MAX_BYTES = 200 * 1024 * 1024
_UNSAFE = re.compile(r"[^\w.\-\u4e00-\u9fff]+")


@router.get("/download")
def download(path: str) -> FileResponse:
    """受控下载：目标必须真实存在于 DATA_DIR 内（resolve 防目录穿越）。"""
    data_dir = Path(deps.get_config().data_dir).resolve()
    target = Path(path).resolve()
    if data_dir not in target.parents:
        raise HTTPException(status_code=403, detail="仅允许下载 DATA_DIR 内的文件")
    if not target.is_file():
        raise HTTPException(status_code=404, detail=f"文件不存在: {path}")
    return FileResponse(target, filename=target.name)


@router.post("", status_code=201)
async def upload(file: UploadFile) -> dict:
    data_dir = deps.get_config().data_dir
    target_dir = Path(data_dir) / "uploads" / date.today().isoformat()
    target_dir.mkdir(parents=True, exist_ok=True)

    raw_name = Path(file.filename or "unnamed").name
    safe_name = _UNSAFE.sub("_", raw_name).strip("_") or "unnamed"
    target = target_dir / f"{uuid.uuid4().hex[:8]}_{safe_name}"

    size = 0
    with target.open("wb") as out:
        while chunk := await file.read(1024 * 1024):
            out.write(chunk)
            size += len(chunk)
            if size > _MAX_BYTES:
                out.close()
                target.unlink(missing_ok=True)
                raise HTTPException(status_code=413, detail=f"文件超过 {_MAX_BYTES // 1024 // 1024}MB 上限")
    if size == 0:
        target.unlink(missing_ok=True)
        raise HTTPException(status_code=422, detail="空文件")
    return {"path": str(target), "name": raw_name, "size": size}
