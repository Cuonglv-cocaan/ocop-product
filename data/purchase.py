"""Manual procurement workflow. Every operation checks identity and database scope."""
from datetime import date, datetime
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP, localcontext
from zoneinfo import ZoneInfo

from psycopg.rows import dict_row
from . import auth, postgres, suppliers

ZONE = ZoneInfo('Asia/Bangkok')
TERMINAL = {'connected', 'cancelled', 'closed_no_match'}
REQUEST_FIELDS = ('title', 'category', 'description', 'quantity', 'unit', 'budget', 'budget_type',
                  'delivery_location', 'delivery_deadline', 'additional_requirements', 'source',
                  'product_id', 'contact_name', 'contact_email', 'contact_phone')
CONTACT_FIELDS = ('contact_name', 'contact_email', 'contact_phone')


def today():
    return datetime.now(ZONE).date()


def number(value, places=2, *, optional=False, positive=False):
    if value in (None, '') and optional:
        return None
    if isinstance(value, (float, bool)):
        raise ValueError('Nhập số thập phân dạng chuỗi, không dùng float.')
    try:
        result = Decimal(str(value))
        quantum = Decimal(10) ** -places
        if not result.is_finite() or result < 0 or (positive and result == 0):
            raise ValueError('Số lượng phải dương; tiền không được âm.')
        if result >= Decimal(10) ** (18 - places) or result != result.quantize(quantum):
            raise ValueError(f'Số vượt giới hạn hoặc có quá {places} chữ số thập phân.')
        return result.quantize(quantum)
    except InvalidOperation:
        raise ValueError('Giá trị số không hợp lệ.') from None


def _date(value):
    try:
        return date.fromisoformat(str(value))
    except ValueError:
        raise ValueError('Ngày không hợp lệ.') from None


def _request_values(fields, previous=None):
    if set(fields) - set(REQUEST_FIELDS):
        raise ValueError('Phiếu chứa trường không được phép cập nhật.')
    values = {key: str(fields.get(key) or '').strip() for key in REQUEST_FIELDS}
    for key in ('title', 'description', 'unit', 'delivery_location'):
        if not values[key]:
            raise ValueError('Thiếu tiêu đề, mô tả, đơn vị tính hoặc địa điểm giao.')
    values['quantity'] = number(fields.get('quantity'), 3, positive=True)
    values['budget'] = number(fields.get('budget'), optional=True)
    if values['budget_type'] not in ('per_unit', 'total'):
        raise ValueError('Loại ngân sách không hợp lệ.')
    values['delivery_deadline'] = _date(fields.get('delivery_deadline'))
    if values['delivery_deadline'] < today():
        raise ValueError('Hạn giao không được ở quá khứ.')
    if not values['contact_email'] and not values['contact_phone']:
        raise ValueError('Nhập email hoặc điện thoại ở phần liên hệ riêng.')
    if values['contact_email'] and ('@' not in values['contact_email'] or '.' not in values['contact_email'].rsplit('@', 1)[-1]):
        raise ValueError('Email chưa đúng định dạng.')
    public_text = ' '.join(values[key] for key in ('title', 'category', 'description', 'delivery_location', 'additional_requirements')).casefold()
    if (values['contact_email'] and values['contact_email'].casefold() in public_text) or (
            len(values['contact_phone']) >= 7 and values['contact_phone'].casefold() in public_text):
        raise ValueError('Chỉ điền email/điện thoại trong phần liên hệ riêng, không đặt vào nội dung chia sẻ.')
    source, product_id = values['source'], values['product_id']
    if bool(source) != bool(product_id):
        raise ValueError('Sản phẩm tham chiếu cần cả source và product_id.')
    if source:
        source, product_id = suppliers._product_key(source, product_id)
        if not previous or (source, product_id) != (previous['source'], previous['product_id']):
            if not any((p['source'], p['product_id']) == (source, product_id) for p in suppliers.catalog_items()):
                raise ValueError('Sản phẩm tham chiếu không còn trong catalog.')
    values['source'], values['product_id'] = source or None, product_id or None
    return tuple(values[key] for key in REQUEST_FIELDS)


