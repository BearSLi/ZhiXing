"""全局错误定义（与业务无关，任何层都可以导入）

为什么要单独一个文件：
    原先 BizError 定义在 services/ticket_service.py 里，却被 services/llm_service.py
    和 services/ai_service.py 导入 —— 大模型模块反向依赖工单模块，依赖方向是错的。
    抽出来之后，依赖关系变成"大家都依赖 errors"，不再有横向耦合。
"""


class BizError(Exception):
    """业务异常：只描述"业务上出了什么问题"，不关心 HTTP

    由 main.py 的全局异常处理器统一翻译成 HTTP 响应，
    因此业务层不需要、也不应该 import fastapi。
    """

    def __init__(self, message: str, code: int = 400):
        self.message = message
        self.code = code
        super().__init__(message)


class ConflictError(BizError):
    """并发冲突（如乐观锁判定失败）—— 语义上对应 HTTP 409"""

    def __init__(self, message: str = "数据已被他人修改，请刷新后重试"):
        super().__init__(message, code=409)
