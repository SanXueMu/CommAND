"""译文页图 → 单 PDF（图片翻译链末步）。

- 按页序合成（每页按图片像素尺寸建页，保持原比例）
- 合成成功后清理中间产物目录（页图 / 译文图），实现「只留 PDF」
- 清理仅限 `COMMAND_DATA_DIR` 内路径（防误删）；只删文件与空目录，不递归删非产物目录
"""
from __future__ import annotations

import os
import shutil
from pathlib import Path


def _error(message: str):
    from core.errors import ToolDomainError

    return ToolDomainError(message)


def _cleanup(dirs: list[str], data_root: Path) -> dict:
    removed: list[str] = []
    skipped: list[str] = []
    files = 0
    freed = 0
    root = data_root.resolve()
    for raw in dirs:
        path = Path(str(raw))
        try:
            resolved = path.resolve()
        except OSError:
            skipped.append(str(path))
            continue
        if root not in resolved.parents or not resolved.is_dir():
            skipped.append(str(path))
            continue
        for item in resolved.rglob("*"):
            if item.is_file():
                try:
                    freed += item.stat().st_size
                    item.unlink()
                    files += 1
                except OSError:
                    pass
        shutil.rmtree(resolved, ignore_errors=True)
        removed.append(str(resolved))
    return {"removed": removed, "files_removed": files, "bytes_freed": freed, "skipped": skipped}


def run(input: dict, ctx, emit) -> dict:
    from command_shared.ocr_render import images_to_pdf

    raw = input.get("images") or []
    if not isinstance(raw, list) or not raw:
        raise _error("images 不能为空")
    paths = [Path(str(p)) for p in raw]
    missing = [str(p) for p in paths if not p.is_file()]
    if missing:
        raise _error(f"译文图片不存在: {missing[0]}")

    data_dir = Path(os.environ.get("COMMAND_DATA_DIR", "data"))
    out_dir = data_dir / "outputs" / getattr(ctx, "handle", "adhoc") / str(input.get("dir_name") or "outputs")
    out_dir.mkdir(parents=True, exist_ok=True)

    source_file = input.get("source_file")
    stem = Path(str(source_file)).stem if source_file else (paths[0].stem.replace("page_", "文档"))
    name = str(input.get("output_name") or f"{stem}_图片译文.pdf")
    if not name.lower().endswith(".pdf"):
        name = f"{name}.pdf"
    dest = out_dir / name

    emit({"phase": "composing", "images": len(paths), "name": name})
    try:
        pages = images_to_pdf(paths, dest)
    except Exception as error:  # noqa: BLE001
        raise _error(f"合成 PDF 失败: {type(error).__name__}: {error}")

    cleanup = _cleanup(list(input.get("cleanup_dirs") or []), data_dir)
    emit({"phase": "composed", "path": str(dest), "pages": pages,
          "cleaned": len(cleanup["removed"]), "bytes_freed": cleanup["bytes_freed"]})
    return {
        "path": str(dest),
        "name": name,
        "pages": pages,
        "size": dest.stat().st_size,
        "source_file": str(source_file) if source_file else None,
        "cleanup": cleanup,
    }
