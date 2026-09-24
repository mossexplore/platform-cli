"""统一策略求值：缺少版本按 1.0.0，非法版本不降级为旧版。"""
import json
import re
from sqlalchemy import or_, select
from .models import now
from .version_models import VersionPolicy, VersionException

VERSION = re.compile(r'(0|[1-9][0-9]{0,8})(?:\.(0|[1-9][0-9]{0,8})){2,3}', re.ASCII)


def version_tuple(value):
    if not isinstance(value, str) or not VERSION.fullmatch(value):
        raise ValueError('版本须为三段或四段数字，例如 1.0.3 或 1.0.3.2（每段最多 9 位，不含前导零）')
    parts = tuple(map(int, value.split('.')))
    return parts + (0,) * (4 - len(parts))


def metadata(request):
    headers = request.headers
    values = headers.getlist('x-cli-version')
    raw = values[0] if len(values) == 1 else (None if not values else ','.join(values))
    version = '1.0.0' if raw is None else raw
    protocols = headers.getlist('x-cli-protocol-version')
    protocol = protocols[0] if len(protocols) == 1 else ('1' if not protocols else ','.join(protocols))
    # Header presence determines legacy status, never the optional client name.
    return {'version': version[:64], 'valid': bool(VERSION.fullmatch(version)),
            'source': 'legacy_default' if raw is None else 'reported',
            'protocol': protocol[:32], 'protocol_valid': protocol == '1',
            'installation_id': headers.get('x-cli-installation-id', '')[:64],
            'invocation_id': headers.get('x-cli-invocation-id', '')[:64],
            'request_id': headers.get('x-request-id', '')[:64]}


def policies_for(db, environment, business_id, timestamp):
    return db.scalars(select(VersionPolicy).where(
        VersionPolicy.enabled.is_(True), VersionPolicy.deleted_at.is_(None), VersionPolicy.effective_at <= timestamp,
        or_(VersionPolicy.environment == '', VersionPolicy.environment == environment),
        or_(VersionPolicy.business_id == '', VersionPolicy.business_id == business_id)
    ).order_by(VersionPolicy.id)).all()


def evaluate_version(db, environment, business_id, username, info, timestamp=None, policies=None):
    timestamp = timestamp or now()
    policies = policies if policies is not None else policies_for(db, environment, business_id, timestamp)
    exceptions = db.scalars(select(VersionException).where(
        VersionException.enabled.is_(True), VersionException.expires_at > timestamp,
        VersionException.environment == environment, VersionException.business_id == business_id,
        VersionException.username == username)).all()
    checks, enforced, warned, exemptions = [], [], [], []
    current = version_tuple(info['version']) if info['valid'] else None
    recommendations = []
    for policy in policies:
        reason = None
        if not info['valid']:
            reason = 'CLI_VERSION_INVALID'
        elif not info['protocol_valid']:
            reason = 'CLI_PROTOCOL_UNSUPPORTED'
        elif any(current == version_tuple(blocked) for blocked in json.loads(policy.blocked_versions)):
            reason = 'CLI_VERSION_BLOCKED'
        elif current < version_tuple(policy.minimum_version):
            reason = 'CLI_VERSION_TOO_OLD'
        exempt = (reason == 'CLI_VERSION_TOO_OLD' and any(
            item.policy_id == policy.id and version_tuple(item.minimum_version) <= current <= version_tuple(item.maximum_version)
            for item in exceptions))
        if exempt:
            exemptions.append(policy.id)
        checks.append({'policy_id': policy.id, 'mode': policy.mode, 'reason': reason or 'ALLOWED', 'exempt': exempt})
        if policy.mode != 'observe' and policy.recommended_version:
            recommendations.append(policy.recommended_version)
        if policy.mode == 'enforce' and not exempt:
            enforced.append(policy)
        if policy.mode != 'observe' and not exempt and (reason or (
                current and policy.recommended_version and current < version_tuple(policy.recommended_version))):
            warned.append(policy)
    denials = [c for c in checks if c['mode'] == 'enforce' and c['reason'] != 'ALLOWED' and not c['exempt']]
    priority = {'CLI_VERSION_BLOCKED': 0, 'CLI_VERSION_INVALID': 1, 'CLI_PROTOCOL_UNSUPPORTED': 2, 'CLI_VERSION_TOO_OLD': 3}
    by_id = {p.id: p for p in policies}
    denial = min(denials, key=lambda c: (priority[c['reason']],
        tuple(-n for n in version_tuple(by_id[c['policy_id']].minimum_version)))) if denials else None
    chosen = next((p for p in policies if denial and p.id == denial['policy_id']), None)
    if chosen is None and warned:
        chosen = max(warned, key=lambda p: version_tuple(p.minimum_version))
    minimum = max((p.minimum_version for p in enforced), key=version_tuple, default='')
    return {'allowed': denial is None, 'reason': denial['reason'] if denial else 'ALLOWED',
            'current_version': info['version'], 'version_source': info['source'],
            'minimum_version': minimum,
            'recommended_version': max(recommendations + ([minimum] if minimum else []), key=version_tuple, default=''),
            'upgrade_url': chosen.upgrade_url if chosen else '',
            'warning': bool(warned) and denial is None,
            'policy_revision': max((p.id for p in policies), default=0),
            'policy_ids': [p.id for p in policies], 'checks': checks, 'exception_policy_ids': exemptions}
