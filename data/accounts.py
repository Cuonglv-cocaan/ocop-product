"""Explicit operator commands: seed missing accounts or reset a password."""
import argparse
import getpass
import json
import os

import psycopg
from . import auth, postgres

DEMO_ACCOUNTS = [('buyer01', 'buyer'), ('buyer02', 'buyer'),
                 ('seller01', 'seller'), ('seller02', 'seller'), ('admin01', 'admin')]


def seed_accounts(password):
    if not password:
        raise ValueError('Password is required')
    created = 0
    with postgres.transaction() as connection:
        for username, role in DEMO_ACCOUNTS:
            row = connection.execute('''INSERT INTO business.users(username,password_hash,role)
                VALUES (%s,%s,%s) ON CONFLICT (username) DO NOTHING RETURNING id''',
                (auth.normalize_username(username), auth.HASHER.hash(password), role)).fetchone()
            created += int(row is not None)
    return {'created': created, 'skipped': len(DEMO_ACCOUNTS) - created}


def reset_password(username, password):
    if not password:
        raise ValueError('Password is required')
    hashed = auth.HASHER.hash(password)
    with postgres.transaction() as connection:
        row = connection.execute('''UPDATE business.users SET password_hash=%s,
            auth_version=auth_version+1 WHERE username=%s RETURNING id''',
            (hashed, auth.normalize_username(username))).fetchone()
        if row is None:
            raise ValueError('Account does not exist')


def list_accounts(session):
    with postgres.transaction() as connection:
        auth.require_user(connection, session, {'admin'})
        rows = connection.execute('SELECT id,username,role,active FROM business.users ORDER BY id').fetchall()
    return [dict(zip(('id', 'username', 'role', 'active'), row)) for row in rows]


def set_active(session, user_id, active):
    if not isinstance(active, bool):
        raise ValueError('Invalid active flag')
    with postgres.transaction() as connection:
        actor = auth.require_user(connection, session, {'admin'})
        if actor['id'] == user_id:
            raise auth.AccessDenied('Không thể tự khóa tài khoản đang đăng nhập.')
        row = connection.execute('''UPDATE business.users SET active=%s,auth_version=auth_version+1
            WHERE id=%s RETURNING id''', (active, user_id)).fetchone()
        if not row:
            raise ValueError('Account does not exist')


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    commands.add_parser('seed')
    reset = commands.add_parser('set-password')
    reset.add_argument('--username', required=True)
    args = parser.parse_args(argv)
    try:
        # No password defaults or command-line arguments; prompt if unset.
        password = os.environ.get('DEMO_ACCOUNT_PASSWORD') or getpass.getpass('Password: ')
        if args.command == 'seed':
            print(json.dumps(seed_accounts(password)))
        else:
            reset_password(args.username, password)
            print(json.dumps({'password_updated': True}))
    except (ValueError, psycopg.Error, OSError, EOFError):
        print(json.dumps({'error': 'Account operation failed; check configuration and schema'}))
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
