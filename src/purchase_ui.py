"""Role-specific manual matching and quote workflow."""
from datetime import datetime, time, timedelta
import hashlib
from decimal import Decimal
from html import escape

import duckdb
import psycopg
import streamlit as st
from data import auth, purchase, suppliers, matching
from src import auth_ui
from src.catalog_cache import catalog_items
from src.ui_labels import field_line, number_label, money_label, date_label, time_label, event_label
from src.ui_labels import parse_vn_number, NUMBER_HELP
from src.ui_labels import UNIT_OPTIONS, select_existing as _select_existing
from src.ui_labels import STATES, render_stepper
from src.ui_labels import role_label
from data.categories import CATEGORY_ALIASES
from crawlers.provinces import PROVINCE_NAMES

QUOTE_STATES = {'active': 'Hiện hành', 'superseded': 'Đã thay thế', 'selected': 'Đã chọn'}


def _done(message):
    st.session_state['_purchase_notice'] = message
    st.rerun()


def request_form(row=None, actor=None):
    row = row or {}
    actor = (actor or auth_ui.identity() or {}) if not row else {}
    reference = st.session_state.get('purchase_reference', {}) if not row else {}
    catalog = catalog_items()
    choices = {None: 'Không chọn sản phẩm tham chiếu'}
    choices.update({(p['source'], p['product_id']): f"{p['product_name']} ({p['source']} · {p['product_id']})" for p in catalog})
    initial = (row.get('source'), row.get('product_id')) if row.get('source') else (
        (reference['source'], reference['product_id']) if reference.get('source') else None)
    if initial and initial not in choices:
        choices[initial] = 'Sản phẩm không còn trong catalog'
    st.caption('Dùng phần thông tin liên hệ bên dưới; không ghi email/điện thoại vào mô tả hay yêu cầu bổ sung.')
    with st.form(f'purchase_form_{row.get("id", "new")}'):
        with st.container(border=True):
            st.subheader('Bạn cần gì')
            title = st.text_input('Tiêu đề *', value=row.get('title', reference.get('title', '')))
            category = _select_existing(
                'Nhóm sản phẩm cần mua (tùy chọn)', CATEGORY_ALIASES,
                row.get('category', reference.get('category', '')),
                help='Chọn nhóm sản phẩm muốn mua để hỗ trợ tìm nhà cung cấp phù hợp. '
                     'Ví dụ: Đồ uống, Trái cây, Thủ công mỹ nghệ. Có thể để trống nếu chưa xác định.')
            description = st.text_area('Mô tả nhu cầu *', value=row.get('description', ''))
            quantity = st.text_input('Số lượng *', value='' if row.get('quantity') is None else number_label(row['quantity']), help=NUMBER_HELP)
            unit = _select_existing(
                'Đơn vị tính *', UNIT_OPTIONS, row.get('unit', ''))
            selected = st.selectbox('Sản phẩm tham chiếu', options=list(choices), index=list(choices).index(initial),
                                    format_func=lambda key: choices[key])
        with st.container(border=True):
            st.subheader('Giao ở đâu, khi nào')
            location = st.text_input('Địa điểm giao *', value=row.get('delivery_location', ''))
            region = _select_existing(
                'Tỉnh/thành giao hàng', PROVINCE_NAMES, row.get('delivery_region', ''),
                help='Chọn tỉnh/thành tại địa chỉ nhận hàng để tìm nhà cung cấp có thể giao đến.')
            deadline = st.date_input('Hạn giao *', format='DD/MM/YYYY', value=row.get('delivery_deadline', purchase.today() + timedelta(days=7)))
            additional = st.text_area('Yêu cầu bổ sung', value=row.get('additional_requirements', ''))
        with st.container(border=True):
            st.subheader('Ngân sách và liên hệ')
            budget = st.text_input('Ngân sách VND (tùy chọn)', value='' if row.get('budget') is None else number_label(row['budget']), help=NUMBER_HELP)
            budget_type = st.radio('Loại ngân sách', options=['total', 'per_unit'],
                                       index=0 if row.get('budget_type', 'total') == 'total' else 1, horizontal=True,
                                       format_func=lambda v: 'Tổng ngân sách' if v == 'total' else 'Mỗi đơn vị')
            st.caption('Liên hệ chỉ chia sẻ với nhà cung cấp được chọn. Nhập ít nhất email hoặc điện thoại.')
            contact_name = st.text_input('Tên liên hệ', value=row.get('contact_name', actor.get('full_name') or actor.get('display_name') or actor.get('username') or ''))
            contact_email = st.text_input('Email liên hệ', value=row.get('contact_email', actor.get('email') or ''))
            contact_phone = st.text_input('Điện thoại liên hệ', value=row.get('contact_phone', ''))
        submitted = st.form_submit_button('Lưu thay đổi nhu cầu' if row else 'Tạo phiếu nhu cầu', type='primary')
    if submitted:
        quantity = parse_vn_number(quantity)
        budget = parse_vn_number(budget) if budget.strip() else None
        fields = dict(title=title, category=category, description=description, quantity=quantity, unit=unit,
                      budget=budget, budget_type=budget_type, delivery_location=location, delivery_deadline=deadline,
                      additional_requirements=additional, source=selected[0] if selected else '',
                      product_id=selected[1] if selected else '', contact_name=contact_name,
                      contact_email=contact_email, contact_phone=contact_phone, delivery_region=region)
        session = st.session_state.get('auth_session')
        if row:
            purchase.edit_request(session, row['id'], fields)
        else:
            request_id = purchase.create_request(session, fields)
            st.session_state.pop('purchase_reference', None)
            st.session_state.pop('_buyer_create_open', None)
            st.session_state['_purchase_created'] = request_id
            st.session_state['purchase_focus'] = request_id
            st.session_state.pop('buyer_request_search', None)
            st.session_state.pop('buyer_request_status', None)
        _done('Đã lưu phiếu nhu cầu.')


