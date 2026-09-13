"""PDF 扫描版 OCR 保障：检测文本层 → 调 OCRmyPDF 补隐形文字层。

供两条路径复用：
- 文档提取/翻译（``pdf.extract.pages`` 的 auto_ocr、``flow.translate.pdf``）
- 版式翻译叠加（``pdf.extract.blocks`` / ``pdf.render.translated``）

设计要点：
- 识别引擎 Tesseract（默认 eng+chi_sim），出层/纠偏/优化交给 OCRmyPDF
- 已含文字层的页不重复识别（``--skip-text``）；``force=True`` 才整篇重做（``--force-ocr``）
- 页数/超时/jobs 均可限制；超页数直接抛错，由调用方决定是否放宽
- 返回补层后的 PDF 路径；调用方据此**重新提取**（层内文字带坐标，可定位可翻译）
"""
from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

from command_shared.ocr_render import calculate_file_hash, is_text_pdf  # noqa: F401  (re-export)
from core.errors import ToolDomainError

DEFAULT_LANGUAGES = "eng+chi_sim"
DEFAULT_JOBS = 4
DEFAULT_OVERSAMPLE = 300
DEFAULT_MAX_PAGES = 300
DEFAULT_TIMEOUT_S = 900


def _bin() -> str:
    return os.environ.get("OCRMYPDF_BIN", "ocrmypdf")


def ocrmypdf_available() -> bool:
    return shutil.which(_bin()) is not None


def tesseract_languages() -> set[str]:
    """本机 tesseract 可用语言包（供上层校验/提示），不可用时返回空集。"""
    tesseract = shutil.which("tesseract")
    if not tesseract:
        return set()
    try:
        proc = subprocess.run([tesseract, "--list-langs"], capture_output=True, text=True, timeout=20)
    except Exception:
        return set()
    return {ln.strip() for ln in (proc.stdout or "").splitlines()[1:] if ln.strip()}


def page_count(path) -> int:
    import pymupdf

    with pymupdf.open(path) as doc:
        return doc.page_count


def page_char_counts(path, limit: int | None = None) -> list[int]:
    """每页去空白后的字符数（用于判定扫描页）。"""
    import pymupdf

    counts: list[int] = []
    with pymupdf.open(path) as doc:
        for i, page in enumerate(doc):
            if limit is not None and i >= limit:
                break
            counts.append(len((page.get_text() or "").strip()))
    return counts


def scanned_pages(path, min_chars_per_page: int = 20, limit: int | None = None) -> list[int]:
    """文本量低于阈值的页码（1-based），即需要 OCR 的页。"""
    return [i + 1 for i, n in enumerate(page_char_counts(path, limit)) if n < min_chars_per_page]


def needs_ocr(path, min_chars_per_page: int = 20) -> bool:
    return bool(scanned_pages(path, min_chars_per_page))


def _build_cmd(src: Path, dst: Path, *, languages: str, jobs: int, oversample: int,
               deskew: bool, clean: bool, force: bool) -> list[str]:
    cmd = [
        _bin(), "-l", languages, "--output-type", "pdf",
        "--jobs", str(jobs), "--oversample", str(oversample),
        "--force-ocr" if force else "--skip-text",
    ]
    if deskew:
        cmd.append("--deskew")
    if clean:
        cmd.append("--clean")
    cmd += [str(src), str(dst)]
    return cmd


def add_ocr_layer(
    src,
    dst,
    *,
    languages: str = DEFAULT_LANGUAGES,
    jobs: int = DEFAULT_JOBS,
    oversample: int = DEFAULT_OVERSAMPLE,
    deskew: bool = True,
    clean: bool = True,
    max_pages: int = DEFAULT_MAX_PAGES,
    timeout_s: int = DEFAULT_TIMEOUT_S,
    force: bool = False,
    progress=None,
) -> dict:
    """给扫描版 PDF 补隐形文字层，写出 ``dst``。

    返回 ``{path, pages, pages_ocr, applied, languages, skipped}``；``applied=False`` 表示
    原本即含文字层、无需 OCR（``path`` 即原文件）。
    """
    src = Path(src)
    dst = Path(dst)
    if not src.is_file():
        raise ToolDomainError(f"文件不存在: {src}")

    total = page_count(src)
    if total > max_pages:
        raise ToolDomainError(f"PDF 共 {total} 页，超过上限 {max_pages} 页；请拆分后重试")

    scanned = scanned_pages(src)
    if not scanned and not force:
        return {"path": str(src), "pages": total, "pages_ocr": 0,
                "applied": False, "languages": languages, "skipped": "已有文字层"}

    if not ocrmypdf_available():
        raise ToolDomainError("未找到 ocrmypdf：无法为扫描版 PDF 补文字层（检查部署依赖）")

    dst.parent.mkdir(parents=True, exist_ok=True)
    if progress:
        progress({"phase": "ocr_start", "pages": total, "scanned": len(scanned),
                  "languages": languages})

    cmd = _build_cmd(src, dst, languages=languages, jobs=jobs, oversample=oversample,
                     deskew=deskew, clean=clean, force=force)
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout_s)
    except subprocess.TimeoutExpired:
        raise ToolDomainError(f"OCR 超时（>{timeout_s}s）；请减少页数或调低 jobs 后重试")
    if proc.returncode != 0:
        tail = " | ".join((proc.stderr or proc.stdout or "").strip().splitlines()[-8:])
        raise ToolDomainError(f"OCRmyPDF 执行失败: {tail}")
    if not dst.is_file():
        raise ToolDomainError("OCRmyPDF 未产出文件")

    if progress:
        progress({"phase": "ocr_done", "pages": total, "pages_ocr": len(scanned)})
    return {"path": str(dst), "pages": total, "pages_ocr": len(scanned),
            "applied": True, "languages": languages}
