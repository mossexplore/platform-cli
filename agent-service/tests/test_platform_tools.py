import httpx
import pytest
from types import SimpleNamespace
from wiserec_cli.client import PlatformClient
from wiserec_cli.models import Profile, Credentials
from wiserec_cli.business import BusinessSelection
from app.platform import Platform
from app.errors import AppError
from conftest import BUSINESS


def test_log_query_validates_host_file_and_injects_business(settings):
    requests = []

    def upstream(req):
        requests.append(req)
        assert req.headers["businessid"] == "b1"
        if req.url.path.endswith("queryServiceHostList"):
            data = {
                "count": 1,
                "data": [
                    {
                        "nodeName": "pod-1",
                        "clusterName": "cluster-1",
                        "infraType": "infer-python",
                    }
                ],
            }
        elif req.url.path.endswith("queryPodAdvanceLogFileList"):
            data = {"podLogFiles": [{"fileName": "run.log"}]}
        else:
            assert req.url.path.endswith("queryPodAdvanceLog")
            data = {"data": {"content": "2026-10-29 service started"}}
        return httpx.Response(200, json={"result": {"code": 0, **data}})

    p = Platform(settings, None)
    with PlatformClient(
        profile=Profile("dev", "https://platform.test/ai/"),
        credentials=Credentials.create("dev", "cookie", "csrf", "u", 1800),
        transport=httpx.MockTransport(upstream),
        business_selection=BusinessSelection.from_dict(BUSINESS),
        retry_times=0,
        timeout_ms=1000,
        verify_ssl=True,
    ) as client:
        args = {
            "service_id": "s1",
            "pod_name": "pod-1",
            "cluster_name": "cluster-1",
            "log_type": "run",
            "file_name": "run.log",
            "lines": 10,
            "keywords": [],
        }
        result = p.dispatch(client, "search_service_logs", args)
        assert (
            "service started" in result["content"] and result["requested_lines"] == 10
        )
        before = len(requests)
        with pytest.raises(AppError, match="日志文件不属于"):
            p.dispatch(
                client, "search_service_logs", {**args, "file_name": "other.log"}
            )
        assert len(requests) == before + 2
        before = len(requests)
        with pytest.raises(AppError, match="未在服务主机"):
            p.dispatch(client, "search_service_logs", {**args, "pod_name": "other"})
        assert len(requests) == before + 1


def test_task_search_is_bounded_and_checks_business(settings):
    p = Platform(settings, None)
    calls = []

    def listing(**kwargs):
        calls.append(kwargs)
        return {
            "items": [{"taskId": "different", "businessId": "b1"}],
            "pageSize": 50,
            "count": 10000,
        }

    service = SimpleNamespace(
        list_tasks=listing, client=SimpleNamespace(business_id="b1")
    )
    with pytest.raises(AppError, match="分页范围"):
        p.find_task(service, "missing")
    assert len(calls) == settings.runtime.max_auto_pages
    service.list_tasks = lambda **kw: {
        "items": [{"taskId": "target", "businessId": "other"}]
    }
    with pytest.raises(AppError, match="业务不匹配"):
        p.find_task(service, "target")


def test_mysql_ddl_preserves_long_text_and_identity_uniqueness():
    from sqlalchemy.schema import CreateTable
    from sqlalchemy.dialects import mysql
    from app.models import Base

    compiled = {
        table.name: str(CreateTable(table).compile(dialect=mysql.dialect()))
        for table in Base.metadata.sorted_tables
    }
    assert "MEDIUMTEXT" in compiled["messages"]
    assert "MEDIUMTEXT" in compiled["agent_runs"]
    assert "utf8mb4_bin" in compiled["agent_users"]
    assert "UNIQUE (conversation_id, client_message_id)" in compiled["agent_runs"]


def test_mysql_all_foreign_keys_share_explicit_table_collation():
    from sqlalchemy.schema import CreateTable
    from sqlalchemy.dialects import mysql
    from app.models import Base

    for table in Base.metadata.sorted_tables:
        ddl = str(CreateTable(table).compile(dialect=mysql.dialect()))
        assert "COLLATE utf8mb4_bin" in ddl
        assert "CHARSET=utf8mb4" in ddl
        assert "ENGINE=InnoDB" in ddl
        for fk in table.foreign_keys:
            assert (
                table.dialect_options["mysql"]["collate"]
                == fk.column.table.dialect_options["mysql"]["collate"]
            )