def _cursor(connection):
    return connection.cursor(row_factory=dict_row)


def _event(connection, request_id, actor, kind, content, match_id=None):
    connection.execute('''INSERT INTO business.request_events(request_id,match_id,actor_id,event_type,content)
        VALUES (%s,%s,%s,%s,%s)''', (request_id, match_id, actor['id'], kind, content))


def _request(connection, actor, request_id):
    row = _cursor(connection).execute('SELECT * FROM business.purchase_requests WHERE id=%s FOR UPDATE',
                                      (request_id,)).fetchone()
    if not row:
        raise auth.AccessDenied('Không tìm thấy phiếu hoặc bạn không có quyền truy cập.')
    if actor['role'] == 'buyer' and row['buyer_id'] != actor['id']:
        raise auth.AccessDenied('Bạn không có quyền truy cập phiếu này.')
    if actor['role'] == 'seller':
        visible = connection.execute('''SELECT 1 FROM business.request_matches m
            JOIN business.supplier_members sm ON sm.supplier_id=m.supplier_id
            JOIN business.suppliers s ON s.id=m.supplier_id
            WHERE m.request_id=%s AND sm.user_id=%s AND s.status='approved' ''', (request_id, actor['id'])).fetchone()
        if not visible:
            raise auth.AccessDenied('Phiếu chưa được phân cho đơn vị đã duyệt của bạn.')
    return row


def _owner(actor, row):
    if actor['role'] != 'buyer' or actor['id'] != row['buyer_id']:
        raise auth.AccessDenied('Chỉ buyer chủ sở hữu được thực hiện thao tác này.')


def _accepting(row):
    if row['status'] not in ('open', 'assigned', 'quoted'):
        raise ValueError('Phiếu đã được chọn, hủy hoặc đóng; không nhận thêm phản hồi.')
    if row['delivery_deadline'] < today():
        raise ValueError('Đã quá hạn giao của phiếu.')


def create_request(session, fields):
    values = _request_values(fields)
    with postgres.transaction() as connection:
        actor = auth.require_user(connection, session, {'buyer'})
        columns = ','.join(REQUEST_FIELDS)
        placeholders = ','.join(['%s'] * len(values))
        request_id = connection.execute(f'''INSERT INTO business.purchase_requests(buyer_id,{columns})
            VALUES (%s,{placeholders}) RETURNING id''', (actor['id'], *values)).fetchone()[0]
        _event(connection, request_id, actor, 'created', 'Buyer tạo phiếu nhu cầu.')
    return request_id


def edit_request(session, request_id, fields):
    with postgres.transaction() as connection:
        actor = auth.require_user(connection, session, {'buyer'})
        row = _request(connection, actor, request_id)
        _owner(actor, row)
        if row['status'] != 'open' or connection.execute(
                'SELECT 1 FROM business.request_matches WHERE request_id=%s', (request_id,)).fetchone():
            raise ValueError('Phiếu đã phân công hoặc đóng. Hãy hủy và tạo phiếu mới.')
        values = _request_values(fields, row)
        assignments = ','.join(f'{field}=%s' for field in REQUEST_FIELDS)
        connection.execute(f'UPDATE business.purchase_requests SET {assignments},updated_at=CURRENT_TIMESTAMP WHERE id=%s',
                           (*values, request_id))
        _event(connection, request_id, actor, 'edited', 'Buyer cập nhật phiếu trước khi phân công.')


