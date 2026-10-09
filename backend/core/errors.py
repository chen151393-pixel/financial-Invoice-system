"""统一应用错误，不依赖任何外部系统。"""


class ApiError(Exception):
    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status = status
        self.message = message
