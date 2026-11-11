"""Supplier workflow and membership authorization on the existing internal accounts."""
from decimal import Decimal, InvalidOperation

from psycopg.rows import dict_row
from . import auth, postgres

PROFILE_FIELDS = ('name', 'entity_type', 'description', 'province', 'email', 'phone', 'delivery_areas')
STATUSES = ('pending', 'approved', 'rejected', 'suspended')


def profile_values(fields):
    if set(fields) - set(PROFILE_FIELDS):
        raise ValueError('Hồ sơ chứa trường không được phép cập nhật.')
    values = tuple(str(fields.get(key) or '').strip() for key in PROFILE_FIELDS)
    if not values[0]:
        raise ValueError('Vui lòng nhập tên đơn vị.')
    if values[4] and ('@' not in values[4] or '.' not in values[4].rsplit('@', 1)[-1]):
        raise ValueError('Email chưa đúng định dạng.')
    return values


def _supplier(connection, actor, supplier_id, *, selling=False):
    # Lock the supplier so review/suspension cannot race with a protected write.
    row = connection.cursor(row_factory=dict_row).execute(
        'SELECT * FROM business.suppliers WHERE id=%s FOR UPDATE', (supplier_id,)).fetchone()
    if row is None:
        raise auth.AccessDenied('Không tìm thấy đơn vị hoặc bạn không có quyền truy cập.')
    if actor['role'] != 'admin':
        member = connection.execute('''SELECT 1 FROM business.supplier_members
            WHERE supplier_id=%s AND user_id=%s FOR SHARE''', (supplier_id, actor['id'])).fetchone()
        if not member:
            raise auth.AccessDenied('Bạn không thuộc đơn vị này.')
    if selling and (actor['role'] != 'seller' or row['status'] != 'approved'):
        raise auth.AccessDenied('Nghiệp vụ người bán cần role seller, thành viên hợp lệ và hồ sơ đã duyệt.')
    return row


def create_application(session, fields):
    values = profile_values(fields)
    with postgres.transaction() as connection:
        actor = auth.require_user(connection, session, {'buyer', 'seller'})
        supplier_id = connection.execute('''INSERT INTO business.suppliers
            (name,entity_type,description,province,email,phone,delivery_areas,created_by)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id''', (*values, actor['id'])).fetchone()[0]
        connection.execute('INSERT INTO business.supplier_members(supplier_id,user_id) VALUES (%s,%s)',
                           (supplier_id, actor['id']))
    return supplier_id


def list_suppliers(session, *, admin=False, status=None):
    if status is not None and status not in STATUSES:
        raise ValueError('Trạng thái không hợp lệ.')
    with postgres.transaction() as connection:
        actor = auth.require_user(connection, session, {'admin'} if admin else {'buyer', 'seller', 'admin'})
        clauses, params = [], []
        if not admin:
            clauses.append('EXISTS (SELECT 1 FROM business.supplier_members m WHERE m.supplier_id=s.id AND m.user_id=%s)')
            params.append(actor['id'])
        if status:
            clauses.append('s.status=%s')
            params.append(status)
        where = ' WHERE ' + ' AND '.join(clauses) if clauses else ''
        return connection.cursor(row_factory=dict_row).execute(
            'SELECT s.* FROM business.suppliers s' + where + ' ORDER BY s.id DESC', params).fetchall()


def get_supplier(session, supplier_id):
    with postgres.transaction() as connection:
        actor = auth.require_user(connection, session)
        return _supplier(connection, actor, supplier_id)


def edit_profile(session, supplier_id, fields, *, resubmit=False):
    values = profile_values(fields)
    with postgres.transaction() as connection:
        actor = auth.require_user(connection, session, {'buyer', 'seller'})
        row = _supplier(connection, actor, supplier_id)
        if row['status'] == 'suspended':
            raise auth.AccessDenied('Đơn vị đang bị tạm ngưng.')
        if row['status'] == 'approved':
            _supplier(connection, actor, supplier_id, selling=True)
        if resubmit and row['status'] != 'rejected':
            raise ValueError('Chỉ hồ sơ bị từ chối được gửi duyệt lại.')
        connection.execute('''UPDATE business.suppliers SET name=%s,entity_type=%s,description=%s,
            province=%s,email=%s,phone=%s,delivery_areas=%s,updated_at=CURRENT_TIMESTAMP WHERE id=%s''',
            (*values, supplier_id))
        if resubmit:
            connection.execute('''UPDATE business.suppliers SET status='pending',reviewed_by=NULL,
                reviewed_at=NULL,rejection_reason='' WHERE id=%s''', (supplier_id,))


