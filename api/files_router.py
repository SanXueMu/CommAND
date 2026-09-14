"""L3 files 路由：文件上传 → DATA_DIR 落盘 → 返回容器内路径（供工具 path 类输入引用）；产物受控下载。"""

import json
import re
import shutil
import time
import uuid
import zipfile
from datetime import date, datetime
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, UploadFile
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel

import deps
from command_shared.image_translate import QUEUE_MAX as IMAGE_QUEUE_MAX
from core.errors import TaskNotFoundError

router = APIRouter(prefix="/files", tags=["files"])

_MAX_BYTES = 200 * 1024 * 1024
_UNSAFE = re.compile(r"[^\w.\-\u4e00-\u9fff]+")
_BATCH_ID_RE = re.compile(r"b_[0-9a-f]{6,32}")

# 批量上传（多文件/目录）与压缩包解压的上限
_MAX_BATCH_FILES = 200
_MAX_BATCH_TOTAL = 500 * 1024 * 1024
_MAX_ARCHIVE_BYTES = 500 * 1024 * 1024
_MAX_ARCHIVE_ENTRIES = 1000
_MAX_ARCHIVE_TOTAL = 2 * 1024 * 1024 * 1024
_MAX_LIST_FILES = 5000

# 图片翻译可直吃的图片后缀（与站点声明 batch.extensions 对齐）
IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp", ".tif", ".tiff", ".bmp"}


def _pdf_page_count(path: Path) -> int | None:
    """PDF 页数（探测失败返回 None，不阻断主流程）。"""
    try:
        import fitz  # pymupdf

        with fitz.open(path) as doc:
            return doc.page_count
    except Exception:  # noqa: BLE001
        return None


def _pdf_has_text_layer(path: Path) -> bool | None:
    """是否有可提取文字层（False=扫描件，走图片翻译）；探测失败返回 None。"""
    try:
        from command_shared.ocr_render import is_text_pdf

        return bool(is_text_pdf(path))
    except Exception:  # noqa: BLE001
        return None
_MAX_PACKAGE_RUNS = 200


def _label(raw: object) -> str:
    """压缩包名：清洗危险字符、折叠连续点、去掉首尾点下划线（中文/字母数字/._- 保留）。"""
    cleaned = re.sub(r"\.{2,}", ".", _UNSAFE.sub("_", str(raw or ""))).strip("_. ")
    return (cleaned or "翻译成果")[:40]


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


_SKIP_REASON = "暂不支持的类型：本轮不处理，任务暂停留档，原文件随批次导出"


def _entry(path: Path, base: Path, skip_exts: set[str] | None = None,
           reason: str | None = None) -> dict:
    item = {"path": str(path), "name": path.name,
            "rel": str(path.relative_to(base)), "size": path.stat().st_size}
    if skip_exts and path.suffix.lower() in skip_exts:
        item["skip"] = True
        item["skip_reason"] = reason or _SKIP_REASON
    return item


def _manifest_dir() -> Path:
    target = Path(deps.get_config().data_dir) / "batches"
    target.mkdir(parents=True, exist_ok=True)
    return target