def _quote_available(quote, row):
    return (quote['status'] == 'active' and quote['valid_until'] > datetime.now(purchase.ZONE)
            and quote.get('supplier_status', 'approved') == 'approved'
            and purchase.today() <= quote['expected_delivery'] <= row['delivery_deadline'])


def _quote_state(quote, row):
    if quote['status'] != 'active':
        return QUOTE_STATES[quote['status']]
    if quote['valid_until'] <= datetime.now(purchase.ZONE):
        return 'Hết hiệu lực'
    if quote.get('supplier_status', 'approved') != 'approved':
        return 'Nhà cung cấp tạm ngưng'
    if not purchase.today() <= quote['expected_delivery'] <= row['delivery_deadline']:
        return 'Cần cập nhật ngày giao'
    return 'Có thể chọn' if row['status'] == 'quoted' and row['delivery_deadline'] >= purchase.today() else 'Ngừng nhận lựa chọn'


def _quotes(detail, actor, session):
    row, quotes = detail['request'], detail['quotes']
    can_select = actor['role'] == 'buyer' and row['status'] == 'quoted' and row['delivery_deadline'] >= purchase.today()
    candidates = [q for q in quotes if _quote_available(q, row)] if can_select else []
    badges = {q['id']: [] for q in quotes}
    if candidates:
        cheapest = min(Decimal(str(q['total_amount'])) for q in candidates)
        earliest = min(q['expected_delivery'] for q in candidates)
        for q in candidates:
            if Decimal(str(q['total_amount'])) == cheapest:
                badges[q['id']].append('Rẻ nhất')
            if q['expected_delivery'] == earliest:
                badges[q['id']].append('Giao sớm nhất')
    st.header('So sánh báo giá' if actor['role'] != 'seller' else 'Lịch sử báo giá của đơn vị')
    if quotes and actor['role'] == 'buyer':
        st.dataframe([{
            'Đơn vị': q['supplier_name'] + (" · " + ' · '.join(badges[q['id']]) if badges[q['id']] else ''),
            'Số lượng': f"{number_label(q['quantity'])} {q['unit']}",
            'Đơn giá': money_label(q['unit_price']), 'Tổng tiền': money_label(q['total_amount']),
            'Giao dự kiến': date_label(q['expected_delivery']), 'Trạng thái': _quote_state(q, row),
        } for q in quotes], hide_index=True)
        st.caption('Nhãn chỉ xét báo giá có thể chọn; các phương án bằng nhau cùng nhận nhãn. '
                   '“Rẻ nhất” so theo tổng tiền ghi nhận, chưa bao gồm các chi phí được nhà cung cấp loại trừ. '
                   'Hãy đối chiếu cả số lượng và phí giao hàng.')
        for q in quotes:
            with st.expander(f"Chi tiết #{q['id']} · {q['supplier_name']} · Phiên bản {q['version']}"):
                field_line(('Phí giao hàng', 'Chưa bao gồm' if q['shipping_fee'] is None else money_label(q['shipping_fee'])),
                           ('Hiệu lực đến', time_label(q['valid_until'])))
                st.write('Chi phí chưa gồm: ' + (q['excluded_costs'] or 'Chưa cập nhật'))
                st.write('Ghi chú: ' + (q['notes'] or 'Không có ghi chú'))
    elif quotes:
        st.dataframe([{'Mã': q['id'], 'Đơn vị cung cấp': q['supplier_name'], 'Phiên bản': q['version'],
                       'Số lượng': number_label(q['quantity']), 'Đơn vị tính': q['unit'], 'Đơn giá': money_label(q['unit_price']),
                       'Phí giao hàng': 'Chưa bao gồm' if q['shipping_fee'] is None else money_label(q['shipping_fee']),
                       'Tổng tiền': money_label(q['total_amount']), 'Giao dự kiến': date_label(q['expected_delivery']),
                       'Hiệu lực đến': time_label(q['valid_until']), 'Trạng thái': _quote_state(q, row),
                       'Chi phí chưa gồm': q['excluded_costs'] or 'Chưa cập nhật', 'Ghi chú': q['notes'] or 'Không có ghi chú'} for q in quotes], hide_index=True)
    else:
        st.info('Chưa có báo giá.')
    for match in detail['matches']:
        if match['status'] == 'declined':
            st.info(f"{match['supplier_name']} không thể đáp ứng: {match['decline_reason']}")
    if can_select:
        if candidates:
            st.caption('Kiểm tra số lượng đáp ứng, phí giao hàng và chi phí chưa gồm trước khi chọn.')
            with st.form(f'choose_quote_{row["id"]}'):
                st.markdown('''<style>
                [class*="st-key-quote_cards_"] [role="radiogroup"] {gap:10px;}
                [class*="st-key-quote_cards_"] [data-baseweb="radio"] {
                    display:flex;align-items:flex-start;margin:0;padding:14px 16px;
                    border:1px solid #d7e3db;border-radius:12px;background:#fff;
                }
                [class*="st-key-quote_cards_"] [data-baseweb="radio"]:has(input:checked) {
                    border:2px solid #287a4d;background:#edf7ef;
                }
                [class*="st-key-quote_cards_"] [data-baseweb="radio"]:hover {border-color:#287a4d;background:#f4f9f5;}
                [class*="st-key-quote_cards_"] [data-baseweb="radio"]:focus-within {outline:2px solid #287a4d;outline-offset:3px;}
                [class*="st-key-quote_cards_"] [data-baseweb="radio"] p {line-height:1.6;}
                </style>''', unsafe_allow_html=True)
                labels = {q['id']: f"#{q['id']} · {q['supplier_name']}\n\n"
                          f"{number_label(q['quantity'])} {q['unit']} · {money_label(q['total_amount'])}"
                          f" · Giao {date_label(q['expected_delivery'])}"
                          + ('\n\n' + ' · '.join(badges[q['id']]) if badges[q['id']] else '')
                          for q in candidates}
                with st.container(key=f'quote_cards_{row["id"]}'):
                    quote_id = st.radio('Phương án muốn chọn', options=list(labels),
                                        format_func=labels.get, key=f'quote_choice_{row["id"]}')
                confirmed = st.checkbox('Tôi hiểu đây chỉ là lựa chọn để tiếp tục trao đổi, chưa phải đơn hàng hay giao dịch thành công.')
                submitted = st.form_submit_button('Chọn phương án', type='primary')
            if submitted:
                if not confirmed:
                    raise ValueError('Vui lòng xác nhận ý nghĩa của việc lựa chọn.')
                purchase.select_quote(session, row['id'], quote_id)
                _done('Đã chọn phương án để tiếp tục trao đổi.')
        else:
            st.info('Chưa có báo giá còn phù hợp để chọn. Vui lòng chờ nhà cung cấp cập nhật.')


