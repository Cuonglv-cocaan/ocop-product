"""Business storage boundary. Backend changes require explicit configuration."""
import sqlite3

if __package__:
    from . import postgres, sqlite_leads
else:
    import postgres
    import sqlite_leads


class LeadStorageError(RuntimeError):
    """Safe public error: never include connection strings or personal data."""


def save_lead(kind: str, name: str, email: str, phone: str, note: str) -> int:
    try:
        backend = postgres.setting('LEADS_BACKEND').strip().lower()
        if backend == 'sqlite':
            return sqlite_leads.save_lead(kind, name, email, phone, note)
        if backend != 'postgres':
            raise ValueError('Unsupported LEADS_BACKEND')
        return _save_postgres(kind, name, email, phone, note)
    except (sqlite3.Error, OSError, ValueError, ImportError):
        raise LeadStorageError('Unable to save contact request') from None


def _save_postgres(kind, name, email, phone, note):
    import psycopg
    try:
        with postgres.transaction() as connection:
            row = connection.execute(
                '''INSERT INTO business.leads (kind, name, email, phone, note)
                   VALUES (%s, %s, %s, %s, %s) RETURNING id''',
                (kind, name.strip(), email.strip(), phone.strip(), note.strip()),
            ).fetchone()
            lead_id = row[0]
        # The context must finish committing before the caller can show success.
        return lead_id
    except psycopg.Error:
        raise LeadStorageError('Unable to save contact request') from None