def assign_supplier(session, request_id, supplier_id):
    with postgres.transaction() as connection:
        actor = auth.require_user(connection, session, {'admin'})
        row = _request(connection, actor, request_id)
        _accepting(row)
        supplier = suppliers._supplier(connection, actor, supplier_id)
        if supplier['status'] != 'approved':
            raise ValueError('Chỉ phân đơn vị đã được duyệt.')
        result = connection.execute('''INSERT INTO business.request_matches(request_id,supplier_id,assigned_by)
            VALUES (%s,%s,%s) ON CONFLICT(request_id,supplier_id) DO NOTHING RETURNING id''',
            (request_id, supplier_id, actor['id'])).fetchone()
        if not result:
            raise ValueError('Đơn vị đã được phân cho phiếu này.')
        connection.execute('''UPDATE business.purchase_requests SET status=CASE WHEN status='open' THEN 'assigned' ELSE status END,
            updated_at=CURRENT_TIMESTAMP WHERE id=%s''', (request_id,))
        _event(connection, request_id, actor, 'assigned', 'Admin phân nhà cung cấp thủ công.', result[0])
    return result[0]


def _match(connection, actor, row, match_id):
    match = _cursor(connection).execute('SELECT * FROM business.request_matches WHERE request_id=%s AND id=%s FOR UPDATE',
                                       (row['id'], match_id)).fetchone()
    if not match:
        raise auth.AccessDenied('Không có phân công hợp lệ.')
    suppliers._supplier(connection, actor, match['supplier_id'], selling=True)
    if match['status'] == 'selected':
        raise ValueError('Không sửa hoặc thay thế báo giá đã được chọn.')
    return match


def submit_quote(session, request_id, match_id, *, quantity, unit, unit_price, shipping_fee=None,
                 expected_delivery, valid_until, notes='', excluded_costs=''):
    qty, price = number(quantity, 3, positive=True), number(unit_price)
    shipping = number(shipping_fee, optional=True)
    delivery = _date(expected_delivery)
    try:
        expiry = datetime.fromisoformat(str(valid_until))
        if expiry.tzinfo is None or expiry.utcoffset() is None:
            raise ValueError()
    except ValueError:
        raise ValueError('Hạn hiệu lực cần ngày giờ có múi giờ.') from None
    if expiry <= datetime.now(ZONE):
        raise ValueError('Báo giá đã hết hạn hiệu lực.')
    if not excluded_costs.strip():
        raise ValueError('Nêu rõ chi phí chưa bao gồm, hoặc ghi Không có.')
    exclusions = excluded_costs.strip()
    if shipping is None:
        exclusions += '\nPhí giao hàng chưa bao gồm trong tổng tiền.'
    with localcontext() as context:
        context.prec = 50
        total = (qty * price + (shipping or Decimal(0))).quantize(Decimal('.01'), rounding=ROUND_HALF_UP)
    total = number(total)
    with postgres.transaction() as connection:
        actor = auth.require_user(connection, session, {'seller'})
        row = _request(connection, actor, request_id)
        _accepting(row)
        match = _match(connection, actor, row, match_id)
        if unit.strip() != row['unit'] or qty > row['quantity']:
            raise ValueError('Đơn vị phải giống phiếu; số lượng đáp ứng không vượt nhu cầu.')
        if delivery < today() or delivery > row['delivery_deadline']:
            raise ValueError('Ngày giao dự kiến phải từ hôm nay đến hạn giao của phiếu.')
        if expiry <= datetime.now(ZONE):
            raise ValueError('Báo giá đã hết hạn hiệu lực.')
        version = connection.execute('SELECT coalesce(max(version),0)+1 FROM business.request_quotes WHERE match_id=%s',
                                     (match_id,)).fetchone()[0]
        connection.execute("UPDATE business.request_quotes SET status='superseded' WHERE match_id=%s AND status='active'", (match_id,))
        quote_id = connection.execute('''INSERT INTO business.request_quotes
            (request_id,match_id,version,quantity,unit,unit_price,shipping_fee,total_amount,
             expected_delivery,valid_until,notes,excluded_costs,created_by)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id''',
            (request_id, match_id, version, qty, row['unit'], price, shipping, total, delivery, expiry,
             notes.strip(), exclusions, actor['id'])).fetchone()[0]
        connection.execute("UPDATE business.request_matches SET status='quoted',decline_reason='' WHERE id=%s", (match_id,))
        connection.execute("UPDATE business.purchase_requests SET status='quoted',updated_at=CURRENT_TIMESTAMP WHERE id=%s", (request_id,))
        _event(connection, request_id, actor, 'quoted', f'Gửi báo giá phiên bản {version}.', match_id)
    return quote_id


