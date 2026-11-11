"""Internal demo login. Sessions contain signed identity, never a client role."""
import hashlib
import hmac
import re
import secrets
from dataclasses import dataclass

from argon2 import PasswordHasher
from argon2.exceptions import VerificationError, InvalidHashError

if __package__:
    from . import postgres
else:
    import postgres

HASHER = PasswordHasher()
_SIGNING_KEY = secrets.token_bytes(32)
_DUMMY_HASH = HASHER.hash(secrets.token_urlsafe(32))


class AccessDenied(PermissionError):
    pass


@dataclass(frozen=True)
class Session:
    user_id: int
    version: int
    signature: str


def normalize_username(username):
    value = username.strip().lower()
    if not re.fullmatch(r'[a-z0-9_]{3,32}', value):
        raise ValueError('Username must contain 3–32 ASCII letters, digits or underscores')
    return value


def _signature(user_id, version):
    return hmac.new(_SIGNING_KEY, f'{user_id}:{version}'.encode(), hashlib.sha256).hexdigest()


def authenticate(username, password):
    try:
        username = normalize_username(username)
    except ValueError:
        username = ''
    with postgres.transaction() as connection:
        row = connection.execute('''SELECT id,password_hash,active,auth_version
            FROM business.users WHERE username=%s FOR SHARE''', (username,)).fetchone()
        try:
            valid = HASHER.verify(row[1] if row else _DUMMY_HASH, password)
        except (VerificationError, InvalidHashError):
            valid = False
        if not row or not valid or not row[2]:
            raise AccessDenied('Tên đăng nhập hoặc mật khẩu không đúng, hoặc tài khoản đã bị khóa.')
        session = Session(row[0], row[3], _signature(row[0], row[3]))
    return session


def require_user(connection, session, roles=None):
    if not isinstance(session, Session) or not isinstance(session.signature, str) or not hmac.compare_digest(
            session.signature, _signature(session.user_id, session.version)):
        raise AccessDenied('Vui lòng đăng nhập.')
    row = connection.execute('''SELECT id,username,role,active,auth_version
        FROM business.users WHERE id=%s FOR SHARE''', (session.user_id,)).fetchone()
    if not row or not row[3] or row[4] != session.version:
        raise AccessDenied('Phiên đăng nhập đã hết hiệu lực. Vui lòng đăng nhập lại.')
    if roles is not None and row[2] not in roles:
        raise AccessDenied('Bạn không có quyền thực hiện thao tác này.')
    return {'id': row[0], 'username': row[1], 'role': row[2], 'active': row[3]}


def current_user(session):
    with postgres.transaction() as connection:
        return require_user(connection, session)


def logout(state):
    # Clear drafts, chat history, widget values and private results as well as identity.
    state.clear()