def review_application(session, supplier_id, status, reason=''):
    transitions = {'approved': {'pending', 'rejected', 'suspended'},
                   'rejected': {'pending'}, 'suspended': {'approved'}}
    if status not in transitions:
        raise ValueError('Thao tác duyệt không hợp lệ.')
    if status in ('rejected', 'suspended') and not reason.strip():
        raise ValueError('Vui lòng nhập lý do từ chối hoặc tạm ngưng.')
    with postgres.transaction() as connection:
        actor = auth.require_user(connection, session, {'admin'})
        row = _supplier(connection, actor, supplier_id)
        if row['status'] not in transitions[status]:
            raise ValueError('Trạng thái đã thay đổi hoặc không cho phép thao tác này.')
        connection.execute('''UPDATE business.suppliers SET status=%s,reviewed_by=%s,
            reviewed_at=CURRENT_TIMESTAMP,rejection_reason=%s,updated_at=CURRENT_TIMESTAMP WHERE id=%s''',
            (status, actor['id'], '' if status == 'approved' else reason.strip(), supplier_id))
        if status == 'approved':
            # Only this admin operation may promote members; suspension never demotes.
            connection.execute('''UPDATE business.users SET role='seller' WHERE role='buyer' AND id IN
                (SELECT user_id FROM business.supplier_members WHERE supplier_id=%s)''', (supplier_id,))


def catalog_items():
    """Read-only bridge. No PostgreSQL FK, writes, or brand-based inference."""
    import duckdb
    from . import database
    if not database.DUCKDB_PATH.is_file():
        return []
    with duckdb.connect(str(database.DUCKDB_PATH), read_only=True) as catalog:
        rows = catalog.execute('SELECT source,product_id,product_name FROM products ORDER BY source,product_id').fetchall()
    return [dict(zip(('source', 'product_id', 'product_name'), row)) for row in rows]


def _product_key(source, product_id):
    source, product_id = str(source).strip().upper(), str(product_id).strip()
    if not source or not product_id:
        raise ValueError('Khóa sản phẩm không được rỗng.')
    return source, product_id


def save_product(session, supplier_id, source, product_id, *, minimum_order=None, unit='',
                 preparation_time='', capacity_description='', is_active=True):
    source, product_id = _product_key(source, product_id)
    try:
        quantity = None if minimum_order in (None, '') else Decimal(str(minimum_order))
    except InvalidOperation:
        raise ValueError('Số lượng tối thiểu không hợp lệ.') from None
    if quantity is not None and (not quantity.is_finite() or quantity <= 0):
        raise ValueError('Số lượng tối thiểu phải lớn hơn 0 hoặc để trống.')
    if not isinstance(is_active, bool):
        raise ValueError('Trạng thái cung ứng không hợp lệ.')
    with postgres.transaction() as connection:
        actor = auth.require_user(connection, session, {'seller'})
        _supplier(connection, actor, supplier_id, selling=True)
        exists = any((p['source'], p['product_id']) == (source, product_id) for p in catalog_items())
        if not exists:
            raise ValueError('Sản phẩm không còn trong catalog. Chỉ có thể ngừng cung ứng liên kết lịch sử.')
        connection.execute('''INSERT INTO business.supplier_products
            (supplier_id,source,product_id,minimum_order,unit,preparation_time,capacity_description,is_active)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
            ON CONFLICT (supplier_id,source,product_id) DO UPDATE SET minimum_order=EXCLUDED.minimum_order,
            unit=EXCLUDED.unit,preparation_time=EXCLUDED.preparation_time,
            capacity_description=EXCLUDED.capacity_description,is_active=EXCLUDED.is_active,updated_at=CURRENT_TIMESTAMP''',
            (supplier_id, source, product_id, quantity, unit.strip(), preparation_time.strip(),
             capacity_description.strip(), is_active))


def stop_product(session, supplier_id, source, product_id):
    source, product_id = _product_key(source, product_id)
    with postgres.transaction() as connection:
        actor = auth.require_user(connection, session, {'seller'})
        _supplier(connection, actor, supplier_id, selling=True)
        row = connection.execute('''UPDATE business.supplier_products SET is_active=FALSE,
            updated_at=CURRENT_TIMESTAMP WHERE supplier_id=%s AND source=%s AND product_id=%s RETURNING product_id''',
            (supplier_id, source, product_id)).fetchone()
        if not row:
            raise ValueError('Không tìm thấy liên kết sản phẩm.')


def list_products(session, supplier_id):
    with postgres.transaction() as connection:
        actor = auth.require_user(connection, session)
        _supplier(connection, actor, supplier_id)
        rows = connection.cursor(row_factory=dict_row).execute('''SELECT * FROM business.supplier_products
            WHERE supplier_id=%s ORDER BY source,product_id''', (supplier_id,)).fetchall()
    catalog = {(p['source'], p['product_id']): p['product_name'] for p in catalog_items()}
    for row in rows:
        key = row['source'], row['product_id']
        row['in_catalog'] = key in catalog
        row['product_name'] = catalog.get(key, 'Sản phẩm không còn trong catalog') or 'Chưa cập nhật'
    return rows
