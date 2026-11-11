"""Deterministic, read-only supplier matching. No catalog prices or text inference.

All five applicable criteria are mandatory. Met earns its fixed weight; unknown
and failed earn zero. Budget is not applicable when buyer has no budget (zero
points). Groups sort before scores: recommended, confirmation, excluded.
"""
from datetime import datetime
import unicodedata
from zoneinfo import ZoneInfo

from psycopg.rows import dict_row
from . import auth, postgres, purchase

VERSION = 'rules-v1'
WEIGHTS = {'product': 40, 'region': 20, 'minimum': 15, 'preparation': 15, 'budget': 10}
GROUPS = {'recommended': 0, 'confirmation': 1, 'excluded': 2}
ZONE = ZoneInfo('Asia/Ho_Chi_Minh')


def normalized(value):
    return ' '.join(unicodedata.normalize('NFC', str(value or '')).casefold().split())


def evaluate_product(request, product, *, as_of):
    criteria = []

    def add(key, state, reason):
        criteria.append({'criterion': key, 'state': state, 'reason': reason,
                         'points': WEIGHTS[key] if state == 'met' else 0})

    exact = bool(request.get('source') and (request['source'], request['product_id']) ==
                 (product['source'], product['product_id']))
    category, offered = normalized(request.get('category')), normalized(product.get('category'))
    if exact:
        add('product', 'met', f"Trùng sản phẩm tham chiếu {request['source']} · {request['product_id']}.")
    elif category and offered and category == offered:
        add('product', 'met', f"Trùng danh mục khai báo: {request['category']} / {product['category']}.")
    elif category and offered:
        add('product', 'failed', 'Không trùng tham chiếu và danh mục khai báo khác nhau.')
    elif request.get('source') and not category:
        add('product', 'failed', 'Nhu cầu chỉ định sản phẩm; khóa sản phẩm không trùng.')
    else:
        add('product', 'unknown', 'Thiếu danh mục khai báo để xác nhận sản phẩm thay thế.')

    regions = {normalized(v) for v in product.get('service_regions', [])}
    region = normalized(request.get('delivery_region'))
    if not region or not regions:
        add('region', 'unknown', 'Chưa khai báo tỉnh/thành giao hoặc danh sách khu vực phục vụ.')
    else:
        add('region', 'met' if region in regions else 'failed',
            f"Tỉnh/thành giao {request['delivery_region']} / khu vực khai báo: {', '.join(product['service_regions'])}.")

    same_unit = bool(normalized(product.get('unit'))) and normalized(request['unit']) == normalized(product['unit'])
    minimum = product.get('minimum_order')
    if minimum is None or not same_unit:
        add('minimum', 'unknown', 'Thiếu số lượng tối thiểu hoặc khác/chưa có đơn vị; không quy đổi.')
    else:
        add('minimum', 'met' if request['quantity'] >= minimum else 'failed',
            f"Nhu cầu {request['quantity']} / tối thiểu {minimum} {product['unit']}.")

    days = product.get('preparation_days')
    if days is None:
        add('preparation', 'unknown', 'Chưa khai báo số ngày chuẩn bị; không đọc từ mô tả tự do.')
    else:
        available = (request['delivery_deadline'] - as_of).days
        add('preparation', 'met' if days <= available else 'failed',
            f'Chuẩn bị {days} ngày / còn {available} ngày đến hạn; vận chuyển cần xác nhận riêng.')

    price = product.get('reference_price')
    if request.get('budget') is None:
        add('budget', 'not_applicable', 'Buyer không đặt ngân sách; không cộng điểm ngân sách.')
    elif price is None or normalized(product.get('reference_price_unit')) != normalized(request['unit']):
        add('budget', 'unknown', 'Thiếu giá tham khảo VND cùng đơn vị; không dùng giá catalog hay báo giá cũ.')
    else:
        required = price if request['budget_type'] == 'per_unit' else price * request['quantity']
        add('budget', 'met' if required <= request['budget'] else 'failed',
            f'Giá tham khảo theo cơ sở {request["budget_type"]}: {required} VND / ngân sách {request["budget"]}; '
            'chưa xác nhận vận chuyển/thuế, không phải báo giá thực tế.')
    states = {c['state'] for c in criteria}
    group = 'excluded' if 'failed' in states else 'confirmation' if 'unknown' in states else 'recommended'
    return {'source': product['source'], 'product_id': product['product_id'],
            'category': product.get('category', ''), 'criteria': criteria,
            'score': sum(c['points'] for c in criteria), 'group': group}


def rank_candidates(request, products, *, as_of=None):
    """Pure function: one result per approved supplier with active product links."""
    as_of = as_of or datetime.now(ZONE).date()
    grouped = {}
    for product in products:
        if product['supplier_status'] != 'approved' or not product['is_active']:
            continue
        result = evaluate_product(request, product, as_of=as_of)
        entry = grouped.setdefault(product['supplier_id'], {
            'supplier_id': product['supplier_id'], 'supplier_name': product['supplier_name'],
            'is_demo': product['is_demo'], 'products': []})
        entry['products'].append(result)
    for entry in grouped.values():
        entry['products'].sort(key=lambda p: (GROUPS[p['group']], -p['score'], p['source'], p['product_id']))
        best = entry['products'][0]
        entry.update(group=best['group'], score=best['score'], criteria=best['criteria'], rule_version=VERSION,
                     evaluated_on=as_of.isoformat())
    return sorted(grouped.values(), key=lambda c: (GROUPS[c['group']], -c['score'], c['supplier_id']))


def candidates_in_connection(connection, request, supplier_id=None):
    # One SELECT gives a consistent read. Assignment already holds the supplier
    # lock used by save_product/stop_product/review, protecting its declarations.
    products = connection.cursor(row_factory=dict_row).execute('''SELECT p.*,s.name AS supplier_name,
        s.status AS supplier_status,s.is_demo FROM business.supplier_products p
        JOIN business.suppliers s ON s.id=p.supplier_id
        WHERE s.status='approved' AND p.is_active
        AND (%s::bigint IS NULL OR s.id=%s) ORDER BY s.id,p.source,p.product_id''',
        (supplier_id, supplier_id)).fetchall()
    return rank_candidates(request, products)


def find_candidates(session, request_id):
    with postgres.transaction() as connection:
        actor = auth.require_user(connection, session, {'admin'})
        request = purchase._request(connection, actor, request_id)
        return candidates_in_connection(connection, request)
