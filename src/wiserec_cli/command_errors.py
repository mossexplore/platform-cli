"""将参数解析错误交给统一消息入口，保留 Click 的退出码。"""
import re

import click

from . import messages as msg


def show_usage_error(exc: click.ClickException) -> None:
    message = exc.format_message()
    # 仅翻译框架固定文本，用户输入与自定义校验说明保持原样。
    replacements = {
        "No such command": "未知命令",
        "No such option": "未知选项",
        "Missing argument": "缺少参数",
        "Missing option": "缺少选项",
        "Missing parameter": "缺少参数",
        "Invalid value for": "参数值无效",
        "Invalid value": "参数值无效",
        "Got unexpected extra arguments": "存在多余参数",
        "Got unexpected extra argument": "存在多余参数",
        "Possible options": "可用选项",
        "Did you mean": "是否要使用",
        "is not a valid integer": "不是有效整数",
        "is not a valid float": "不是有效数值",
        "is not a valid boolean": "不是有效布尔值",
        "is not in the range": "不在允许范围内",
        "does not exist": "不存在",
        "is a directory": "是目录",
        "is a file": "是文件",
        "is not readable": "不可读取",
    }
    for original, translated in replacements.items():
        message = message.replace(original, translated)
    message = re.sub(r"Option ('[^']+') requires an argument\.", r"选项 \1 需要参数值", message)
    msg.error(message)
    if exc.ctx is not None:
        root_name = exc.ctx.find_root().info_name or "ml"
        path = "ml" + exc.ctx.command_path[len(root_name):]
        msg.info(f"请执行 {path} --help 查看用法")
    else:
        msg.info("请执行 ml --help 查看用法")
