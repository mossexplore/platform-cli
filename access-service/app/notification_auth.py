"""One configured owner and one scoped, revocable machine credential."""
import secrets
from fastapi import HTTPException
from sqlalchemy import update
from .admin_auth import admin_session, authorize_form
from .models import Admin, now
from .notification_models import NotificationClient
from .security import digest


def fail(code, status=409):
    raise HTTPException(status, code)


def lock_client(db):
    # Serialize protocol mutations on MySQL AND SQLite; SELECT FOR UPDATE alone
    # does not serialize writers on SQLite. This is one client, not a global queue.
    db.execute(update(NotificationClient).where(NotificationClient.id == 1)
               .values(revision=NotificationClient.revision + 1))
    client = db.get(NotificationClient, 1)
    if client is None:
        fail('NOTIFICATION_SCHEMA_NOT_READY', 503)
    return client


def owner(request, db, csrf=None):
    actor, session = admin_session(request, db)
    if actor.id != request.app.state.settings.notification_owner_admin_id:
        fail('NOTIFICATION_OWNER_REQUIRED', 403)
    if csrf is not None:
        authorize_form(request, db, csrf)
    client = lock_client(db)
    if client.owner_admin_id not in (None, actor.id):
        fail('OWNER_CONFIGURATION_CHANGED', 403)
    return actor, session, client


def machine(request, db, body, binding=False):
    if body.protocol_version != 1:
        fail('UNSUPPORTED_PROTOCOL', 400)
    client = lock_client(db)
    header = request.headers.get('authorization', '')
    token = header[7:] if header.startswith('Bearer ') else ''
    if not token or len(token) > 256 or not client.token_hash or not secrets.compare_digest(
            digest(token), client.token_hash):
        fail('TOKEN_INVALID', 401)
    admin = db.get(Admin, client.owner_admin_id) if client.owner_admin_id else None
    if not admin or not admin.enabled or admin.role not in ('admin', 'super_admin') or (
            admin.id != request.app.state.settings.notification_owner_admin_id):
        fail('OWNER_DISABLED', 403)
    if client.installation_id:
        if not client.expires_at or client.expires_at <= now():
            fail('TOKEN_EXPIRED', 401)
        if client.installation_id != body.installation_id:
            fail('INSTANCE_MISMATCH')
    elif not binding:
        fail('BIND_REQUIRED')
    elif not client.bind_deadline or client.bind_deadline <= now():
        fail('TOKEN_EXPIRED', 401)
    return client
