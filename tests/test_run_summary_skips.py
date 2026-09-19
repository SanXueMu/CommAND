"""Y1/Y2：跳步入进度分母 + 人话原因。"""

from __future__ import annotations

from services.pipeline_service import PipelineService


def _summary(skipped, titles=None, statuses=None, outputs=None):
    return PipelineService._assemble_summary(
        statuses or {}, outputs or {}, 3, skipped, titles or {})


def test_skipped_steps_count_into_steps_done() -> None:
    """when 跳过的步无 task 行——Y1 单独并入，2/3 不再误导。"""
    out = _summary([{"step_index": 2, "when": {"input.export_units": True}}],
                   statuses={0: "succeeded", 1: "succeeded"})
    assert out["steps_done"] == 3
    assert out["steps_total"] == 3


def test_skip_reason_human_readable() -> None:
    """Y2：when 条件翻成人话（input.X=True → 未开启「X」）。"""
    out = _summary([{"step_index": 2, "when": {"input.export_units": True}}],
                   titles={"export_units": "导出识别单元"})
    assert out["steps_skipped"] == [{"step_index": 2, "reason": "未开启「导出识别单元」"}]


def test_skip_reason_variants() -> None:
    r = PipelineService._skip_reason
    assert r({"input.model": "@exists"}, {"model": "模型"}) == "「模型」无值（该步需要它）"
    assert r({"input.use_cache": False}, {"use_cache": "缓存"}) == "「缓存」需关闭"
    assert r({"prev.view_spec": "@exists"}, {}) == "「prev.view_spec」无值（该步需要它）"
    assert r({"input.db": "a"}, {"db": "结果库"}) == "「结果库」需为 a"


def test_records_count_and_failed_pages_keys() -> None:
    """X4 键名修正 + Y4：records_count 进 summary（0 也透出，前端警示）。"""
    out = _summary([], outputs={1: {"failed_pages": 2, "records_count": 0}})
    assert out["failed_pages"] == 2
    assert out["records_count"] == 0


def test_no_skipped_no_noise() -> None:
    out = _summary(None, statuses={0: "succeeded"})
    assert "steps_skipped" not in out
    assert "records_count" not in out
