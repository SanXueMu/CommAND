"""L4 管线编排：线性管线逐步入队与推进（S3 实现）。"""

from typing import Any

from store.db import Db
from store.task_repo import TaskRepo


class PipelineService:
    """管线运行实例：上步 succeeded → 解析模板 → 校验下步 schema → 自动入队。"""

    def __init__(self, db: Db, task_repo: TaskRepo) -> None:
        self._db = db
        self._task_repo = task_repo

    def run(self, pipeline_id: str, input: dict[str, Any]) -> dict[str, Any]:
        raise NotImplementedError("S3 里程碑实现")
