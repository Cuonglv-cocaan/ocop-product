"""Authorized business operations; identity comes from internal login."""
from contextlib import contextmanager

if __package__:
    from . import auth, postgres
else:
    import postgres
    import auth

KINDS = {'buyer': 'Nhận báo giá / tìm nguồn hàng', 'seller': 'Đăng ký nhà cung cấp'}


class LeadStorageError(RuntimeError):
    """Safe public error: never include connection strings or personal data."""


@contextmanager
def _operation():
    import psycopg
    try:
        if postgres.setting('LEADS_BACKEND').strip().lower() != 'postgres':
            raise LeadStorageError('Đăng nhập và yêu cầu có chủ sở hữu cần PostgreSQL.')
        with postgres.transaction() as connection:
            yield connection
    except auth.AccessDenied:
        raise
    except (psycopg.Error, OSError, ValueError):
        raise LeadStorageError('Không thể truy cập yêu cầu lúc này.') from None


def save_lead(kind, name, email, phone, note, *, session=None):
    with _operation() as connection:
        actor = auth.require_user(connection, session, {'buyer', 'seller'})
        if actor['role'] == 'seller':
            raise auth.AccessDenied('Đăng ký nhà cung cấp qua hồ sơ đơn vị; không tạo đăng ký mới trong leads.')
        if kind != KINDS[actor['role']]:
            raise auth.AccessDenied('Loại yêu cầu không thuộc vai trò của bạn.')
        values = tuple(value.strip() for value in (name, email, phone, note))
        if not all(values):
            raise ValueError('Required lead fields are empty')
        row = connection.execute('''INSERT INTO business.leads(kind,name,email,phone,note,user_id)
            VALUES (%s,%s,%s,%s,%s,%s) RETURNING id''', (kind, *values, actor['id'])).fetchone()
        lead_id = row[0]
    return lead_id


def save_guest_lead(kind, name, email, phone, note):
    """Accept public enquiries; unowned records remain visible only to admins."""
    if kind not in ('Nhu cầu mua hàng', 'Nhờ tìm sản phẩm'):
        raise ValueError('Vui lòng chọn loại yêu cầu hợp lệ.')
    name, email, phone, note = (str(v or '').strip() for v in (name, email, phone, note))
    if not name or not note or not (email or phone):
        raise ValueError('Nhập tên, nội dung và ít nhất email hoặc số điện thoại.')
    if email and ('@' not in email or '.' not in email.rsplit('@', 1)[-1]):
        raise ValueError('Email chưa đúng định dạng.')
    if any(len(v) > limit for v, limit in ((name, 200), (email, 254), (phone, 30), (note, 5000))):
        raise ValueError('Thông tin vượt quá độ dài cho phép.')
    with _operation() as connection:
        row = connection.execute('''INSERT INTO business.leads(kind,name,email,phone,note,user_id)
            VALUES (%s,%s,%s,%s,%s,NULL) RETURNING id''', (kind, name, email, phone, note)).fetchone()
    return row[0]


def read_leads(session, lead_id=None):
    with _operation() as connection:
        actor = auth.require_user(connection, session, {'buyer', 'seller', 'admin'})
        clauses, params = [], []
        if actor['role'] != 'admin':
            clauses.extend(['user_id=%s', 'kind=%s'])
            params.extend([actor['id'], KINDS[actor['role']]])
        if lead_id is not None:
            clauses.append('id=%s')
            params.append(lead_id)
        where = ' WHERE ' + ' AND '.join(clauses) if clauses else ''
        rows = connection.execute('''SELECT id,created_at,kind,name,email,phone,note,user_id
            FROM business.leads''' + where + ' ORDER BY id DESC', params).fetchall()
    return [dict(zip(('id', 'created_at', 'kind', 'name', 'email', 'phone', 'note', 'user_id'), row)) for row in rows]


def update_note(session, lead_id, note):
    with _operation() as connection:
        actor = auth.require_user(connection, session, {'buyer', 'seller', 'admin'})
        if not note.strip():
            raise ValueError('Note is required')
        if actor['role'] == 'admin':
            row = connection.execute('UPDATE business.leads SET note=%s WHERE id=%s RETURNING id',
                                     (note.strip(), lead_id)).fetchone()
        else:
            row = connection.execute('''UPDATE business.leads SET note=%s
                WHERE id=%s AND user_id=%s AND kind=%s RETURNING id''',
                (note.strip(), lead_id, actor['id'], KINDS[actor['role']])).fetchone()
        if row is None:
            raise auth.AccessDenied('Không tìm thấy yêu cầu hoặc bạn không có quyền sửa.')
