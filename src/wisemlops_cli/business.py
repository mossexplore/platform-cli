"""部门、租户（服务）和团队目录管理。"""

from __future__ import annotations

import json
import os
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

from .config import user_config_dir
from .errors import BusinessError


@dataclass(frozen=True)
class Team:
    id: str
    key: str
    name: str
    status: str
    business_id: str

    @property
    def selectable(self) -> bool:
        return self.status == "available"

    @classmethod
    def from_dict(cls, value: Dict[str, Any]) -> "Team":
        return cls(
            id=str(value.get("id", "")),
            key=str(value.get("key", "")),
            name=str(value.get("name", "")),
            status=str(value.get("status", "")),
            business_id=str(value.get("businessId") or ""),
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "key": self.key,
            "name": self.name,
            "status": self.status,
            "businessId": self.business_id,
        }


@dataclass(frozen=True)
class Tenant:
    id: str
    name: str
    service_ids: Tuple[str, ...]
    teams: Tuple[Team, ...]

    @classmethod
    def from_dict(cls, value: Dict[str, Any]) -> "Tenant":
        return cls(
            id=str(value.get("id", "")),
            name=str(value.get("name", "")),
            service_ids=tuple(str(item) for item in value.get("service_ids", [])),
            teams=tuple(Team.from_dict(item) for item in value.get("teams", [])),
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "service_ids": list(self.service_ids),
            "teams": [item.to_dict() for item in self.teams],
        }


@dataclass(frozen=True)
class Department:
    id: str
    name: str
    tenants: Tuple[Tenant, ...]

    @classmethod
    def from_dict(cls, value: Dict[str, Any]) -> "Department":
        return cls(
            id=str(value.get("id", "")),
            name=str(value.get("name", "")),
            tenants=tuple(
                Tenant.from_dict(item) for item in value.get("tenants", [])
            ),
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "tenants": [item.to_dict() for item in self.tenants],
        }


@dataclass(frozen=True)
class BusinessSelection:
    type: str
    department_id: str
    department_name: str
    tenant_id: str
    tenant_name: str
    business_id: str
    team_id: str = ""
    team_name: str = ""

    @classmethod
    def from_dict(cls, value: Dict[str, Any]) -> "BusinessSelection":
        return cls(
            type=str(value.get("type", "")),
            department_id=str(value.get("department_id", "")),
            department_name=str(value.get("department_name", "")),
            tenant_id=str(value.get("tenant_id", "")),
            tenant_name=str(value.get("tenant_name", "")),
            business_id=str(value.get("businessId") or ""),
            team_id=str(value.get("team_id", "")),
            team_name=str(value.get("team_name", "")),
        )

    def to_dict(self) -> Dict[str, Any]:
        value = asdict(self)
        value["businessId"] = value.pop("business_id")
        return value


def _localized_name(value: Any, fallback: str) -> str:
    parsed = value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return value or fallback
    if isinstance(parsed, dict):
        return str(parsed.get("cn") or parsed.get("en") or fallback)
    return fallback


def parse_business_list(raw_value: Any) -> Tuple[Department, ...]:
    """将 localStorage 中的 ai-businessList 标准化为三层目录。"""
    value = raw_value
    if isinstance(raw_value, str):
        try:
            value = json.loads(raw_value)
        except json.JSONDecodeError as exc:
            raise BusinessError("ai-businessList 不是有效的 JSON") from exc
    if not isinstance(value, list):
        raise BusinessError("ai-businessList 顶层必须是数组")

    grouped: Dict[str, Dict[str, Any]] = {}
    for item in value:
        if not isinstance(item, dict):
            continue
        department_id = str(item.get("settleTenant") or "").strip()
        tenant_id = str(item.get("value") or "").strip()
        if not department_id or not tenant_id:
            continue
        department = grouped.setdefault(
            department_id,
            {
                "name": _localized_name(
                    item.get("settleTenantName"),
                    str(item.get("cn") or ""),
                ),
                "tenants": [],
            },
        )
        service_ids = tuple(
            str(service.get("serviceId"))
            for service in (item.get("serviceIdList") or [])
            if isinstance(service, dict) and service.get("serviceId")
        )
        teams: List[Team] = []
        for team_value in (item.get("teamList") or []):
            if not isinstance(team_value, dict):
                continue
            team_id = str(team_value.get("teamId") or "").strip()
            if not team_id:
                continue
            teams.append(
                Team(
                    id=team_id,
                    key=str(team_value.get("key") or "").strip(),
                    name=str(team_value.get("cn") or "").strip()
                    or _localized_name(team_value.get("name"), team_id),
                    status=str(team_value.get("teamStatus") or "").strip(),
                    business_id=str(
                        team_value.get("businessId") or ""
                    ).strip(),
                )
            )
        department["tenants"].append(
            Tenant(
                id=tenant_id,
                name=str(item.get("cn") or item.get("en") or tenant_id),
                service_ids=service_ids,
                teams=tuple(teams),
            )
        )

    departments = tuple(
        Department(
            id=department_id,
            name=str(value["name"]),
            tenants=tuple(value["tenants"]),
        )
        for department_id, value in grouped.items()
    )
    if not departments:
        raise BusinessError("ai-businessList 中没有有效的租户信息")
    return departments