def decline_request(session, request_id, match_id, reason):
    if not reason.strip():
        raise ValueError('Vui lòng ghi lý do không thể đáp ứng.')
    with postgres.transaction() as connection:
        actor = auth.require_user(connection, session, {'seller'})
        row = _request(connection, actor, request_id)
        _accepting(row)
        _match(connection, actor, row, match_id)
        connection.execute("UPDATE business.request_quotes SET status='superseded' WHERE match_id=%s AND status='active'", (match_id,))
        connection.execute("UPDATE business.request_matches SET status='declined',decline_reason=%s WHERE id=%s", (reason.strip(), match_id))
        connection.execute('UPDATE business.purchase_requests SET updated_at=CURRENT_TIMESTAMP WHERE id=%s', (request_id,))
        _event(connection, request_id, actor, 'declined', reason.strip(), match_id)


def select_quote(session, request_id, quote_id):
    with postgres.transaction() as connection:
        actor = auth.require_user(connection, session, {'buyer'})
        row = _request(connection, actor, request_id)
        _owner(actor, row)
        _accepting(row)
        if row['status'] != 'quoted' or row['selected_quote_id'] is not None:
            raise ValueError('Phiếu không còn cho phép chọn báo giá.')
        quote = _cursor(connection).execute('''SELECT q.*,m.supplier_id FROM business.request_quotes q
            JOIN business.request_matches m ON m.id=q.match_id WHERE q.request_id=%s AND q.id=%s FOR UPDATE OF q,m''',
            (request_id, quote_id)).fetchone()
        if not quote or quote['status'] != 'active' or quote['valid_until'] <= datetime.now(ZONE):
            raise ValueError('Báo giá không hợp lệ, đã thay thế hoặc hết hạn.')
        supplier = _cursor(connection).execute('SELECT * FROM business.suppliers WHERE id=%s FOR UPDATE',
                                              (quote['supplier_id'],)).fetchone()
        if supplier['status'] != 'approved':
            raise ValueError('Nhà cung cấp không còn được duyệt.')
        if quote['valid_until'] <= datetime.now(ZONE):
            raise ValueError('Báo giá đã hết hạn hiệu lực.')
        connection.execute("UPDATE business.request_quotes SET status='selected' WHERE id=%s", (quote_id,))
        connection.execute("UPDATE business.request_matches SET status='selected' WHERE id=%s", (quote['match_id'],))
        connection.execute("UPDATE business.purchase_requests SET status='selected',selected_quote_id=%s,updated_at=CURRENT_TIMESTAMP WHERE id=%s", (quote_id, request_id))
        _event(connection, request_id, actor, 'selected', 'Buyer chọn phương án để tiếp tục trao đổi; chưa phải đơn hàng hay giao dịch thành công.', quote['match_id'])


def close_request(session, request_id, status):
    allowed = {'cancelled': {'open', 'assigned', 'quoted', 'selected'},
               'closed_no_match': {'open', 'assigned', 'quoted'}, 'connected': {'selected'}}
    if status not in allowed:
        raise ValueError('Chuyển trạng thái không hợp lệ.')
    with postgres.transaction() as connection:
        actor = auth.require_user(connection, session, {'buyer', 'admin'})
        row = _request(connection, actor, request_id)
        if actor['role'] != 'admin' or status == 'connected':
            _owner(actor, row)
        if row['status'] not in allowed[status]:
            raise ValueError('Không cho phép chuyển trạng thái này.')
        connection.execute('UPDATE business.purchase_requests SET status=%s,updated_at=CURRENT_TIMESTAMP WHERE id=%s', (status, request_id))
        _event(connection, request_id, actor, status, {'connected': 'Buyer xác nhận đã kết nối để trao đổi, không xác nhận thanh toán hoặc giao dịch.',
               'cancelled': 'Phiếu đã bị hủy.', 'closed_no_match': 'Đóng phiếu do không có phương án phù hợp.'}[status])


