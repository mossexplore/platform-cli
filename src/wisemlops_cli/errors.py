"""CLI 统一异常。"""


class MlError(Exception):
    """可以直接展示给命令行用户的错误。"""


class ConfigError(MlError):
    """配置错误。"""


class CredentialError(MlError):
    """认证信息错误。"""


class AuthenticationError(MlError):
    """服务端拒绝了当前认证信息。"""


class ApiError(MlError):
    """接口请求错误。"""
