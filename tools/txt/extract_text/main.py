"""txt / md → 整文件一个 text 单元（translee extract_text 移植）。"""
from __future__ import annotations

import hashlib
from pathlib import Path


def _file_hash(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(1048576):
            h.update(chunk)
    return h.hexdigest()


def run(input: dict, ctx, emit) -> dict:
    path = Path(input["file"])
    if not path.is_file():
        from core.errors import ToolDomainError

        raise ToolDomainError(f"文件不存在: {path}")

    text = path.read_text(encoding="utf-8", errors="replace").strip()
    emit({"phase": "extracted", "chars": len(text)})
    return {
        "file": str(path),
        "file_hash": _file_hash(path),
        "kind": "text",
        "units": [{"unit_id": path.name, "unit_type": "text", "text": text}],
    }
