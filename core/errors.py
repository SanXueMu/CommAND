"""L5 错误三分类：用户拒绝 / 系统致命 / 领域可恢复，及退出码与 HTTP 码映射。"""


class ToolUserError(Exception):
    """用户错误：提交即可判定（schema 不过、路径不存在），422 拒绝不入队。"""


class ToolSystemError(Exception):
    """系统错误：致命不可恢复（认证失败、存储损坏），中止并落盘。"""


class ToolDomainError(Exception):
    """领域错误：运行中可恢复（限流、单条质检不过），按 max_attempts 重试。"""


class ToolPauseError(Exception):
    """需要人工介入才能继续（旧版 .doc 需另存、扫描件需先补文字层、冒烟拦截等）。

    区别于 failed：任务落 `paused`、run 停在该步，**不消耗重试次数**；人工处理（或直接
    修正输入后点「继续」）由 resume 从该步续跑。子进程工具退出码 4 亦映射到此。
    """

    def __init__(self, message: str, *, hint: str | None = None) -> None:
        super().__init__(message)
        self.hint = hint


class ToolUnavailableError(Exception):
    """能力不可用（模型未开通 / 无权限 / 模型不存在）：**不重试**。

    与 ToolDomainError（限流等可重试）区分开：这种失败重试多少次都一样，应当交由 run 级
    `on_failure.fallback_flow` 降级到等价流（如「图片版 PDF 翻译」→「版式翻译」）。
    """


class TaskCancelled(Exception):
    """协作取消：工具在检查点主动抛出或 subprocess 被 SIGTERM 后转译。"""


EXIT_CODE = {ToolUserError: 1, ToolSystemError: 2, ToolDomainError: 3, ToolPauseError: 4,
             ToolUnavailableError: 5}
HTTP_STATUS = {ToolUserError: 422, ToolSystemError: 500, ToolDomainError: 503, ToolPauseError: 409,
               ToolUnavailableError: 503}


class ToolNotFoundError(Exception):
    """工具不存在于注册表（活跃状态）。"""


class TaskNotFoundError(Exception):
    """任务 handle 不存在。"""


class TaskConflictError(Exception):
    """任务状态冲突（终态后取消、重复终态等）。"""


def exit_code_for(exc: Exception) -> int:
    for cls, code in EXIT_CODE.items():
        if isinstance(exc, cls):
            return code
    return 2
