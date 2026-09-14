"""L3 files 路由：文件上传 → DATA_DIR 落盘 → 返回容器内路径（供工具 path 类输入引用）；产物受控下载。"""

import re
import shutil
import uuid
import zipfile
from datetime import date
from pathlib import Path

from fastapi import APIRouter, HTTPException, UploadFile
from fastapi.responses import FileResponse, Response

import deps

router = APIRouter(prefix="/files", tags=["files"])

_MAX_BYTES = 200 * 1024 * 1024
_UNSAFE = re.compile(r"[^\w.\-\u4e00-\u9fff]+")

# 批量上传（多文件/目录）与压缩包解压的上限
_MAX_BATCH_FILES = 200
_MAX_BATCH_TOTAL = 500 * 1024 * 1024
_MAX_ARCHIVE_BYTES = 500 * 1024 * 1024
_MAX_ARCHIVE_ENTRIES = 1000
_MAX_ARCHIVE_TOTAL = 2 * 1024 * 1024 * 1024
_MAX_LIST_FILES = 5000


def _data_dir() -> Path:
    return Path(deps.get_config().data_dir).resolve()


def _ensure_within(path: str | Path) -> Path:
    """resolve 后必须落在 DATA_DIR 内（防目录穿越；软链指向外部同样被拒）。"""
    target = Path(path).resolve()
    data_dir = _data_dir()
    if target != data_dir and data_dir not in target.parents:
        raise HTTPException(status_code=403, detail="仅允许访问 DATA_DIR 内的路径")
    return target


def _safe_rel(name: str) -> Path:
    """相对路径逐段清洗（去空段、替换危险字符、限长）。"""
    parts = [p for raw in re.split(r"[\\/]+", name or "")
             if (p := (_UNSAFE.sub("_", raw).strip("_. "))[:120])]
    if not parts:
        raise HTTPException(status_code=422, detail=f"非法文件名: {name!r}")
    return Path(*parts)


def _strict_rel(name: str) -> Path:
    """比 _safe_rel 更严：显式拒绝绝对路径与上跳（压缩包条目 / 浏览器目录上传）。"""
    raw = (name or "").replace("\\", "/")
    if raw.startswith("/") or re.match(r"^[A-Za-z]:", raw) or ".." in raw.split("/"):
        raise ValueError(f"非法路径（绝对路径或上跳）: {name!r}")
    return _safe_rel(raw)


def _parse_exts(raw: str | None) -> set[str]:
    return {e.strip().lower() if e.strip().startswith(".") else f".{e.strip().lower()}"
            for e in (raw or "").split(",") if e.strip()}


def _ext_ok(name: str, exts: set[str]) -> bool:
    return not exts or Path(name).suffix.lower() in exts


def _entry(path: Path, base: Path) -> dict:
    return {"path": str(path), "name": path.name,
            "rel": str(path.relative_to(base)), "size": path.stat().st_size}


def _new_batch_dir(label: str) -> Path:
    safe = (_UNSAFE.sub("_", label).strip("_") or "batch")[:60]
    target = Path(deps.get_config().data_dir) / "uploads" / date.today().isoformat() / f"{uuid.uuid4().hex[:8]}_{safe}"
    target.mkdir(parents=True, exist_ok=True)
    return target


@router.get("/list")
def list_files(path: str | None = None, extensions: str | None = None,
               recursive: bool = True, limit: int = _MAX_LIST_FILES) -> dict:
    """列出 DATA_DIR 内的文件（供「目录已在服务器上」的批量入口）。

    - path 缺省为 DATA_DIR 根；必须在其内（防穿越）
    - extensions 逗号分隔过滤（如 ".pdf,.docx"）；recursive 默认递归子目录
    - 上限 limit 个，超出置 truncated=true
    """
    base = _ensure_within(path or _data_dir())
    if not base.exists():
        raise HTTPException(status_code=404, detail=f"路径不存在: {path}")
    if base.is_file():
        base = base.parent
    data_dir, exts = _data_dir(), _parse_exts(extensions)
    files: list[dict] = []
    truncated = False
    for item in (base.rglob("*") if recursive else base.glob("*")):
        if len(files) >= limit:
            truncated = True
            break
        try:
            if not item.is_file() or item.is_symlink():
                continue
            if data_dir not in item.resolve().parents:  # 软链指向外部 → 跳过
                continue
        except OSError:
            continue
        if _ext_ok(item.name, exts):
            files.append(_entry(item, base))
    return {"path": str(base), "name": base.name or str(base), "count": len(files),
            "size": sum(f["size"] for f in files), "files": files, "truncated": truncated}


