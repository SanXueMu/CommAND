"""下载并生成内嵌 CJK 字体（Noto Sans SC Regular 静态 TTF）。

产物：assets/fonts/NotoSansSC-Regular.ttf（版式翻译渲染内嵌用，~10MB）
用法：uv run python scripts/fetch_cjk_font.py
说明：仓库已提交生成后的静态 TTF，正常无需执行；字体升级/重建时运行本脚本。
"""
from __future__ import annotations

import pathlib
import urllib.request

VAR_URL = "https://raw.githubusercontent.com/notofonts/noto-cjk/main/Sans/Variable/TTF/Subset/NotoSansSC-VF.ttf"
OUT_DIR = pathlib.Path(__file__).resolve().parent.parent / "assets" / "fonts"


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    var = OUT_DIR / "NotoSansSC-var.ttf"
    static = OUT_DIR / "NotoSansSC-Regular.ttf"
    if not var.exists():
        print(f"下载 {VAR_URL}")
        urllib.request.urlretrieve(VAR_URL, var)
    from fontTools.ttLib import TTFont
    from fontTools.varLib import instancer

    font = TTFont(str(var))
    instancer.instantiateVariableFont(font, {"wght": 400}, inplace=False, updateFontNames=True)
    font.save(str(static))
    print(f"已生成 {static}（{static.stat().st_size // 1024} KB）")


if __name__ == "__main__":
    main()
