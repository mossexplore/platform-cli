"""Per-operation clients. Every business HTTP call checks session and gateway first."""

from datetime import timezone
import json
import threading
from contextlib import contextmanager
from .business_tools import OPERATIONS
from .artifacts import Artifacts, MAX_BYTES
from .approvals import Approvals
from collections import defaultdict
import time
from uuid import uuid4
import httpx
from wiserec_cli import __version__
from wiserec_cli.access_transport import tls_verify
from wiserec_cli.models import Profile, Credentials
from wiserec_cli.business import BusinessSelection
from wiserec_cli.client import PlatformClient
from wiserec_cli.client_metadata import begin_invocation
from wiserec_cli.errors import AuthenticationError
from wiserec_cli.services.model import ModelService
from wiserec_cli.services.train import TrainService
from wiserec_cli.services.service import ServiceCatalog
from .models import Credential, User, Run, now
from .sessions import valid
from .errors import AppError
from .sanitize import clean
from .credential_activity import confirm_activity, response_credentials, expire_snapshot

COMMANDS = {
    "keepalive": "ml auth ping start",
    "list_models": "ml model list",
    "get_model": "ml model detail",
    "get_model_source": "ml model source",
    "get_model_training": "ml model source",
    "list_train_tasks": "ml train list",
    "get_train_task": "ml train list",
    "list_train_instances": "ml train instance list",
    "list_train_history": "ml train history list",
    "list_services": "ml service list",
    "list_service_hosts": "ml service host list",
    "get_service_deployments": "ml service deployment list",
    "list_service_log_files": "ml service logs",
    "search_service_logs": "ml service logs",
    "business_selection": "ml business use",
}
COMMANDS.update({name: op.command for name, op in OPERATIONS.items()})
LOG_TYPES = {
    "infer-python": (
        "run",
        "interface",
        "metrics",
        "engine",
        "ascend",
        "mslite",
        "alarm",
    ),
    "rtc": (
        "rtc",
        "run",
        "interface",
        "dcs",
        "metrics",
        "gc",
        "interface_manager",
        "interface_extend",
        "engine",
        "monitor",
        "catalina",
        "dmq",
    ),
}