def _seller_response(detail, session):
    row = detail['request']
    if row['status'] not in ('assigned', 'quoted'):
        return
    if row['delivery_deadline'] < purchase.today():
        st.warning('Yêu cầu đã quá hạn giao, không nhận thêm báo giá.')
        return
    st.header('Phản hồi yêu cầu')
    st.caption('Điền báo giá bên dưới. Nếu đã gửi, báo giá mới sẽ thay thế phiên bản trước của đơn vị.')
    match = st.selectbox('Đơn vị phản hồi', options=detail['matches'], format_func=lambda m: m['supplier_name'],
                         key=f'response_match_{row["id"]}')
    with st.form(f'submit_supplier_quote_{row["id"]}_{match["id"]}'):
        quantity = st.text_input('Số lượng đáp ứng', value=number_label(row['quantity']), help=NUMBER_HELP)
        st.caption('Đơn vị tính: ' + row['unit'])
        price = st.text_input('Đơn giá VND', help=NUMBER_HELP)
        shipping = st.text_input('Phí giao hàng VND (trống = chưa gồm)', help='Nhập 0 nếu miễn phí hoặc đã gồm trong đơn giá. ' + NUMBER_HELP)
        delivery = st.date_input('Ngày giao dự kiến', format='DD/MM/YYYY', value=row['delivery_deadline'],
                                 min_value=purchase.today(), max_value=row['delivery_deadline'])
        validity = st.date_input('Báo giá có hiệu lực hết ngày', format='DD/MM/YYYY', value=purchase.today() + timedelta(days=1),
                                 min_value=purchase.today())
        excluded = st.text_area('Chi phí chưa bao gồm (ghi Không có nếu đã gồm hết)')
        notes = st.text_area('Ghi chú báo giá')
        submitted = st.form_submit_button('Gửi phiên bản báo giá mới', type='primary')
    if submitted:
        purchase.submit_quote(session, row['id'], match['id'], quantity=parse_vn_number(quantity), unit=row['unit'], unit_price=parse_vn_number(price),
                              shipping_fee=parse_vn_number(shipping) if shipping.strip() else None, expected_delivery=delivery,
                              valid_until=datetime.combine(validity, time.max, purchase.ZONE), notes=notes, excluded_costs=excluded)
        _done('Đã gửi báo giá. Bạn có thể xem lại trong lịch sử báo giá.')
    with st.expander('Không thể đáp ứng yêu cầu này?'):
        with st.form(f'decline_match_{row["id"]}_{match["id"]}'):
            reason = st.text_area('Lý do không thể đáp ứng')
            declined = st.form_submit_button('Không thể đáp ứng')
        if declined:
            purchase.decline_request(session, row['id'], match['id'], reason)
            _done('Đã ghi nhận phản hồi không thể đáp ứng.')


