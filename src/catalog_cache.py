"""Cache only public catalog data; private business records always read fresh."""
from pathlib import Path

import streamlit as st
from data import database, suppliers


def catalog_version():
    """Include the WAL: uncheckpointed DuckDB writes may not change the DB file."""
    path = Path(database.DUCKDB_PATH).resolve()
    signatures = []
    for candidate in (path, Path(str(path) + '.wal')):
        try:
            stat = candidate.stat()
        except FileNotFoundError:
            signatures.append(None)
        else:
            signatures.append((stat.st_mtime_ns, stat.st_size))
    return str(path), *signatures


@st.cache_data(ttl=600, max_entries=8, show_spinner=False)
def _catalog_items(version):
    return suppliers.catalog_items()


def catalog_items():
    return _catalog_items(catalog_version())
