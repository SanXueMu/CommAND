"""L5 错误三分类：用户拒绝 / 系统致命 / 领域可恢复，及退出码与 HTTP 码映射。"""


class ToolUserError(Exception):
    """用户错误：提交即可判定（schema 不过、路径不存在），422 拒绝不入队。"""


class ToolSystemError(Exception):
    """系统错误：致命不可恢复（认证失败、存储损坏），中止并落盘。"""


class ToolDomainError(Exception):
    """领域错误：运行中可恢复（限流、单条质检不过），按 max_attempts 重试。"""


EXIT_CODE = {ToolUserError: 1, ToolSystemError: 2, ToolDomainError: 3}
HTTP_STATUS = {ToolUserError: 422, ToolSystemError: 500, ToolDomainError: 503}


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
