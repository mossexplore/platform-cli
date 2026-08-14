"""CLI 统一异常。"""


class WoError(Exception):
    """可以直接展示给命令行用户的错误。"""


class ConfigError(WoError):
    """配置错误。"""


class CredentialError(WoError):
    """认证信息错误。"""


class AuthenticationError(WoError):
    """服务端拒绝了当前认证信息。"""


class ApiError(WoError):
    """接口请求错误。"""