def list_requests(session):
    with postgres.transaction() as connection:
        actor = auth.require_user(connection, session, {'buyer', 'seller', 'admin'})
        where, params = '', []
        if actor['role'] == 'buyer':
            where, params = ' WHERE r.buyer_id=%s', [actor['id']]
        elif actor['role'] == 'seller':
            where = ''' WHERE EXISTS (SELECT 1 FROM business.request_matches m
                JOIN business.supplier_members sm ON sm.supplier_id=m.supplier_id
                JOIN business.suppliers s ON s.id=m.supplier_id
                WHERE m.request_id=r.id AND sm.user_id=%s AND s.status='approved')'''
            params = [actor['id']]
        return _cursor(connection).execute('''SELECT r.id,r.title,r.category,r.quantity,r.unit,r.status,
            r.delivery_deadline,r.created_at FROM business.purchase_requests r''' + where + ' ORDER BY r.id DESC', params).fetchall()


def request_detail(session, request_id):
    """Return role-scoped projections, never send concealed contacts to the UI."""
    with postgres.transaction() as connection:
        actor = auth.require_user(connection, session, {'buyer', 'seller', 'admin'})
        row = _request(connection, actor, request_id)
        matches = _cursor(connection).execute('''SELECT m.*,s.name AS supplier_name
            FROM business.request_matches m JOIN business.suppliers s ON s.id=m.supplier_id
            WHERE m.request_id=%s ORDER BY m.id''', (request_id,)).fetchall()
        if actor['role'] == 'seller':
            memberships = connection.execute('''SELECT sm.supplier_id FROM business.supplier_members sm
                JOIN business.suppliers s ON s.id=sm.supplier_id
                WHERE sm.user_id=%s AND s.status='approved' ''', (actor['id'],)).fetchall()
            visible_suppliers = {m[0] for m in memberships}
            matches = [m for m in matches if m['supplier_id'] in visible_suppliers]
        match_ids = [m['id'] for m in matches]
        quotes = _cursor(connection).execute('''SELECT q.*,m.supplier_id,s.name AS supplier_name
            FROM business.request_quotes q JOIN business.request_matches m ON m.id=q.match_id
            JOIN business.suppliers s ON s.id=m.supplier_id
            WHERE q.request_id=%s AND q.match_id=ANY(%s) ORDER BY q.match_id,q.version''',
            (request_id, match_ids)).fetchall()
        winner = next((q for q in quotes if q['id'] == row['selected_quote_id']), None)
        disclosed = row['status'] in ('selected', 'connected')
        owner = actor['role'] == 'buyer' and actor['id'] == row['buyer_id']
        if not (owner or (disclosed and (actor['role'] == 'admin' or winner is not None))):
            for key in CONTACT_FIELDS:
                row.pop(key, None)
        if actor['role'] == 'seller':
            row.pop('buyer_id', None)
            if winner is None:
                row['selected_quote_id'] = None
        contacts = None
        if disclosed and winner is not None:
            supplier = _cursor(connection).execute('SELECT name,email,phone FROM business.suppliers WHERE id=%s',
                                                  (winner['supplier_id'],)).fetchone()
            contacts = {'supplier_name': supplier['name'], 'supplier_email': supplier['email'],
                        'supplier_phone': supplier['phone']}
            if not owner:
                contacts.update({key: row.get(key, '') for key in CONTACT_FIELDS})
        event_where, params = 'request_id=%s', [request_id]
        if actor['role'] == 'seller':
            event_where += ' AND match_id=ANY(%s)'
            params.append(match_ids)
        events = _cursor(connection).execute('''SELECT id,actor_id,event_type,content,created_at
            FROM business.request_events WHERE ''' + event_where + ' ORDER BY id', params).fetchall()
    return {'request': row, 'matches': matches, 'quotes': quotes, 'contacts': contacts, 'events': events}