class Platform:
    def __init__(self, config, db, transport=None):
        self.config, self.db, self.transport = config, db, transport
        self.approvals = Approvals()
        self.credential_locks = defaultdict(threading.RLock)

    def identity(self, env, cred, *, return_response=False):
        with httpx.Client(
            transport=self.transport,
            verify=tls_verify() if env.verify_ssl else False,
            trust_env=False,
            timeout=15,
            follow_redirects=False,
        ) as client:
            r = client.get(
                Profile(env.id, env.api_endpoint).base_url + "/ai/user/info",
                headers={
                    "cookie": cred.cookie,
                    "csrftoken": cred.csrftoken,
                    "referer": env.api_endpoint,
                },
            )
        if r.status_code >= 500:
            raise AppError("PLATFORM_UNAVAILABLE", "平台身份服务暂时不可用", 503)
        try:
            result = r.json()["result"]
        except (ValueError, KeyError, TypeError):
            result = {}
        if (
            not r.is_success
            or type(result.get("code")) is not int
            or result["code"] != 0
            or not str(result.get("username", "")).strip()
        ):
            raise AppError(
                "PLATFORM_AUTH_REJECTED", "平台登录验证失败，请重新登录", 401
            )
        return (result, r) if return_response else result

    def context(self, session_id, run_id=None):
        with self.db() as db:
            s = valid(db, self.config, session_id)
            if run_id:
                run = db.get(Run, run_id)
                if not run or run.session_id != s.id or run.status != "running":
                    raise AppError("RUN_CANCELLED", "运行已停止", 409)
            u, c = db.get(User, s.user_id), db.get(Credential, s.id)
            cred = Credentials(
                profile=s.environment_id,
                username=u.username,
                cookie=c.cookie,
                csrftoken=c.csrftoken,
                acquired_at=c.acquired_at.replace(tzinfo=timezone.utc).timestamp(),
                expires_at=c.expires_at.replace(tzinfo=timezone.utc).timestamp(),
            )
            return s, self.config.env(s.environment_id), cred

    def gateway(self, session_id, business, name, invocation, run_id=None):
        s, env, cred = self.context(session_id, run_id)
        if not any(x == business for x in s.catalog):
            raise AppError("BUSINESS_DENIED", "业务不属于本次登录，请重新选择", 403)
        request_id = str(uuid4())
        headers = {
            "Authorization": "Bearer "
            + self.config.access_control.gateway_token.get_secret_value(),
            "businessid": business["businessId"],
            "X-CLI-Version": __version__,
            "X-CLI-Protocol-Version": "1",
            "X-CLI-Invocation-ID": invocation,
            "X-Request-ID": request_id,
        }
        try:
            with httpx.Client(
                transport=self.transport,
                verify=tls_verify(),
                trust_env=self.config.access_control.use_env_proxy,
                timeout=self.config.access_control.timeout_seconds,
                follow_redirects=False,
            ) as client:
                r = client.post(
                    self.config.access_control.url.rstrip("/")
                    + "/api/v1/gateway/check",
                    headers=headers,
                    json={
                        "username": cred.username,
                        "environment": env.id,
                        "platform_origin": Profile(env.id, env.api_endpoint).base_url,
                        "command": COMMANDS[name],
                        "full_command": "Agent " + name,
                    },
                )
            body = r.json()
        except (httpx.HTTPError, ValueError):
            raise AppError(
                "ACCESS_UNAVAILABLE", "权限服务暂时不可用，已停止平台调用", 503
            ) from None
        if not r.is_success or body.get("allowed") is not True:
            raise AppError(
                "ACCESS_DENIED", "权限或版本准入未通过，请联系管理员核对授权", 403
            )
        return request_id

    def execute(self, session_id, run_id, business, name, args, invocation, approval=None):
        if name in OPERATIONS:
            args = OPERATIONS[name].schema.model_validate(args).model_dump()
            if OPERATIONS[name].write:
                self.approvals.consume(approval, session_id, run_id, business, name, args)
        with self.credential_locks[session_id]:
            return self._execute(session_id, run_id, business, name, args, invocation)

    def _execute(self, session_id, run_id, business, name, args, invocation):
        if name not in COMMANDS or name in ("business_selection", "keepalive"):
            raise AppError("TOOL_DENIED", "不支持该操作", 403)
        s, env, cred = self.context(session_id, run_id)
        try:
            identity, response = self.identity(env, cred, return_response=True)
            if identity["username"] != cred.username:
                raise AppError("IDENTITY_CHANGED", "平台账号已变化，请重新登录", 401)
            cred = confirm_activity(
                self.db,
                self.config,
                session_id,
                cred,
                response_credentials(cred, response),
            )
        except AppError as exc:
            if exc.status == 401:
                expire_snapshot(self.db, session_id, cred)
            raise
        owner = self
        deadline = time.monotonic() + self.config.runtime.run_timeout_seconds

        latest_response = []

        guard_failures = []

        def guard():
            if time.monotonic() >= deadline:
                raise AppError('TOOL_TIMEOUT', '操作时间已超限', 504)
            try:
                owner.gateway(session_id, business, name, invocation, run_id)
            except AppError as exc:
                guard_failures.append(exc)
                raise

        class BoundedResponse:
            def __init__(inner, response): inner.response = response
            def __getattr__(inner, key): return getattr(inner.response, key)
            def iter_bytes(inner, *args, **kwargs):
                count = 0
                for chunk in inner.response.iter_bytes(*args, **kwargs):
                    owner.context(session_id, run_id)
                    count += len(chunk)
                    if count > MAX_BYTES: raise AppError('FILE_TOO_LARGE', '文件超过 20 MiB', 413)
                    yield chunk

        class GuardedClient(PlatformClient):
            def upload_file(inner, *a, **kw):
                guard()
                result = super().upload_file(*a, **kw)
                owner.context(session_id, run_id)
                return result

            @contextmanager
            def stream(inner, *a, **kw):
                guard()
                with super().stream(*a, **kw) as response:
                    yield BoundedResponse(response)
                owner.context(session_id, run_id)

            def request(inner, *a, **kw):
                nonlocal cred
                if time.monotonic() >= deadline:
                    raise AppError("TOOL_TIMEOUT", "查询时间已超限", 504)
                guard()
                result = super().request(*a, **kw)
                payload = result.get("result", {}) if isinstance(result, dict) else {}
                if (
                    latest_response
                    and type(payload.get("code")) is int
                    and payload["code"] == 0
                ):
                    updated = response_credentials(cred, latest_response[-1])
                    cred = confirm_activity(
                        owner.db, owner.config, session_id, cred, updated
                    )
                    inner._client.headers.update(
                        {"cookie": cred.cookie, "csrftoken": cred.csrftoken}
                    )
                owner.context(session_id, run_id)
                return result

        begin_invocation()
        with GuardedClient(
            profile=Profile(env.id, env.api_endpoint),
            credentials=cred,
            timeout_ms=self.config.runtime.platform_timeout_seconds * 1000,
            retry_times=0,
            verify_ssl=env.verify_ssl,
            transport=self.transport,
            business_selection=BusinessSelection.from_dict(business),
        ) as client:
            client.agent_artifacts = Artifacts(self.config, session_id, business)
            client.agent_business = business
            client.agent_environment = env
            client.agent_transport = self.transport
            client.agent_guard = guard
            def check():
                try:
                    return owner.context(session_id, run_id)
                except AppError as exc:
                    guard_failures.append(exc)
                    raise
            client.agent_check = check
            client._client.event_hooks["response"].append(
                lambda response: latest_response.__setitem__(slice(None), [response])
            )
            try:
                result = self.dispatch(client, name, args)
                if guard_failures:
                    raise guard_failures[-1]
            except AuthenticationError:
                try:
                    self.identity(env, cred)
                except AppError as exc:
                    if exc.status == 401:
                        expire_snapshot(self.db, session_id, cred)
                        raise AppError(
                            "AUTH_REQUIRED", "平台登录已失效，请重新登录", 401
                        ) from None
                    raise
                raise AppError("RESOURCE_DENIED", "平台拒绝访问该资源", 403) from None
            except Exception:
                if guard_failures:
                    raise guard_failures[-1] from None
                raise
        normalized = clean(result)
        if (
            len(json.dumps(normalized, ensure_ascii=False))
            > self.config.runtime.max_tool_output_chars
        ):
            # Keep valid structured output; never slice JSON or resource identifiers.
            return {
                "ok": True,
                "data": None,
                "truncated": True,
                "warnings": ["结果超过输出限制，请缩小名称、分页或日志行数后重试"],
            }
        return {
            "ok": True,
            "data": normalized,
            "truncated": False,
            "fetched_at": now().isoformat() + "Z",
        }

    def find_task(self, service, task_id):
        for page in range(1, self.config.runtime.max_auto_pages + 1):
            result = service.list_tasks(
                page_index=page, page_size=self.config.runtime.max_page_size
            )
            for task in result["items"]:
                if task.get("taskId") == task_id:
                    if task.get("businessId") != service.client.business_id:
                        raise AppError("RESOURCE_DENIED", "训练任务业务不匹配", 403)
                    return task
            if not result["items"] or page * result["pageSize"] >= result["count"]:
                break
        raise AppError(
            "TASK_NOT_FOUND",
            "在本次分页范围内未找到任务，请先按名称查询以缩小范围",
            404,
        )

    def dispatch(self, client, name, a):
        if name in OPERATIONS:
            from .business_dispatch import dispatch
            return dispatch(self, client, name, a)
        page, size = a.get("page", 1), a.get("page_size", 10)
        if page < 1 or not 1 <= size <= self.config.runtime.max_page_size:
            raise ValueError("分页参数超出范围")
        m, t, s = ModelService(client), TrainService(client), ServiceCatalog(client)
        if name == "list_models":
            return m.list_models(page, size, a.get("name", ""), a.get("model_type"), a.get("owner"), a.get("team_id", ""))
        if name == "get_model":
            return m.detail(a["model_id"])
        if name == "get_model_source":
            return m.source(a["model_id"])
        if name == "get_model_training":
            return m.train_task(a["model_id"])
        if name == "list_train_tasks":
            return t.list_tasks(page, size, a.get("name", ""))
        if name == "get_train_task":
            return self.find_task(t, a["task_id"])
        if name == "list_train_instances":
            return t.list_instances(self.find_task(t, a["task_id"]), page, size)
        if name == "list_train_history":
            self.find_task(t, a["task_id"])
            return t.list_history(a["task_id"])
        if name == "list_services":
            return s.list_services(
                page, size, name=a.get("name"), model_name=a.get("model_name"), model_version=a.get("model_version")
            )
        if name == "list_service_hosts":
            return s.list_hosts(a["service_id"], page, pod_ip=a.get("pod_ip"))
        if name == "get_service_deployments":
            return s.list_deployments(a["service_id"])
        host = None
        for p in range(1, self.config.runtime.max_auto_pages + 1):
            result = s.list_hosts(a["service_id"], p)
            host = next(
                (
                    h
                    for h in result["items"]
                    if h.get("nodeName") == a["pod_name"]
                    and h.get("clusterName") == a["cluster_name"]
                ),
                None,
            )
            if host or not result["items"] or p * 10 >= result["total"]:
                break
        if not host:
            raise AppError(
                "HOST_NOT_FOUND", "未在服务主机中找到该 Pod/集群，请先查询主机", 404
            )
        infra = host.get("infraType")
        if a["log_type"] not in LOG_TYPES.get(infra, ()):
            raise AppError("LOG_TYPE_INVALID", "日志类别不适用于该主机")
        files = s.list_pod_log_files(
            a["pod_name"], a["cluster_name"], a["log_type"], infra
        )
        if name == "list_service_log_files":
            return files
        if a["file_name"] not in [f.get("fileName") for f in files]:
            raise AppError("LOG_FILE_INVALID", "日志文件不属于该主机")
        lines = a.get("lines", 100)
        if not 1 <= lines <= self.config.runtime.max_log_lines:
            raise ValueError("日志行数超限")
        return {
            "content": s.search_pod_log(
                a["pod_name"],
                a["cluster_name"],
                a["log_type"],
                a["file_name"],
                a.get("keywords", []),
                lines,
                a.get("search_order", "tail"),
                a.get("grep_scope", "C"),
                a.get("grep_line", 0),
                infra,
            ),
            "warnings": ["当前接口按指定方向和行数检索，不保证覆盖完整时间范围"],
            "requested_lines": lines,
        }
