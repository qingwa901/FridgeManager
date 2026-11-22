from __future__ import annotations


class ServiceError(Exception):
    """业务错误：消息直接展示给用户，status_code 作为 HTTP 状态码返回（main.py 统一转换）。"""

    NOT_FOUND = 404
    CONFLICT = 409
    INVALID = 422

    def __init__(self, status_code: int, message: str):
        super().__init__(message)
        self.status_code = status_code
        self.message = message
