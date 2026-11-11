"""Explicit SQLite -> PostgreSQL import; source stays read-only."""
import argparse
import json
import sqlite3
from contextlib import closing
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

import psycopg
from . import postgres


@dataclass
class Report:
    total: int = 0
    inserted: int = 0
    skipped: int = 0
    failed: int = 0
    would_insert: int = 0
    dry_run: bool = False
    error: str | None = None


def values_for(row):
    if not isinstance(row['id'], int) or row['id'] <= 0:
        raise ValueError('Invalid source ID')
    timestamp = datetime.fromisoformat(row['created_at'])
    if timestamp.tzinfo is None or timestamp.utcoffset() is None:
        raise ValueError('Timestamp needs a timezone')
    values = [timestamp.astimezone(timezone.utc)]
    for field in ('kind', 'name', 'email', 'phone', 'note'):
        value = row[field]
        if not isinstance(value, str):
            raise ValueError('Invalid source text')
        values.append(value)
    legacy = row['legacy_duckdb_id'] if 'legacy_duckdb_id' in row.keys() else None
    if legacy is not None and not isinstance(legacy, int):
        raise ValueError('Invalid legacy ID')
    return (*values, legacy)


def migrate(source: Path, source_id: str, *, dry_run: bool) -> Report:
    source_id = source_id.strip()
    if not source_id:
        raise ValueError('Stable source-id required')
    source = Path(source).resolve(strict=True)
    with closing(sqlite3.connect(source.as_uri() + '?mode=ro', uri=True)) as sqlite:
        sqlite.row_factory = sqlite3.Row
        sqlite.execute('PRAGMA query_only=ON')
        sqlite.execute('BEGIN')
        rows = sqlite.execute('SELECT * FROM leads ORDER BY id').fetchall()
    report = Report(total=len(rows), dry_run=dry_run)
    try:
        with postgres.transaction() as connection:
            if dry_run:
                connection.execute('SET TRANSACTION READ ONLY')
            for row in rows:
                try:
                    values = values_for(row)
                    with connection.transaction():
                        inserted = None
                        if not dry_run:
                            inserted = connection.execute('''
                                INSERT INTO business.leads
                                (created_at,kind,name,email,phone,note,legacy_duckdb_id,
                                 legacy_sqlite_source,legacy_sqlite_id)
                                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
                                ON CONFLICT (legacy_sqlite_source,legacy_sqlite_id)
                                DO NOTHING RETURNING id
                            ''', (*values, source_id, row['id'])).fetchone()
                        if inserted:
                            report.inserted += 1
                        else:
                            existing = connection.execute('''
                                SELECT created_at,kind,name,email,phone,note,legacy_duckdb_id
                                FROM business.leads
                                WHERE legacy_sqlite_source=%s AND legacy_sqlite_id=%s
                            ''', (source_id, row['id'])).fetchone()
                            if existing is None and dry_run:
                                report.would_insert += 1
                            elif existing == values:
                                report.skipped += 1
                            else:
                                raise ValueError('Conflicting source contents')
                except (ValueError, TypeError, KeyError, IndexError, psycopg.DataError, psycopg.IntegrityError):
                    report.failed += 1
        # Return success counts only after the outer transaction commits.
    except (psycopg.Error, ValueError, OSError):
        report.inserted = report.skipped = report.would_insert = 0
        report.failed = report.total
        report.error = 'Destination transaction failed; rerun with the same source-id to verify outcome'
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--source-id', required=True)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--dry-run', action='store_true')
    mode.add_argument('--apply', action='store_true')
    args = parser.parse_args(argv)
    try:
        report = migrate(args.source, args.source_id, dry_run=args.dry_run)
    except (OSError, sqlite3.Error, ValueError):
        print(json.dumps({'error': 'Cannot read source or invalid source-id; no rows imported'}))
        return 1
    print(json.dumps(asdict(report)))
    return 1 if report.failed or report.error else 0


if __name__ == '__main__':
    raise SystemExit(main())