def _write_batch_manifest(batch_id: str, root: str, batch_dir: Path,
                          saved: list[dict], skip_exts: set[str] | None = None) -> None:
    """上传即固化批次清单：导出按它还原原目录结构，不依赖 run 是否存在/成功。

    顺带清理 30 天前的旧清单（防止无限增长）。
    """
    target_dir = _manifest_dir()
    cutoff = time.time() - 30 * 86400
    for old in target_dir.glob("*.json"):
        try:
            if old.stat().st_mtime < cutoff:
                old.unlink()
        except OSError:  # noqa: PERF203
            pass
    payload = {"batch_id": batch_id, "root": root, "dir": str(batch_dir),
               "created_at": date.today().isoformat(), "skip_exts": sorted(skip_exts or ()),
               "files": saved}
    (target_dir / f"{batch_id}.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _new_batch_dir(label: str) -> Path:
    safe = (_UNSAFE.sub("_", label).strip("_") or "batch")[:60]
    target = Path(deps.get_config().data_dir) / "uploads" / date.today().isoformat() / f"{uuid.uuid4().hex[:8]}_{safe}"
    target.mkdir(parents=True, exist_ok=True)
    return target


@router.get("/batches")
def batch_manifests(ids: str) -> dict:
    """批次清单摘要（只读）：批次列/导出要显示「根目录名」，刷新后仍要能查到。

    返回 {names: {batch_id: 根目录名}, count: {batch_id: 条目数}}；未知 id 静默跳过。
    """
    names: dict[str, str] = {}
    counts: dict[str, int] = {}
    for raw in (ids or "").split(","):
        batch_id = raw.strip()
        if not batch_id or not _BATCH_ID_RE.fullmatch(batch_id):
            continue
        path = _manifest_dir() / f"{batch_id}.json"
        if not path.is_file():
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        names[batch_id] = str(data.get("root") or "")
        counts[batch_id] = len(data.get("files") or [])
    return {"names": names, "count": counts}


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
                       skip: str | None = None, label: str | None = None) -> dict:
    """多文件 / 目录上传：每个 file.filename 可含相对路径（浏览器 webkitdirectory 形态）。

    落盘：uploads/<日期>/<uuid8>_<label>/<相对路径>。
    上限：200 个文件、单文件 200MB、合计 500MB；越界即整批回滚（不留半批脏数据）。
    skip：本轮不处理的后缀（声明驱动，如 .ppt）——照常落盘但打标，前端据此生成暂停任务；
    同时固化批次清单 data/batches/<batch_id>.json（导出按它还原原目录结构）。
    """
    if not files:
        raise HTTPException(status_code=422, detail="未提供文件")
    if len(files) > _MAX_BATCH_FILES:
        raise HTTPException(status_code=413,
                            detail=f"文件数超上限 {_MAX_BATCH_FILES} 个（请改用压缩包上传）")
    exts = _parse_exts(extensions)
    skip_exts = _parse_exts(skip)
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
            saved.append(_entry(target, batch_dir, skip_exts))
    except Exception:
        shutil.rmtree(batch_dir, ignore_errors=True)
        raise
    batch_id = _new_batch_id()
    _write_batch_manifest(batch_id, root or batch_dir.name.split("_", 1)[-1], batch_dir, saved, skip_exts)
    return {"path": str(batch_dir), "name": batch_dir.name.split("_", 1)[-1], "count": len(saved),
            "size": total, "batch_id": batch_id, "root": root or batch_dir.name.split("_", 1)[-1],
            "files": saved, "skipped": [f["rel"] for f in saved if f.get("skip")]}


def _is_zip_symlink(info: zipfile.ZipInfo) -> bool:
    return (info.external_attr >> 16) & 0o170000 == 0o120000


@router.post("/archive", status_code=201)
async def upload_archive(file: UploadFile, extensions: str | None = None,
                         skip: str | None = None) -> dict:
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
    skip_exts = _parse_exts(skip)
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
                saved.append(_entry(target, batch_dir, skip_exts))
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
    batch_id = _new_batch_id()
    _write_batch_manifest(batch_id, batch_dir.name.split("_", 1)[-1], batch_dir, saved, skip_exts)
    return {"path": str(batch_dir), "name": batch_dir.name.split("_", 1)[-1], "count": len(saved),
            "size": total, "batch_id": batch_id, "root": batch_dir.name.split("_", 1)[-1],
            "files": saved, "skipped": skipped}



