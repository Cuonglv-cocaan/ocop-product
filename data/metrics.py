"""Admin-only cohort metrics, computed from persisted business records."""
from datetime import datetime, time, timedelta
from statistics import median
from zoneinfo import ZoneInfo

from psycopg.rows import dict_row
from . import auth, postgres

ZONE = ZoneInfo('Asia/Ho_Chi_Minh')


def _hours(start, end):
    return (end - start).total_seconds() / 3600


def summarize(requests, matches, quotes, events, *, supplier_id=None):
    """Inputs are a creation-date cohort plus all its records through viewing time.

    Supplier filter narrows cohort to requests assigned to it and measures only its
    assignments/quotes; selected/connected remain request outcomes, not attribution.
    """
    cohort = {r['id']: r for r in requests}
    if supplier_id is not None:
        assigned_to = {m['request_id'] for m in matches if m['supplier_id'] == supplier_id}
        cohort = {rid: r for rid, r in cohort.items() if rid in assigned_to}
    matches = [m for m in matches if m['request_id'] in cohort and
               (supplier_id is None or m['supplier_id'] == supplier_id)]
    match_map = {m['id']: m for m in matches}
    quotes = [q for q in quotes if q['match_id'] in match_map]
    events = [e for e in events if e['request_id'] in cohort]
    first_quote, first_response = {}, {}
    for q in quotes:
        mid, at = q['match_id'], q['created_at']
        if at >= match_map[mid]['assigned_at']:
            first_quote[mid] = min(first_quote.get(mid, at), at)
            first_response[mid] = min(first_response.get(mid, at), at)
    for e in events:
        mid, at = e.get('match_id'), e['created_at']
        if mid in match_map and e['event_type'] in ('declined', 'quoted') and at >= match_map[mid]['assigned_at']:
            first_response[mid] = min(first_response.get(mid, at), at)
    assigned = {m['request_id'] for m in matches}
    quoted = {match_map[mid]['request_id'] for mid in first_quote}
    # Durations use individual assignments, not the first supplier assigned to a
    # request. Versioned quotes contribute only their match's earliest timestamp.
    latencies = [_hours(match_map[mid]['assigned_at'], at) for mid, at in first_quote.items()]
    selected = {e['request_id'] for e in events if e['event_type'] == 'selected'}
    selected |= {r['id'] for r in cohort.values() if r.get('selected_quote_id') is not None}
    supplier_rows = []
    for sid in sorted({m['supplier_id'] for m in matches}):
        items = [m for m in matches if m['supplier_id'] == sid]
        response_hours = [_hours(m['assigned_at'], first_response[m['id']])
                          for m in items if m['id'] in first_response]
        supplier_rows.append({'supplier_id': sid, 'supplier_name': items[0]['supplier_name'],
                              'assigned': len(items),
                              'responded': sum(m['id'] in first_response for m in items),
                              'quoted': sum(m['id'] in first_quote for m in items),
                              'median_response_hours': median(response_hours) if response_hours else None})
    return {'created': len(cohort), 'assigned': len(assigned), 'quoted_requests': len(quoted),
            'quote_rate': len(quoted) / len(assigned) if assigned else None,
            'median_first_quote_hours': median(latencies) if latencies else None,
            'selected': len(selected),
            'connected': sum(r['status'] == 'connected' for r in cohort.values()),
            'cancelled': sum(r['status'] == 'cancelled' for r in cohort.values()),
            'closed_no_match': sum(r['status'] == 'closed_no_match' for r in cohort.values()),
            'suppliers': supplier_rows}


def dashboard(session, start_date, end_date, *, supplier_id=None):
    if start_date > end_date:
        raise ValueError('Ngày bắt đầu phải trước hoặc bằng ngày kết thúc.')
    start = datetime.combine(start_date, time.min, ZONE)
    end = datetime.combine(end_date + timedelta(days=1), time.min, ZONE)
    with postgres.transaction() as connection:
        # All reads see one committed snapshot; no cached/private cross-session data.
        connection.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ')
        auth.require_user(connection, session, {'admin'})
        cursor = connection.cursor(row_factory=dict_row)
        viewed_at = cursor.execute('SELECT CURRENT_TIMESTAMP AS at').fetchone()['at']
        requests = cursor.execute('''SELECT id,status,selected_quote_id
            FROM business.purchase_requests WHERE created_at >= %s AND created_at < %s''', (start, end)).fetchall()
        ids = [r['id'] for r in requests]
        matches = cursor.execute('''SELECT m.*,s.name AS supplier_name
            FROM business.request_matches m JOIN business.suppliers s ON s.id=m.supplier_id
            WHERE m.request_id=ANY(%s)''', (ids,)).fetchall()
        quotes = cursor.execute('''SELECT request_id,match_id,created_at FROM business.request_quotes
            WHERE request_id=ANY(%s)''', (ids,)).fetchall()
        events = cursor.execute('''SELECT request_id,match_id,event_type,created_at FROM business.request_events
            WHERE request_id=ANY(%s)''', (ids,)).fetchall()
    result = summarize(requests, matches, quotes, events, supplier_id=supplier_id)
    result['viewed_at'] = viewed_at
    return result