def _seller_overview(rows):
    """Current request outcomes in the seller's visible scope, before UI filters."""
    total, ongoing, selected = st.columns(3)
    total.metric('Yêu cầu được phân', len(rows),
                 help='Số phiếu duy nhất được phân cho các đơn vị đã duyệt mà bạn là thành viên, gồm mọi trạng thái.')
    ongoing.metric('Đang tiếp nhận báo giá',
                   sum(r['status'] in ('assigned', 'quoted') and r['delivery_deadline'] >= purchase.today() for r in rows),
                   help='Phiếu đang được phân hoặc đã có báo giá và chưa quá hạn giao. Không phải số phiếu bạn chưa phản hồi.')
    selected.metric('Đã chọn / kết nối', sum(r['status'] in ('selected', 'connected') for r in rows),
                    help='Phiếu hiện đã chọn phương án hoặc xác nhận kết nối. Không tính phiếu đã hủy; không khẳng định đơn vị của bạn được chọn.')
    st.caption('Tổng quan tất cả yêu cầu bạn được phép xem, trước bộ lọc. '
               '“Đã chọn / kết nối” là kết quả của yêu cầu, không phải số đơn hàng của đơn vị.')


def _open_buyer_create():
    st.session_state.pop('_purchase_created', None)
    st.session_state['_buyer_create_open'] = True


def _close_buyer_create():
    st.session_state.pop('_buyer_create_open', None)
    st.session_state.pop('purchase_reference', None)


def _confirm_connected_action(session, request_id):
    try:
        purchase.close_request(session, request_id, 'connected')
    except (auth.AccessDenied, ValueError) as error:
        st.session_state['_connected_error'] = str(error)
    except (psycopg.Error, OSError):
        st.session_state['_connected_error'] = 'Chưa thể xác nhận. Vui lòng thử lại.'
    else:
        st.session_state['_purchase_notice'] = 'Đã ghi nhận người mua xác nhận kết nối.'


@st.dialog('Xác nhận đã kết nối để trao đổi')
def _confirm_connected(session, request_id):
    st.info('Chỉ xác nhận đã trao đổi, không xác nhận thanh toán hay giao hàng')
    error = st.session_state.pop('_connected_error', None)
    if error:
        st.error(error)
    cancel, confirm = st.columns(2)
    with cancel:
        if st.button('Hủy', key=f'cancel_connected_{request_id}', use_container_width=True):
            st.rerun()
    with confirm:
        if st.button('Xác nhận', key=f'confirm_connected_{request_id}', type='primary',
                     on_click=_confirm_connected_action, args=(session, request_id), use_container_width=True):
            if '_connected_error' in st.session_state:
                st.error(st.session_state.pop('_connected_error'))
            else:
                st.rerun()