@router.post("/package", status_code=201)
def package_run_artifacts(body: dict) -> dict:
    """把多个任务的产物打包成一个 zip（服务端收集 → data/exports/<时间>_<名>.zip）。

    body: {run_ids: [...], scope: "final"|"all", name?: "压缩包名"}
    scope=final（默认）只含各 run 最后一步的成果；all 含每一步产物（含中间临时产物）。
    """
    raw_ids = body.get("run_ids") or []
    if not isinstance(raw_ids, list):
        raise HTTPException(status_code=422, detail="run_ids 须为数组")
    run_ids = [str(r).strip() for r in raw_ids if str(r).strip()]
    if not run_ids:
        raise HTTPException(status_code=422, detail="run_ids 不能为空")
    if len(run_ids) > _MAX_PACKAGE_RUNS:
        raise HTTPException(status_code=413, detail=f"单次最多打包 {_MAX_PACKAGE_RUNS} 个任务（当前 {len(run_ids)}）")
    scope = str(body.get("scope") or "final").lower()
    if scope not in ("final", "all"):
        raise HTTPException(status_code=422, detail="scope 只支持 final / all")

    service = deps.get_pipeline_service()
    zip_path = _data_dir() / "exports" / f"{datetime.now():%Y%m%d-%H%M%S}_{_label(body.get('name'))}.zip"
    zip_path.parent.mkdir(parents=True, exist_ok=True)

    entries: list[dict] = []
    skipped: list[dict] = []
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for run_id in run_ids:
            try:
                artifacts = service.collect_run_artifacts(run_id, scope)
            except TaskNotFoundError:
                skipped.append({"run_id": run_id, "reason": "任务不存在"})
                continue
            except Exception as error:  # noqa: BLE001 —— 单个任务失败不拖垮整包
                skipped.append({"run_id": run_id, "reason": f"{type(error).__name__}: {error}"})
                continue
            if not artifacts:
                skipped.append({"run_id": run_id, "reason": "没有可打包的产物"})
                continue
            folder = (_UNSAFE.sub("_", run_id)[:24] or "run")
            used: set[str] = set()
            for artifact in artifacts:
                arc = f"{folder}/{artifact['name']}"
                if arc in used:  # 同 run 内同名产物加序号，避免相互覆盖
                    stem, dot, suffix = artifact["name"].rpartition(".")
                    arc = (f"{folder}/{stem}-{len(used)}{dot}{suffix}" if dot
                           else f"{folder}/{artifact['name']}-{len(used)}")
                used.add(arc)
                try:
                    zf.write(artifact["path"], arcname=arc)
                except OSError as error:
                    skipped.append({"run_id": run_id, "reason": f"读取失败 {artifact['name']}: {error}"})
                    continue
                entries.append({"run_id": run_id, "name": artifact["name"], "arcname": arc,
                                "step": artifact.get("step"), "size": artifact.get("size", 0)})

    if not entries:
        zip_path.unlink(missing_ok=True)
        raise HTTPException(status_code=422, detail=f"所选任务没有可打包的产物（{skipped}）")

    return {
        "path": str(zip_path),
        "name": zip_path.name,
        "scope": scope,
        "count": len(entries),
        "runs": len({e["run_id"] for e in entries}),
        "size": zip_path.stat().st_size,
        "entries": entries,
        "skipped": skipped,
    }


_STATUS_ZH = {"queued": "排队中", "running": "进行中", "paused": "已暂停",
              "cancelled": "已取消", "succeeded": "已完成", "failed": "失败"}


class PackageBatchBody(BaseModel):
    batch_id: str
    suffix: str = "_中文"
    scope: str = "final"
    name: str | None = None


