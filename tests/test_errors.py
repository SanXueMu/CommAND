"""errors 模块测试：三分类退出码映射。"""

from core.errors import ToolDomainError, ToolSystemError, ToolUserError, exit_code_for


def test_exit_codes_for_three_classes():
    assert exit_code_for(ToolUserError("路径不存在")) == 1
    assert exit_code_for(ToolSystemError("认证失败")) == 2
    assert exit_code_for(ToolDomainError("限流")) == 3


def test_unclassified_falls_back_to_system():
    assert exit_code_for(RuntimeError("未分类异常")) == 2
