import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import hashlib
import json
import sqlite3
from contextlib import closing
from dataclasses import asdict
from datetime import datetime, timezone
from data import postgres, migrate_leads, sqlite_leads


def main():
    source = sqlite_leads.SQLITE_LEADS_PATH.resolve(strict=True)
    before = hashlib.sha256(source.read_bytes()).hexdigest()
    source_id = 'local-main'
    with closing(sqlite3.connect(source.as_uri() + '?mode=ro', uri=True)) as connection:
        connection.row_factory = sqlite3.Row
        connection.execute('PRAGMA query_only=ON')
        connection.execute('BEGIN')
        rows = connection.execute('SELECT * FROM leads ORDER BY id').fetchall()
        for row in rows:
            migrate_leads.values_for(row)
        backup_dir = source.parent / 'backups'
        backup_dir.mkdir(exist_ok=True)
        backup = backup_dir / ('leads-before-postgres-' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ') + '.sqlite3')
        with closing(sqlite3.connect(backup)) as target:
            connection.backup(target)
    print(json.dumps({'source_rows': len(rows), 'backup_created': True}), flush=True)
    postgres.initialize_schema()
    print(json.dumps({'schema_migrations_applied': True}), flush=True)
    preview = migrate_leads.migrate(source, source_id, dry_run=True)
    print(json.dumps({'dry_run': asdict(preview)}), flush=True)
    if preview.failed or preview.error:
        raise RuntimeError('Dry run failed')
    applied = migrate_leads.migrate(source, source_id, dry_run=False)
    print(json.dumps({'apply': asdict(applied)}), flush=True)
    if applied.failed or applied.error:
        raise RuntimeError('Apply failed')
    repeat = migrate_leads.migrate(source, source_id, dry_run=False)
    print(json.dumps({'repeat': asdict(repeat)}), flush=True)
    if repeat.failed or repeat.error or repeat.inserted or repeat.skipped != len(rows):
        raise RuntimeError('Repeat verification failed')
    with postgres.transaction() as connection:
        connection.execute('SET TRANSACTION READ ONLY')
        for row in rows:
            actual = connection.execute('''SELECT created_at,kind,name,email,phone,note,legacy_duckdb_id
                FROM business.leads WHERE legacy_sqlite_source=%s AND legacy_sqlite_id=%s''',
                (source_id, row['id'])).fetchone()
            if actual != migrate_leads.values_for(row):
                raise RuntimeError('Content verification failed')
        versions = connection.execute('SELECT version FROM business.schema_migrations ORDER BY version').fetchall()
    unchanged = hashlib.sha256(source.read_bytes()).hexdigest() == before
    print(json.dumps({'verified_rows': len(rows), 'source_unchanged': unchanged,
                      'versions': [v[0] for v in versions]}), flush=True)
    if not unchanged:
        raise RuntimeError('Source changed during import')


if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        print(json.dumps({'operation_failed': True, 'error_type': type(error).__name__}), flush=True)
        raise SystemExit(1)