def _history_timeline(events):
    if not events:
        st.info('Chưa có lịch sử xử lý.')
        return
    items = []
    # Event types identify the business role even if an account later changes role.
    roles = {'created': 'buyer', 'edited': 'buyer', 'assigned': 'admin',
             'quoted': 'seller', 'declined': 'seller', 'selected': 'buyer', 'connected': 'buyer'}
    for event in events:
        label = role_label(event.get('actor_role') or roles.get(event['event_type']))
        supplier = event.get('actor_supplier_name')
        if supplier:
            label += ' · ' + str(supplier)
        items.append('<li><div class="request-timeline-meta"><strong>' + escape(label)
                     + '</strong><span>' + escape(time_label(event.get('created_at')))
                     + '</span></div><div class="request-timeline-content">'
                     + escape(event_label(event)) + '</div></li>')
    st.markdown('''<style>
    .request-timeline {list-style:none!important;margin:12px 0 12px 8px!important;padding:0 0 0 22px!important;border-left:2px solid #d3e5d9;}
    .request-timeline li {position:relative;list-style:none;padding:0 0 22px 0;}
    .request-timeline li:last-child {padding-bottom:0;}
    .request-timeline li::before {content:'';position:absolute;left:-29px;top:5px;width:12px;height:12px;border-radius:50%;background:#287a4d;border:2px solid #fff;}
    .request-timeline-meta {display:flex;flex-wrap:wrap;align-items:center;gap:6px 16px;font-size:13px;color:#195b3e;}
    .request-timeline-meta span {font-size:12px;color:#63796b;}
    .request-timeline-content {margin-top:8px;padding:12px 14px;background:#f4f8f5;border:1px solid #e0e9e3;border-radius:10px;white-space:pre-wrap;overflow-wrap:anywhere;font-size:14px;line-height:1.7;}
    </style><ol class="request-timeline" aria-label="Lịch sử xử lý">'''
                + ''.join(items) + '</ol>', unsafe_allow_html=True)


def _request_selector(rows, role):
    ids = [r['id'] for r in rows]
    focus = st.session_state.pop('purchase_focus', None)
    if focus in ids:
        st.session_state['purchase_selected_id'] = focus
        st.session_state['purchase_table_generation'] = st.session_state.get('purchase_table_generation', 0) + 1
    signature = (role, st.session_state.get('purchase_table_generation', 0),
                 [(r['id'], r['status'], str(r['delivery_deadline'])) for r in rows])
    digest = hashlib.sha256(repr(signature).encode('utf-8')).hexdigest()[:16]
    st.caption('Bấm chọn một dòng để xem chi tiết phiếu bên dưới.')
    event = st.dataframe(
        [{'Mã': r['id'], 'Tiêu đề': r['title'], 'Trạng thái': STATES[r['status']],
          'Số lượng': number_label(r['quantity']), 'Đơn vị': r['unit'],
          'Hạn giao': date_label(r['delivery_deadline'])} for r in rows],
        hide_index=True, key=f'purchase_requests_{digest}',
        on_select='rerun', selection_mode='single-row', use_container_width=True,
    )
    positions = event['selection']['rows']
    if positions and isinstance(positions[0], int) and 0 <= positions[0] < len(ids):
        st.session_state['purchase_selected_id'] = ids[positions[0]]
    selected = st.session_state.get('purchase_selected_id')
    if selected not in ids:
        selected = ids[0]
        st.session_state['purchase_selected_id'] = selected
    return selected