@router.post("/batch", status_code=201)
async def upload_batch(files: list[UploadFile], extensions: str | None = None,
                       label: str | None = None) -> dict:
    """多文件 / 目录上传：每个 file.filename 可含相对路径（浏览器 webkitdirectory 形态）。

    落盘：uploads/<日期>/<uuid8>_<label>/<相对路径>。
    上限：200 个文件、单文件 200MB、合计 500MB；越界即整批回滚（不留半批脏数据）。
    """
    if not files:
        raise HTTPException(status_code=422, detail="未提供文件")
    if len(files) > _MAX_BATCH_FILES:
        raise HTTPException(status_code=413,
                            detail=f"文件数超上限 {_MAX_BATCH_FILES} 个（请改用压缩包上传）")
    exts = _parse_exts(extensions)
    try:
        first = _strict_rel(files[0].filename or "unnamed")
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    # 目录上传时首个路径段即根目录名：用它命名批次目录，并在落盘时剥掉这层前缀（避免重复嵌套）
    root = first.parts[0] if len(first.parts) > 1 else None
    batch_dir = _new_batch_dir(label or root or "批量上传")

    saved: list[dict] = []
    total = 0
    try:
        for item in files:
            try:
                rel = _strict_rel(item.filename or "unnamed")
            except ValueError as exc:
                raise HTTPException(status_code=422, detail=str(exc)) from exc
            if root and len(rel.parts) > 1 and rel.parts[0] == root:
                rel = Path(*rel.parts[1:])
            if not _ext_ok(rel.name, exts):
                raise HTTPException(status_code=422, detail=f"不支持的类型: {rel.name}")
            target = batch_dir / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            size = 0
            with target.open("wb") as out:
                while chunk := await item.read(1024 * 1024):
                    out.write(chunk)
                    size += len(chunk)
                    total += len(chunk)
                    if size > _MAX_BYTES:
                        raise HTTPException(
                            status_code=413,
                            detail=f"{rel.name} 超过 {_MAX_BYTES // 1024 // 1024}MB 上限")
                    if total > _MAX_BATCH_TOTAL:
                        raise HTTPException(
                            status_code=413,
                            detail=f"合计超过 {_MAX_BATCH_TOTAL // 1024 // 1024}MB 上限")
            if size == 0:
                raise HTTPException(status_code=422, detail=f"空文件: {rel.name}")
            saved.append(_entry(target, batch_dir))
    except Exception:
        shutil.rmtree(batch_dir, ignore_errors=True)
        raise
    return {"path": str(batch_dir), "name": batch_dir.name.split("_", 1)[-1], "count": len(saved),
            "size": total, "files": saved}


def _is_zip_symlink(info: zipfile.ZipInfo) -> bool:
    return (info.external_attr >> 16) & 0o170000 == 0o120000


