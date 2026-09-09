"""L5 调度循环：认领（FOR UPDATE SKIP LOCKED）/ 心跳 / 恢复 / 双层并发闸（S2 实现）。"""


class Scheduler:
    """worker 主循环：从队列认领任务经 Runner 执行，状态全程落 PostgreSQL。"""

    def start(self) -> None:
        raise NotImplementedError("S2 里程碑实现")
