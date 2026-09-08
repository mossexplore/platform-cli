import hashlib
import hmac
import secrets
from urllib.parse import urlsplit
from datetime import datetime, timezone, timedelta
from fastapi import HTTPException

BEIJING = timezone(timedelta(hours=8))


def password_hash(password):
    if len(password) < 12 or len(password) > 256:
        raise ValueError('管理员密码须为 12–256 个字符')
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac('sha256', password.encode(), salt.encode(), 600000).hex()
    return f'pbkdf2_sha256$600000${salt}${digest}'


def password_matches(password, encoded):
    try:
        _, rounds, salt, expected = encoded.split('$')
        digest = hashlib.pbkdf2_hmac('sha256', password.encode(), salt.encode(), int(rounds)).hex()
        return hmac.compare_digest(digest, expected)
    except (ValueError, TypeError):
        return False


def digest(value):
    return hashlib.sha256(value.encode()).hexdigest()


def origin(value):
    try:
        parsed = urlsplit(value)
        if parsed.scheme not in ('http', 'https') or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment:
            raise ValueError()
        if parsed.path not in ('', '/'):
            raise ValueError()
        _ = parsed.port
        return f'{parsed.scheme}://{parsed.netloc.lower()}'
    except ValueError:
        raise HTTPException(400, '平台地址必须是 HTTP 或 HTTPS 源地址，例如 http://platform.example.com:8080，不含路径或凭据')


def expiry(value):
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=BEIJING)
        return parsed.astimezone(timezone.utc).replace(tzinfo=None)
    except ValueError:
        raise HTTPException(400, '失效时间格式错误')


def display_time(value):
    return value.replace(tzinfo=timezone.utc).astimezone(BEIJING).strftime('%Y-%m-%d %H:%M:%S') if value else '不限'
