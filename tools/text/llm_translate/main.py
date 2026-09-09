"""纯翻译 — S2 调度链路验证参考实现（确定性伪翻译）。

LLM 版替换点：只改本文件的 run() 内部，manifest 与调用契约不变。
"""
import time


def run(input: dict, ctx, emit) -> dict:
    """inproc 契约：run(input, ctx, emit) -> dict。"""
    from core.errors import TaskCancelled

    segments = input["segments"]
    target_lang = input.get("target_lang", "English")
    translations = []
    for i, seg in enumerate(segments):
        if ctx.cancel_event.is_set():
            raise TaskCancelled(ctx.handle)
        time.sleep(0.2)
        emit("progress", {"done": i + 1, "total": len(segments)})
        translations.append(f"[{target_lang}] {seg}")
    emit("log", {"message": f"translated {len(segments)} segments -> {target_lang}"})
    return {"translations": translations}