def page(title='Nhu cầu và kết nối cung cầu'):
    session = st.session_state.get('auth_session')
    if session is None:
        if title:
            st.title(title)
        st.info('Vui lòng đăng nhập để tạo hoặc theo dõi phiếu nhu cầu.')
        auth_ui.login()
        return
    try:
        actor = auth.current_user(session)
        if actor['role'] == 'buyer':
            if st.session_state.get('purchase_reference'):
                st.session_state['_buyer_create_open'] = True
            creating = st.session_state.get('_buyer_create_open', False)
            heading, action = st.columns([5, 1.5], vertical_alignment='center')
            with heading:
                if title:
                    st.title(title)
                st.caption('Gửi nhu cầu mua hàng, theo dõi phản hồi và chọn báo giá phù hợp.')
            with action:
                if creating:
                    st.button('Quay lại danh sách', on_click=_close_buyer_create, use_container_width=True)
                else:
                    st.button('Tạo nhu cầu', type='primary', on_click=_open_buyer_create, use_container_width=True)
        elif title:
            st.title(title)
        notice = st.session_state.pop('_purchase_notice', None)
        if notice:
            st.success(notice)
        if actor['role'] == 'buyer' and st.session_state.get('_purchase_created'):
            with st.container(border=True):
                st.subheader('Đã tạo phiếu nhu cầu thành công')
                st.write(f"Mã phiếu: #{st.session_state['_purchase_created']}")
                st.info('Bước tiếp theo: quản trị viên sẽ phân nhà cung cấp')
                st.write('Bạn có thể theo dõi tiến độ và xem báo giá trong chi tiết phiếu.')
                if st.button('Xem phiếu nhu cầu vừa tạo', type='primary'):
                    st.session_state.pop('_purchase_created', None)
                    st.rerun()
            return
        connected_error = st.session_state.pop('_connected_error', None)
        if connected_error:
            st.error(connected_error)
        if actor['role'] == 'seller':
            st.caption('Xem yêu cầu được phân cho đơn vị, gửi báo giá hoặc phản hồi không thể đáp ứng.')
        if actor['role'] == 'buyer':
            if creating:
                st.header('Tạo nhu cầu')
                st.caption('Điền thông tin mua hàng và liên hệ. Các trường có dấu * là bắt buộc.')
                request_form(actor=actor)
                return
        rows = purchase.list_requests(session)
        if actor['role'] in ('buyer', 'admin') and rows:
            state = st.selectbox('Lọc trạng thái nhu cầu', options=['all', *STATES],
                                 format_func=lambda value: 'Tất cả' if value == 'all' else STATES[value],
                                 key='buyer_request_status' if actor['role'] == 'buyer' else 'admin_request_status')
            query = st.text_input('Tìm nhu cầu', placeholder='Nhập tiêu đề hoặc mã phiếu',
                                  key='buyer_request_search' if actor['role'] == 'buyer' else 'admin_request_search').strip().casefold()
            rows = [r for r in rows if (state == 'all' or r['status'] == state)
                    and (not query or query in r['title'].casefold() or query == str(r['id']))]
            if not rows:
                st.info('Không có nhu cầu phù hợp. Hãy đổi trạng thái hoặc từ khóa tìm kiếm.')
                return
        if actor['role'] == 'seller':
            _seller_overview(rows)
        if actor['role'] == 'seller' and rows:
            groups = {'Tất cả': None, 'Đang tiếp nhận báo giá': {'assigned', 'quoted'},
                      'Đã chọn / kết nối': {'selected', 'connected'}, 'Đã kết thúc': set(purchase.TERMINAL)}
            group = st.selectbox('Lọc yêu cầu', options=list(groups))
            rows = [r for r in rows if groups[group] is None or r['status'] in groups[group]]
            if group == 'Đang tiếp nhận báo giá':
                rows = [r for r in rows if r['delivery_deadline'] >= purchase.today()]
            rows = sorted(rows, key=lambda r: (not (r['status'] in ('assigned', 'quoted') and r['delivery_deadline'] >= purchase.today()), r['delivery_deadline']))
            if not rows:
                st.info('Không có yêu cầu trong nhóm này. Chọn nhóm khác để xem tiếp.')
                return
        st.header({'buyer': 'Nhu cầu đã gửi', 'seller': 'Nhu cầu được phân cho đơn vị của tôi', 'admin': 'Quản lý và theo dõi nhu cầu'}[actor['role']])
        if not rows:
            st.info('Bạn chưa có nhu cầu mua hàng. Chọn “Tạo nhu cầu” phía trên để tìm nhà cung cấp và nhận báo giá.'
                    if actor['role'] == 'buyer' else
                    ('Chưa có yêu cầu báo giá được phân cho đơn vị của bạn.'
                     if actor['role'] == 'seller' else 'Chưa có phiếu nhu cầu trong phạm vi quyền của bạn.'))
            return
        request_id = _request_selector(rows, actor['role'])
        detail = purchase.request_detail(session, request_id)
        row = detail['request']
        st.subheader(row['title'])
        render_stepper(row['status'])
        tab_labels = ['Tổng quan', 'Báo giá', 'Liên hệ & lịch sử']
        if actor['role'] == 'admin':
            tab_labels.append('Phân công')
        tabs = st.tabs(tab_labels)
        with tabs[0]:
            if row['status'] in ('open', 'assigned', 'quoted') and row['delivery_deadline'] < purchase.today():
                st.warning('Đã quá hạn giao: không thể phân nhà cung cấp, gửi hoặc chọn báo giá. '
                           'Bạn có thể đóng phiếu; nếu chưa phân công, người mua có thể sửa hạn giao.')
            if actor['role'] == 'seller':
                amount, due = st.columns(2)
                amount.metric('Số lượng cần mua', f"{number_label(row['quantity'])} {row['unit']}")
                due.metric('Hạn giao hàng', date_label(row['delivery_deadline']))
            st.write(row['description'])
            field_line(('Danh mục', row['category'] or 'Chưa cập nhật'),
                       ('Số lượng', f"{number_label(row['quantity'])} {row['unit']}"))
            field_line(('Giao tại', row['delivery_location']),
                       ('Hạn giao', date_label(row['delivery_deadline'])))
            field_line(('Yêu cầu bổ sung', row['additional_requirements'] or 'Chưa cập nhật'))
            field_line(('Ngân sách', 'Chưa cập nhật' if row['budget'] is None else
                        f"{money_label(row['budget'])} / " + ('đơn vị' if row['budget_type'] == 'per_unit' else 'tổng')))
            if row['source']:
                product = next((p for p in catalog_items() if (p['source'], p['product_id']) == (row['source'], row['product_id'])), None)
                st.caption(f"Tham chiếu: {product['product_name'] if product else 'Sản phẩm không còn trong catalog'} ({row['source']} · {row['product_id']})")
            if actor['role'] == 'buyer' and row['status'] == 'open':
                with st.expander('Sửa nhu cầu trước khi phân công'):
                    request_form(row)
            st.header('Tiến độ phân công')
            if detail['matches']:
                match_states = {'assigned': 'Đã phân, chờ phản hồi', 'quoted': 'Đã báo giá',
                                'declined': 'Không thể đáp ứng', 'selected': 'Đã được người mua chọn'}
                st.dataframe([{'Đơn vị': m['supplier_name'], 'Trạng thái': match_states[m['status']],
                               'Thời điểm phân': time_label(m['assigned_at'])} for m in detail['matches']], hide_index=True)
                if actor['role'] == 'admin':
                    for match in detail['matches']:
                        if match.get('matching_snapshot'):
                            with st.expander(f"Snapshot lúc phân · {match['supplier_name']} · {match['rule_version']}"):
                                snapshot = dict(match['matching_snapshot'])
                                if 'evaluated_on' in snapshot:
                                    snapshot['evaluated_on'] = date_label(snapshot['evaluated_on'])
                                st.json(snapshot)
            else:
                st.info('Chưa phân nhà cung cấp cho phiếu này.')
            if actor['role'] in ('buyer', 'admin') and row['status'] not in purchase.TERMINAL:
                if actor['role'] == 'buyer' and row['status'] == 'selected':
                    if st.button('Xác nhận đã kết nối để trao đổi'):
                        _confirm_connected(session, request_id)
                with st.expander('Đóng hoặc hủy nhu cầu'):
                    confirm_close = st.checkbox('Tôi xác nhận kết thúc nhu cầu này; phiếu sẽ không nhận thêm báo giá.', key=f'confirm_close_{request_id}')
                    if st.button('Hủy phiếu nhu cầu', disabled=not confirm_close):
                        purchase.close_request(session, request_id, 'cancelled')
                        _done('Đã hủy phiếu. Bạn có thể tạo nhu cầu mới.')
                    if row['status'] in ('open', 'assigned', 'quoted') and st.button('Đóng vì không tìm được phương án', disabled=not confirm_close):
                        purchase.close_request(session, request_id, 'closed_no_match')
                        _done('Đã đóng phiếu không có phương án phù hợp.')
        with tabs[1]:
            if actor['role'] == 'seller':
                _seller_response(detail, session)
            _quotes(detail, actor, session)
        with tabs[2]:
            st.header('Thông tin liên hệ sau lựa chọn')
            if detail['contacts']:
                for label, value in detail['contacts'].items():
                    labels = {'supplier_name': 'Nhà cung cấp', 'supplier_email': 'Email nhà cung cấp',
                              'supplier_phone': 'Điện thoại nhà cung cấp', 'contact_name': 'Tên liên hệ người mua',
                              'contact_email': 'Email người mua', 'contact_phone': 'Điện thoại người mua'}
                    st.write(f"{labels[label]}: {value or 'Chưa cập nhật'}")
                st.info('Lựa chọn này chưa phải đơn hàng hoặc bằng chứng giao dịch thành công.')
            else:
                st.info('Chưa có thông tin liên hệ được chia sẻ cho bạn.')
            st.header('Lịch sử xử lý')
            _history_timeline(detail['events'])
        if actor['role'] == 'admin':
            with tabs[3]:
                if actor['role'] == 'admin' and row['status'] in ('open', 'assigned', 'quoted') and row['delivery_deadline'] >= purchase.today():
                    _matching(session, row, detail['matches'])
                    units = suppliers.list_suppliers(session, admin=True, status='approved')
                    assigned = {m['supplier_id'] for m in detail['matches']}
                    options = [s for s in units if s['id'] not in assigned]
                    if options:
                        with st.form('manual_assignment'):
                            unit = st.selectbox('Phân đơn vị đã duyệt', options=options, format_func=lambda s: s['name'])
                            submitted = st.form_submit_button('Phân nhà cung cấp')
                        if submitted:
                            purchase.assign_supplier(session, request_id, unit['id'])
                            _done('Đã phân nhà cung cấp.')
                else:
                    st.info('Phiếu đã kết thúc, đã chọn báo giá hoặc quá hạn giao nên không thể phân thêm nhà cung cấp.')
    except (auth.AccessDenied, ValueError) as error:
        st.error(str(error))
    except (psycopg.Error, duckdb.Error, OSError):
        st.error('Không thể xử lý nhu cầu lúc này. Nội dung form được giữ để thử lại.')


