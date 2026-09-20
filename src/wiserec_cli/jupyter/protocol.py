"""Jupyter 默认 WebSocket 消息协议和 Notebook 输出合并。"""
from __future__ import annotations

import json
import struct
import time
from datetime import datetime, timezone
from uuid import uuid4

import nbformat
import websocket

from .connection import JupyterError


def decode_message(raw):
    if not raw:
        raise JupyterError("Kernel 连接已断开，执行结果待确认；不会自动重跑")
    if isinstance(raw, bytes):
        # 默认协议二进制帧：偏移数量、偏移表、JSON、可选 buffers。
        count = struct.unpack("!I", raw[:4])[0]
        if count < 1 or 4 * (count + 1) > len(raw):
            raise JupyterError("Kernel 返回无效二进制消息")
        offsets = struct.unpack("!" + "I" * count, raw[4:4 * (count + 1)])
        start, end = offsets[0], offsets[1] if count > 1 else len(raw)
        if not 4 * (count + 1) <= start <= end <= len(raw):
            raise JupyterError("Kernel 返回无效消息偏移")
        raw = raw[start:end].decode("utf-8")
    return json.loads(raw)


class KernelChannel:
    def __init__(self, socket):
        self.socket = socket
        self.session = str(uuid4())

    def send(self, kind, content):
        msg_id = str(uuid4())
        self.socket.send(json.dumps({
            "header": {"msg_id": msg_id, "session": self.session, "username": "ml",
                       "msg_type": kind, "version": "5.3",
                       "date": datetime.now(timezone.utc).isoformat()},
            "parent_header": {}, "metadata": {}, "content": content,
            "channel": "shell", "buffers": [],
        }))
        return msg_id

    def messages(self, msg_id, deadline):
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError("Notebook 执行达到时限")
            self.socket.settimeout(min(1, remaining))
            try:
                message = decode_message(self.socket.recv())
            except websocket.WebSocketTimeoutException:
                continue
            except websocket.WebSocketException as exc:
                raise JupyterError("Kernel 连接中断，执行结果待确认；不会自动重跑") from exc
            if message.get("parent_header", {}).get("msg_id") == msg_id:
                yield message

    def ready(self, timeout):
        msg_id = self.send("kernel_info_request", {})
        for message in self.messages(msg_id, time.monotonic() + timeout):
            if message.get("header", {}).get("msg_type") == "kernel_info_reply":
                return message["content"]


class Outputs:
    def __init__(self, emit):
        self.emit = emit
        self.displays = {}
        self.pending_clear = set()

    def clear(self, cell):
        cell.outputs = []
        self.pending_clear.discard(id(cell))
        for key in self.displays:
            self.displays[key] = [(owner, out) for owner, out in self.displays[key] if owner is not cell]

    def accept(self, cell, message):
        kind = message.get("header", {}).get("msg_type")
        content = message.get("content", {})
        if kind == "clear_output":
            if content.get("wait"):
                self.pending_clear.add(id(cell))
            else:
                self.clear(cell)
            return
        if kind not in {"stream", "display_data", "execute_result", "error", "update_display_data"}:
            return
        if id(cell) in self.pending_clear:
            self.clear(cell)
        if kind == "update_display_data":
            key = content.get("transient", {}).get("display_id")
            for _, output in self.displays.get(key, []):
                output.data = content.get("data", {})
                output.metadata = content.get("metadata", {})
            return
        if kind == "stream":
            output = nbformat.v4.new_output(kind, name=content["name"], text=content["text"])
            self.emit(content["text"])
        elif kind == "error":
            output = nbformat.v4.new_output(kind, ename=content["ename"], evalue=content["evalue"],
                                           traceback=content.get("traceback", []))
            self.emit("\n".join(content.get("traceback", [])) + "\n")
        else:
            data = {"data": content.get("data", {}), "metadata": content.get("metadata", {})}
            if kind == "execute_result":
                data["execution_count"] = content.get("execution_count")
            output = nbformat.v4.new_output(kind, **data)
            text = content.get("data", {}).get("text/plain")
            if text:
                self.emit(("".join(text) if isinstance(text, list) else text) + "\n")
        cell.outputs.append(output)
        display_id = content.get("transient", {}).get("display_id")
        if display_id and kind in {"display_data", "execute_result"}:
            self.displays.setdefault(display_id, []).append((cell, output))


def execute_cell(channel, cell, outputs, deadline):
    request = channel.send("execute_request", {
        "code": cell.source, "silent": False, "store_history": True,
        "user_expressions": {}, "allow_stdin": False, "stop_on_error": True,
    })
    reply = None
    idle = False
    for message in channel.messages(request, deadline):
        kind = message.get("header", {}).get("msg_type")
        content = message.get("content", {})
        if kind == "execute_reply" and message.get("channel") == "shell":
            reply = content
            cell.execution_count = content.get("execution_count")
        elif kind == "status" and content.get("execution_state") == "idle":
            idle = True
        elif message.get("channel") == "iopub":
            outputs.accept(cell, message)
        if reply is not None and idle:
            if reply.get("status") != "ok":
                raise JupyterError("单元格执行失败：" + str(reply.get("ename", reply.get("status"))))
            return