@router.post("/archive", status_code=201)
async def upload_archive(file: UploadFile, extensions: str | None = None) -> dict:
    """.zip 压缩包 → 解压到 uploads/<日期>/<uuid8>_<名>/（stdlib zipfile，零新依赖）。

    防护：仅 .zip；条目 ≤1000、声明解压总量 ≤2GB、写盘按实际字节计（防大小造假的 zip 炸弹）；
    条目名逐段校验（拒绝绝对路径 / 上跳），软链条目直接跳过；不支持的扩展名跳过并回报。
    """
    name = Path(file.filename or "archive.zip").name
    if Path(name).suffix.lower() != ".zip":
        raise HTTPException(status_code=422, detail="仅支持 .zip 压缩包（请先压缩为 zip）")
    uploads = Path(deps.get_config().data_dir) / "uploads" / date.today().isoformat()
    uploads.mkdir(parents=True, exist_ok=True)
    tmp_zip = uploads / f".tmp_{uuid.uuid4().hex}.zip"

    size = 0
    with tmp_zip.open("wb") as out:
        while chunk := await file.read(1024 * 1024):
            out.write(chunk)
            size += len(chunk)
            if size > _MAX_ARCHIVE_BYTES:
                out.close()
                tmp_zip.unlink(missing_ok=True)
                raise HTTPException(status_code=413,
                                    detail=f"压缩包超过 {_MAX_ARCHIVE_BYTES // 1024 // 1024}MB 上限")
    if size == 0:
        tmp_zip.unlink(missing_ok=True)
        raise HTTPException(status_code=422, detail="空文件")

    exts = _parse_exts(extensions)
    batch_dir = _new_batch_dir(Path(name).stem)
    saved: list[dict] = []
    skipped: list[dict] = []
    total = 0
    try:
        with zipfile.ZipFile(tmp_zip) as archive:
            entries = [i for i in archive.infolist() if not i.is_dir()]
            if len(entries) > _MAX_ARCHIVE_ENTRIES:
                raise HTTPException(status_code=413,
                                    detail=f"压缩包条目超上限 {_MAX_ARCHIVE_ENTRIES} 个")
            if sum(i.file_size for i in entries) > _MAX_ARCHIVE_TOTAL:
                raise HTTPException(status_code=413,
                                    detail=f"解压总量超上限 {_MAX_ARCHIVE_TOTAL // 1024 // 1024 // 1024}GB")
            for info in entries:
                if _is_zip_symlink(info):
                    skipped.append({"name": info.filename, "reason": "软链条目已跳过"})
                    continue
                try:
                    rel = _strict_rel(info.filename)
                except ValueError as exc:
                    skipped.append({"name": info.filename, "reason": str(exc)})
                    continue
                if not _ext_ok(rel.name, exts):
                    skipped.append({"name": info.filename, "reason": "扩展名不在允许范围"})
                    continue
                target = batch_dir / rel
                target.parent.mkdir(parents=True, exist_ok=True)
                written = 0
                with archive.open(info) as src, target.open("wb") as out:
                    while chunk := src.read(1024 * 1024):
                        out.write(chunk)
                        written += len(chunk)
                        total += len(chunk)
                        if total > _MAX_ARCHIVE_TOTAL:
                            raise HTTPException(
                                status_code=413,
                                detail=f"解压总量超上限 {_MAX_ARCHIVE_TOTAL // 1024 // 1024 // 1024}GB")
                if written == 0:
                    target.unlink(missing_ok=True)
                    skipped.append({"name": info.filename, "reason": "空文件"})
                    continue
                saved.append(_entry(target, batch_dir))
    except HTTPException:
        shutil.rmtree(batch_dir, ignore_errors=True)
        raise
    except (zipfile.BadZipFile, OSError) as exc:
        shutil.rmtree(batch_dir, ignore_errors=True)
        raise HTTPException(status_code=422, detail=f"压缩包无法解析: {exc}") from exc
    finally:
        tmp_zip.unlink(missing_ok=True)
    if not saved:
        shutil.rmtree(batch_dir, ignore_errors=True)
        raise HTTPException(status_code=422, detail=f"压缩包内没有可用的文件（跳过 {len(skipped)} 条）")
    return {"path": str(batch_dir), "name": batch_dir.name.split("_", 1)[-1], "count": len(saved),
            "size": total, "files": saved, "skipped": skipped}



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


@router.get("/page")
def page_image(path: str, page: int = 1) -> Response:
    """原页预览：PDF 按页渲染 jpeg，图片文件直通原样（限 DATA_DIR 内，防目录穿越）。"""
    data_dir = Path(deps.get_config().data_dir).resolve()
    target = Path(path).resolve()
    if data_dir not in target.parents:
        raise HTTPException(status_code=403, detail="仅允许预览 DATA_DIR 内的文件")
    if not target.is_file():
        raise HTTPException(status_code=404, detail=f"文件不存在: {path}")
    if target.suffix.lower() in {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tif", ".tiff"}:
        if page != 1:
            raise HTTPException(status_code=422, detail="图片文件无页码概念（page 必须为 1）")
        return FileResponse(target)
    if target.suffix.lower() != ".pdf":
        raise HTTPException(status_code=422, detail=f"不支持的预览类型: {target.suffix or '未知'}")
    import fitz

    with fitz.open(target) as doc:
        if not 1 <= page <= doc.page_count:
            raise HTTPException(status_code=422, detail=f"页码超界: 1..{doc.page_count}")
        pix = doc[page - 1].get_pixmap(dpi=110)
        return Response(content=pix.tobytes("jpeg"), media_type="image/jpeg")


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