def _matching(session, row, matches):
    st.header('Gợi ý nhà cung cấp theo quy tắc')
    st.caption('Điểm phù hợp theo quy tắc, không phải xác suất thành công. '
               'Sản phẩm 40 · khu vực 20 · tối thiểu 15 · chuẩn bị 15 · ngân sách 10. '
               'Khai báo nhà cung cấp chưa phải xác minh năng lực hoặc chứng nhận OCOP.')
    # Running/viewing is read-only. No match is persisted until form confirmation.
    if not st.checkbox('Hiển thị kết quả matching', key=f'matching_visible_{row["id"]}'):
        return
    candidates = matching.find_candidates(session, row['id'])
    product_names = {(p['source'], p['product_id']): p['product_name'] for p in catalog_items()}
    labels = {'recommended': 'Đề xuất chính', 'confirmation': 'Cần xác nhận', 'excluded': 'Bị loại'}
    states = {'met': 'Đáp ứng', 'failed': 'Không đáp ứng', 'unknown': 'Cần xác nhận', 'not_applicable': 'Không áp dụng'}
    for group, label in labels.items():
        with st.expander(label, expanded=group != 'excluded'):
            items = [c for c in candidates if c['group'] == group]
            if not items:
                st.caption('Chưa có ứng viên trong nhóm này.')
            for candidate in items:
                st.write(f"{candidate['supplier_name']} · Điểm phù hợp theo quy tắc: {candidate['score']}/100")
                for product in candidate['products'][:3]:
                    name = product_names.get((product['source'], product['product_id']), 'Sản phẩm không còn trong catalog')
                    st.write(f"{name} ({product['source']} · {product['product_id']}) · {product['category']} · {labels[product['group']]}")
                    for criterion in product['criteria']:
                        st.caption(f"{states[criterion['state']]}: {criterion['reason']} (+{criterion['points']})")
    assigned = {m['supplier_id'] for m in matches}
    options = [c for c in candidates if c['group'] != 'excluded' and c['supplier_id'] not in assigned]
    if options:
        with st.form(f'confirm_matching_{row["id"]}'):
            choice = st.selectbox('Ứng viên muốn phân', options=options,
                                  format_func=lambda c: f"{c['supplier_name']} · {labels[c['group']]} · {c['score']}")
            confirmed = st.checkbox('Tôi đã kiểm tra điều kiện, bao gồm các thông tin cần xác nhận.')
            submitted = st.form_submit_button('Xác nhận phân ứng viên')
        if submitted:
            if not confirmed:
                raise ValueError('Cần xác nhận đã kiểm tra điều kiện trước khi phân.')
            purchase.assign_supplier(session, row['id'], choice['supplier_id'], use_matching=True)
            _done('Đã phân và lưu snapshot quy tắc. Chưa gửi thông báo ra ngoài.')