@router.post("/package_batch", status_code=201)
def package_batch(body: PackageBatchBody) -> dict:
    """批次导出：按**上传清单**还原原目录结构（只有批次根目录加 suffix）。

    - run 成功且有产物 → 放**译文产物**
    - 暂停/跳过/未提交/已删除 → 回退**源文件**（含未翻译的 PPT，保证交付目录结构与原结构一致）
    - run 失败 → 只进 missing（不把半成品混进交付目录）
    """
    manifest = _load_batch_manifest(body.batch_id)
    scope = str(body.scope or "final").lower()
    if scope not in ("final", "all"):
        raise HTTPException(status_code=422, detail="scope 只支持 final / all")
    suffix = _UNSAFE.sub("_", body.suffix or "")[:16]
    root = (_UNSAFE.sub("_", str(manifest.get("root") or "batch"))[:40] or "batch")
    service = deps.get_pipeline_service()
    runs = service.list_runs(batch_id=body.batch_id, limit=_MAX_PACKAGE_RUNS)["runs"]
    by_file = {str((r.get("input") or {}).get("file") or ""): r for r in runs}
    zip_path = _data_dir() / "exports" / f"{datetime.now():%Y%m%d-%H%M%S}_{_label(body.name or root)}.zip"
    zip_path.parent.mkdir(parents=True, exist_ok=True)

    translated: list[dict] = []
    passthrough: list[dict] = []
    missing: list[dict] = []
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for entry in (manifest.get("files") or [])[:_MAX_PACKAGE_RUNS]:
            rel = str(entry.get("rel") or entry.get("name") or "").replace("\\", "/")
            if not rel:
                continue
            parent = str(Path(rel).parent)
            prefix = root + suffix + (f"/{parent}" if parent not in (".", "", "/") else "")
            run = by_file.get(str(entry.get("path") or ""))
            artifacts: list[dict] = []
            if run is not None and run.get("status") == "succeeded":
                try:
                    artifacts = service.collect_run_artifacts(run["id"], scope)
                except Exception as error:  # noqa: BLE001 —— 单条失败不影响整批
                    missing.append({"rel": rel, "reason": f"产物收集失败: {error}"})
                    artifacts = []
            if artifacts:
                for artifact in artifacts:
                    arc = f"{prefix}/{artifact['name']}"
                    try:
                        zf.write(artifact["path"], arcname=arc)
                    except OSError as error:
                        missing.append({"rel": rel, "reason": f"读取产物失败: {error}"})
                        continue
                    translated.append({"rel": rel, "name": artifact["name"], "arcname": arc,
                                       "step": artifact.get("step"), "size": artifact.get("size", 0)})
                continue
            status = (run or {}).get("status")
            if status == "failed":
                missing.append({"rel": rel, "reason": "任务失败：不放入交付目录"})
                continue
            source = Path(str(entry.get("path") or ""))
            if not source.is_file():
                missing.append({"rel": rel, "reason": "源文件不存在"})
                continue
            reason = entry.get("skip_reason") if entry.get("skip") else None
            if not reason:
                reason = ("未翻译（保留源文件）" if status is None
                          else f"未产出（任务{_STATUS_ZH.get(str(status), status)}）")
            arc = f"{prefix}/{Path(rel).name}"
            zf.write(source, arcname=arc)
            passthrough.append({"rel": rel, "name": Path(rel).name, "arcname": arc, "reason": reason})

    if not translated and not passthrough and not missing:
        zip_path.unlink(missing_ok=True)
        raise HTTPException(status_code=422, detail="批次清单为空")
    return {
        "path": str(zip_path), "name": zip_path.name, "batch_id": body.batch_id,
        "scope": scope, "count": len(translated) + len(passthrough),
        "translated": translated, "passthrough": passthrough, "missing": missing,
        "size": zip_path.stat().st_size,
    }


def _load_batch_manifest(batch_id: str) -> dict:
    path = _manifest_dir() / f"{_UNSAFE.sub('', batch_id or '')}.json"
    if not path.is_file():
        raise HTTPException(status_code=404, detail=f"批次不存在或清单已过期: {batch_id}")
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise HTTPException(status_code=422, detail=f"批次清单损坏: {error}") from error


def _new_batch_id() -> str:
    return "b_" + uuid.uuid4().hex[:12]


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


@router.get("/probe")
def probe_file(path: str) -> dict:
    """只读轻量探测：扩展名 / PDF 页数 / 有无文字层 → 工作台据此自动选流。

    - kind：pdf | image | document | other
    - has_text_layer：仅 pdf 有值；False = 扫描件（图片版，走图片翻译）
    - image_max_pages：图片翻译单任务页数上限（超出需拆分，工作台据此提示）
    """
    target = _ensure_within(path)
    if not target.is_file():
        raise HTTPException(status_code=404, detail="文件不存在")
    ext = target.suffix.lower()
    result: dict = {
        "path": str(target), "name": target.name, "ext": ext, "kind": "other",
        "pages": None, "has_text_layer": None, "size": target.stat().st_size,
        "image_max_pages": IMAGE_QUEUE_MAX,
    }
    if ext in IMAGE_SUFFIXES:
        result["kind"] = "image"
    elif ext == ".pdf":
        result["kind"] = "pdf"
        result["pages"] = _pdf_page_count(target)
        result["has_text_layer"] = _pdf_has_text_layer(target)
    elif ext:
        result["kind"] = "document"
    return result


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
