"""PDF 页面方向转正（CommOCR turn_pages 移植）：逐页检测主导书写方向并旋转。

判定：字符数加权投票行方向——(0,1) 顺时针躺倒→270°，(0,-1) 逆时针→90°。
局限（与 CommOCR 一致）：180° 倒置不改 dir 检测不到；无文字层扫描页跳过。
平面设计图（横版贴竖版页）识别前必经此工具，否则 VL 版面对位大面积出错。
"""
from __future__ import annotations

from pathlib import Path

from command_shared.ocr_render import straighten_pdf
from core.errors import ToolDomainError


def run(input: dict, ctx, emit) -> dict:
    src = Path(input["file"])
    if not src.is_file():
        raise ToolDomainError(f"文件不存在: {src}")
    if src.suffix.lower() != ".pdf":
        raise ToolDomainError("仅支持 PDF（图片无文字层无需转正）")

    data_dir = Path(__import__("os").environ.get("COMMAND_DATA_DIR", "data"))
    out_dir = data_dir / "outputs" / "upright"
    out_dir.mkdir(parents=True, exist_ok=True)
    dst = out_dir / f"{src.stem}_转正.pdf"

    turned = straighten_pdf(src, dst)
    emit({"type": "progress", "phase": "upright",
          "message": f"转正 {turned} 页 → {dst.name}"})
    return {"file": str(dst), "source": str(src), "turned_pages": turned}
