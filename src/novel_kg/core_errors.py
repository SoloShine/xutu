"""
统一错误类体系 — V27 P1。

所有 novel_kg 公共 API 的错误通过此模块的类表达，
标准化为 `{"error": str, "code": str}` 的 dict 格式。

调用方可通过 `code` 字段做程序化判断，不再依赖字符串匹配。

用法:
    from .core_errors import UserError, SystemError, LogicError

    # 抛出（内部使用）
    raise UserError("快照不存在", code="NOT_FOUND")

    # 转为 dict 返回给调用方
    return UserError("快照不存在", code="NOT_FOUND").to_dict()

    # 检查错误
    result = some_function()
    if result.get("code") == "NOT_FOUND":
        ...
"""


class NovelKGError(Exception):
    """所有 novel_kg 错误的基类。

    既是异常（可 raise），也可通过 to_dict() 转为标准化 dict。
    """

    def __init__(self, message: str, code: str = "UNKNOWN"):
        super().__init__(message)
        self.message = message
        self.code = code

    def to_dict(self) -> dict:
        """转为标准化错误 dict，可直接作为 MCP 工具返回值。"""
        return {"error": self.message, "code": self.code}

    def __str__(self):
        return f"[{self.code}] {self.message}"

    def __repr__(self):
        return f"{self.__class__.__name__}(message={self.message!r}, code={self.code!r})"


class UserError(NovelKGError):
    """用户输入/请求层面的错误。

    适用于：参数无效、资源不存在、破坏性操作未确认、操作前提不满足。
    这类错误通常可以通过修改用户输入来修复。
    """


class SystemError(NovelKGError):
    """基础设施/环境层面的错误。

    适用于：文件读写失败、LLM API 不可用、后端连接失败。
    这类错误通常需要运维干预。
    """


class LogicError(NovelKGError):
    """内部逻辑错误 — 表示代码中的 bug 或不可达状态。

    适用于：不可达代码路径、数据不一致、意外状态。
    这类错误表示代码需要修复。
    """