class BusinessStore:
    """按环境保存业务目录和当前操作上下文。"""

    def __init__(self, path: Optional[Path] = None):
        self.path = (path or (user_config_dir() / "business.json")).expanduser()

    def refresh(
        self,
        profile: str,
        username: str,
        departments: Sequence[Department],
        browser_business_id: str = "",
    ) -> Optional[BusinessSelection]:
        data = self._read(reset_incompatible=True)
        old_entry = data.get("profiles", {}).get(profile, {})
        old_selection = (
            self._selection_from_entry(old_entry)
            if isinstance(old_entry, dict)
            and str(old_entry.get("username") or "") == username
            else None
        )
        catalog = tuple(departments)
        selection = self._validated_selection(catalog, old_selection)
        if selection is None and browser_business_id:
            selection = self._selection_for_business_id(
                catalog, browser_business_id
            )
        data.setdefault("profiles", {})[profile] = {
            "username": username,
            "updated_at": time.time(),
            "catalog": [item.to_dict() for item in catalog],
            "selected": selection.to_dict() if selection else None,
        }
        self._write(data)
        return selection

    def catalog(self, profile: str, username: str = "") -> Tuple[Department, ...]:
        entry = self._entry(profile, username)
        catalog = tuple(
            Department.from_dict(item) for item in entry.get("catalog", [])
        )
        if not catalog:
            raise BusinessError(
                "当前环境没有业务目录，请先运行 ml login 或 ml business refresh"
            )
        return catalog

    def selection(
        self,
        profile: str,
        username: str = "",
    ) -> Optional[BusinessSelection]:
        entry = self._entry(profile, username)
        return self._validated_selection(
            tuple(Department.from_dict(item) for item in entry.get("catalog", [])),
            self._selection_from_entry(entry),
        )

    def updated_at(self, profile: str) -> float:
        data = self._read(reset_incompatible=True)
        entry = data.get("profiles", {}).get(profile, {})
        if not isinstance(entry, dict):
            return 0.0
        value = entry.get("updated_at", 0)
        return float(value) if isinstance(value, (int, float)) else 0.0

    def require_selection(
        self,
        profile: str,
        username: str = "",
    ) -> BusinessSelection:
        selection = self.selection(profile, username)
        if selection is None:
            raise BusinessError(
                "尚未选择租户或团队，请运行 ml business use"
            )
        return selection

    def select(
        self,
        profile: str,
        username: str,
        tenant_id: str,
        team_id: str = "",
        department_id: str = "",
    ) -> BusinessSelection:
        data = self._read()
        entry = self._entry(profile, username, data)
        catalog = tuple(
            Department.from_dict(item) for item in entry.get("catalog", [])
        )
        matches = [
            (department, tenant)
            for department in catalog
            for tenant in department.tenants
            if tenant.id == tenant_id
            and (not department_id or department.id == department_id)
        ]
        if not matches:
            raise BusinessError(f"不存在租户: {tenant_id}")
        if len(matches) > 1:
            raise BusinessError(
                f"租户 ID {tenant_id!r} 不唯一，请同时指定 --department"
            )
        department, tenant = matches[0]
        selection = self._make_selection(department, tenant, team_id)
        entry["selected"] = selection.to_dict()
        self._write(data)
        return selection

    def _entry(
        self,
        profile: str,
        username: str,
        data: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        current = data if data is not None else self._read()
        entry = current.get("profiles", {}).get(profile)
        if not isinstance(entry, dict):
            raise BusinessError(
                "当前环境没有业务目录，请先运行 ml login 或 ml business refresh"
            )
        owner = str(entry.get("username") or "")
        if username and owner and owner != username:
            raise BusinessError(
                "业务目录属于其他账号，请运行 ml business refresh"
            )
        return entry

    @staticmethod
    def _selection_from_entry(entry: Any) -> Optional[BusinessSelection]:
        if not isinstance(entry, dict) or not isinstance(entry.get("selected"), dict):
            return None
        return BusinessSelection.from_dict(entry["selected"])

    def _validated_selection(
        self,
        catalog: Sequence[Department],
        selection: Optional[BusinessSelection],
    ) -> Optional[BusinessSelection]:
        if selection is None:
            return None
        try:
            return self._selection_from_catalog(
                catalog,
                selection.tenant_id,
                selection.team_id,
                selection.department_id,
            )
        except BusinessError:
            return None

    def _selection_for_business_id(
        self,
        catalog: Sequence[Department],
        business_id: str,
    ) -> Optional[BusinessSelection]:
        matches: List[BusinessSelection] = []
        for department in catalog:
            for tenant in department.tenants:
                if tenant.id == business_id:
                    matches.append(
                        self._make_selection(department, tenant, "")
                    )
                for team in tenant.teams:
                    if team.key == business_id and team.selectable:
                        matches.append(
                            self._make_selection(department, tenant, team.id)
                        )
        return matches[0] if len(matches) == 1 else None

    def _selection_from_catalog(
        self,
        catalog: Sequence[Department],
        tenant_id: str,
        team_id: str,
        department_id: str,
    ) -> BusinessSelection:
        for department in catalog:
            if department.id != department_id:
                continue
            for tenant in department.tenants:
                if tenant.id == tenant_id:
                    return self._make_selection(department, tenant, team_id)
        raise BusinessError("保存的业务上下文已失效")

    @staticmethod
    def _make_selection(
        department: Department,
        tenant: Tenant,
        team_id: str,
    ) -> BusinessSelection:
        if not team_id:
            return BusinessSelection(
                type="tenant",
                department_id=department.id,
                department_name=department.name,
                tenant_id=tenant.id,
                tenant_name=tenant.name,
                business_id=tenant.id,
            )
        team = next(
            (
                item
                for item in tenant.teams
                if item.id == team_id or item.key == team_id
            ),
            None,
        )
        if team is None:
            raise BusinessError(f"租户 {tenant.id!r} 下不存在团队: {team_id}")
        if not team.selectable:
            raise BusinessError(
                f"团队 {team.name!r} 当前状态为 {team.status!r}，不可选择"
            )
        if not team.business_id:
            raise BusinessError(
                f"团队 {team.name!r} 缺少 businessId，无法选择"
            )
        return BusinessSelection(
            type="team",
            department_id=department.id,
            department_name=department.name,
            tenant_id=tenant.id,
            tenant_name=tenant.name,
            team_id=team.id,
            team_name=team.name,
            business_id=team.business_id,
        )

    def _read(self, reset_incompatible: bool = False) -> Dict[str, Any]:
        if not self.path.exists():
            return {"version": 2, "profiles": {}}
        try:
            with self.path.open("r", encoding="utf-8") as file:
                value = json.load(file)
        except json.JSONDecodeError as exc:
            raise BusinessError(f"业务上下文文件已损坏: {self.path}") from exc
        if not isinstance(value, dict):
            raise BusinessError(f"业务上下文文件格式错误: {self.path}")
        if value.get("version") != 2:
            if reset_incompatible:
                return {"version": 2, "profiles": {}}
            raise BusinessError(
                "business.json 版本不兼容，请运行 ml login 或 "
                "ml business refresh 重新生成"
            )
        return value

    def _write(self, data: Dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(".tmp")
        with temporary.open("w", encoding="utf-8") as file:
            json.dump(data, file, ensure_ascii=False, indent=2)
            file.write("\n")
        try:
            os.chmod(temporary, 0o600)
        except OSError:
            pass
        temporary.replace(self.path)
