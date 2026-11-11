"""Lazy PostgreSQL connections, one transaction per context; no catalog imports."""
import os
from contextlib import contextmanager
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
    with psycopg.connect(url, connect_timeout=10, prepare_threshold=None) as connection:
        yield connection


def initialize_schema():
    """Explicit operator action; never run DDL during a form submission."""
    sql = Path(__file__).with_name('init_business_db.sql').read_text(encoding='utf-8')
    with transaction() as connection:
        connection.execute(sql)


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description='Initialize PostgreSQL business schema (no data copy)')
    parser.add_argument('--init-schema', action='store_true', required=True)
    parser.parse_args()
    initialize_schema()
