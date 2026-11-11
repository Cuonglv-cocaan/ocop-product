"""Lazy PostgreSQL connections, one transaction per context; no catalog imports."""
import os
import hashlib
from contextlib import closing, contextmanager
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[1] / '.env')


def setting(name, default=''):
    """Environment (including .env) first, then root-level Streamlit secrets."""
    if name in os.environ:
        return os.environ[name]
    import streamlit as st
    from streamlit.errors import StreamlitSecretNotFoundError
    try:
        return st.secrets.get(name, default)
    except StreamlitSecretNotFoundError:
        return default


@contextmanager
def transaction():
    """Commit on success, rollback on error, always close; pooler compatible."""
    url = setting('DATABASE_URL').strip()
    if not url:
        raise ValueError('DATABASE_URL is required for PostgreSQL')
    import psycopg
    # close() must also run if COMMIT itself raises.
    with closing(psycopg.connect(url, connect_timeout=10, prepare_threshold=None)) as connection, connection:
        # Nested transaction contexts must be savepoints from the first row.
        with connection.transaction():
            yield connection


def initialize_schema():
    """Apply versioned SQL atomically, with locking and checksum validation."""
    with transaction() as connection:
        connection.execute('SELECT pg_advisory_xact_lock(674091824)')
        connection.execute('CREATE SCHEMA IF NOT EXISTS business')
        connection.execute('''CREATE TABLE IF NOT EXISTS business.schema_migrations (
            version TEXT PRIMARY KEY, checksum TEXT NOT NULL,
            applied_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP)''')
        for path in sorted(Path(__file__).with_name('migrations').glob('[0-9]*.sql')):
            sql = path.read_text(encoding='utf-8')
            checksum = hashlib.sha256(sql.encode('utf-8')).hexdigest()
            previous = connection.execute(
                'SELECT checksum FROM business.schema_migrations WHERE version=%s',
                (path.name,),
            ).fetchone()
            if previous:
                if previous[0] != checksum:
                    raise ValueError(f'Applied migration changed: {path.name}')
                continue
            connection.execute(sql)
            connection.execute(
                'INSERT INTO business.schema_migrations(version,checksum) VALUES (%s,%s)',
                (path.name, checksum),
            )


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description='Initialize PostgreSQL business schema (no data copy)')
    parser.add_argument('--init-schema', action='store_true', required=True)
    parser.parse_args()
    initialize_schema()
