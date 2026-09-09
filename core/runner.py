"""L5 三形态执行器：inproc / subprocess / http adapter（S2 实现）。

subprocess 契约：stdin 信封 JSON → stdout 结果 JSON，退出码 0/1/2/3。
"""

from typing import Any, Callable

from core.protocol import ToolManifest


class Runner:
    """按 manifest.runtime.kind 分派 adapter，统一 emit 注入与协作取消语义。"""

    def run(
        self,
        manifest: ToolManifest,
        input: dict[str, Any],
        ctx: Any,
        emit: Callable[[str, dict], None],
    ) -> dict[str, Any]:
        raise NotImplementedError("S2 里程碑实现")
