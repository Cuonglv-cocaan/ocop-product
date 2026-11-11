"""Role-specific manual matching and quote workflow."""
from datetime import datetime, time, timedelta

import duckdb
import psycopg
import streamlit as st
from data import auth, purchase, suppliers
from src import auth_ui

STATES = {'open': 'Mới tạo', 'assigned': 'Đã phân nhà cung cấp', 'quoted': 'Đã có báo giá',
          'selected': 'Đã chọn để trao đổi', 'connected': 'Buyer đã xác nhận kết nối',
          'cancelled': 'Đã hủy', 'closed_no_match': 'Đóng: chưa có phương án'}
QUOTE_STATES = {'active': 'Hiện hành', 'superseded': 'Đã thay thế', 'selected': 'Đã chọn'}


def _done(message):
    st.session_state['_purchase_notice'] = message
    st.rerun()


def request_form(row=None):
    row = row or {}
    reference = st.session_state.get('purchase_reference', {}) if not row else {}
    catalog = suppliers.catalog_items()
    choices = {None: 'Không chọn sản phẩm tham chiếu'}
    choices.update({(p['source'], p['product_id']): f"{p['product_name']} ({p['source']} · {p['product_id']})" for p in catalog})
    initial = (row.get('source'), row.get('product_id')) if row.get('source') else (
        (reference['source'], reference['product_id']) if reference.get('source') else None)
    if initial and initial not in choices:
        choices[initial] = 'Sản phẩm không còn trong catalog'
    st.caption('Dùng phần liên hệ riêng bên dưới; không ghi email/điện thoại vào mô tả hay yêu cầu bổ sung.')
    with st.form(f'purchase_form_{row.get("id", "new")}'):
        title = st.text_input('Tiêu đề *', value=row.get('title', reference.get('title', '')))
        category = st.text_input('Danh mục', value=row.get('category', reference.get('category', '')))
        description = st.text_area('Mô tả nhu cầu *', value=row.get('description', ''))
        quantity = st.text_input('Số lượng *', value=str(row.get('quantity', '')))
        unit = st.text_input('Đơn vị tính *', value=row.get('unit', ''))
        budget = st.text_input('Ngân sách VND (tùy chọn)', value='' if row.get('budget') is None else str(row['budget']))
        budget_type = st.selectbox('Loại ngân sách', options=['total', 'per_unit'],
                                   index=0 if row.get('budget_type', 'total') == 'total' else 1,
                                   format_func=lambda v: 'Tổng ngân sách' if v == 'total' else 'Mỗi đơn vị')
        location = st.text_input('Địa điểm giao *', value=row.get('delivery_location', ''))
        deadline = st.date_input('Hạn giao *', value=row.get('delivery_deadline', purchase.today() + timedelta(days=7)))
        additional = st.text_area('Yêu cầu bổ sung', value=row.get('additional_requirements', ''))
        selected = st.selectbox('Sản phẩm tham chiếu', options=list(choices), index=list(choices).index(initial),
                                format_func=lambda key: choices[key])
        st.caption('Liên hệ chỉ chia sẻ với nhà cung cấp được chọn. Nhập ít nhất email hoặc điện thoại.')
        contact_name = st.text_input('Tên liên hệ riêng', value=row.get('contact_name', ''))
        contact_email = st.text_input('Email liên hệ riêng', value=row.get('contact_email', ''))
        contact_phone = st.text_input('Điện thoại liên hệ riêng', value=row.get('contact_phone', ''))
        submitted = st.form_submit_button('Lưu thay đổi nhu cầu' if row else 'Tạo phiếu nhu cầu')
    if submitted:
        fields = dict(title=title, category=category, description=description, quantity=quantity, unit=unit,
                      budget=budget, budget_type=budget_type, delivery_location=location, delivery_deadline=deadline,
                      additional_requirements=additional, source=selected[0] if selected else '',
                      product_id=selected[1] if selected else '', contact_name=contact_name,
                      contact_email=contact_email, contact_phone=contact_phone)
        session = st.session_state.get('auth_session')
        if row:
            purchase.edit_request(session, row['id'], fields)
        else:
            request_id = purchase.create_request(session, fields)
            st.session_state.pop('purchase_reference', None)
            st.session_state['purchase_focus'] = request_id
        _done('Đã lưu phiếu nhu cầu.')


def _quotes(detail, actor, session):
    row, quotes = detail['request'], detail['quotes']
    st.subheader('So sánh báo giá' if actor['role'] != 'seller' else 'Lịch sử báo giá của đơn vị')
    if quotes:
        st.dataframe([{'Mã': q['id'], 'Đơn vị cung cấp': q['supplier_name'], 'Phiên bản': q['version'],
                       'Số lượng': str(q['quantity']), 'Đơn vị tính': q['unit'], 'Đơn giá VND': str(q['unit_price']),
                       'Phí giao VND': 'Chưa bao gồm' if q['shipping_fee'] is None else str(q['shipping_fee']),
                       'Tổng tiền VND': str(q['total_amount']), 'Giao dự kiến': q['expected_delivery'],
                       'Hiệu lực đến': q['valid_until'], 'Trạng thái': QUOTE_STATES[q['status']],
                       'Chi phí chưa gồm': q['excluded_costs'], 'Ghi chú': q['notes']} for q in quotes], hide_index=True)
    else:
        st.info('Chưa có báo giá.')
    for match in detail['matches']:
        if match['status'] == 'declined':
            st.info(f"{match['supplier_name']} không thể đáp ứng: {match['decline_reason']}")
    if actor['role'] == 'buyer' and row['status'] == 'quoted':
        candidates = [q for q in quotes if q['status'] == 'active' and q['valid_until'] > datetime.now(purchase.ZONE)]
        if candidates:
            with st.form('choose_quote'):
                quote_id = st.selectbox('Phương án muốn chọn', options=[q['id'] for q in candidates])
                confirmed = st.checkbox('Tôi hiểu đây chỉ là lựa chọn để tiếp tục trao đổi, chưa phải đơn hàng hay giao dịch thành công.')
                submitted = st.form_submit_button('Chọn phương án')
            if submitted:
                if not confirmed:
                    raise ValueError('Vui lòng xác nhận ý nghĩa của việc lựa chọn.')
                purchase.select_quote(session, row['id'], quote_id)
                _done('Đã chọn phương án để tiếp tục trao đổi.')


def _seller_response(detail, session):
    row = detail['request']
    if row['status'] not in ('assigned', 'quoted'):
        return
    match = st.selectbox('Đơn vị phản hồi', options=detail['matches'], format_func=lambda m: m['supplier_name'])
    with st.form('submit_supplier_quote'):
        quantity = st.text_input('Số lượng đáp ứng', value=str(row['quantity']))
        st.caption('Đơn vị tính: ' + row['unit'])
        price = st.text_input('Đơn giá VND')
        shipping = st.text_input('Phí giao hàng VND (trống = chưa gồm)')
        delivery = st.date_input('Ngày giao dự kiến', value=row['delivery_deadline'])
        validity = st.date_input('Báo giá có hiệu lực hết ngày', value=purchase.today() + timedelta(days=1))
        excluded = st.text_area('Chi phí chưa bao gồm (ghi Không có nếu đã gồm hết)')
        notes = st.text_area('Ghi chú báo giá')
        submitted = st.form_submit_button('Gửi phiên bản báo giá mới')
    if submitted:
        purchase.submit_quote(session, row['id'], match['id'], quantity=quantity, unit=row['unit'], unit_price=price,
                              shipping_fee=shipping, expected_delivery=delivery,
                              valid_until=datetime.combine(validity, time.max, purchase.ZONE), notes=notes, excluded_costs=excluded)
        _done('Đã gửi báo giá. Tổng tiền được tính trên server.')
    with st.form('decline_match'):
        reason = st.text_area('Lý do không thể đáp ứng')
        declined = st.form_submit_button('Không thể đáp ứng')
    if declined:
        purchase.decline_request(session, row['id'], match['id'], reason)
        _done('Đã ghi nhận phản hồi không thể đáp ứng.')


def page():
    st.header('Nhu cầu và kết nối cung cầu')
    session = st.session_state.get('auth_session')
    if session is None:
        st.info('Vui lòng đăng nhập để tạo hoặc theo dõi phiếu nhu cầu.')
        auth_ui.login()
        return
    try:
        actor = auth.current_user(session)
        notice = st.session_state.pop('_purchase_notice', None)
        if notice:
            st.success(notice)
        if actor['role'] == 'buyer':
            with st.expander('Tạo nhu cầu mới', expanded=bool(st.session_state.get('purchase_reference'))):
                request_form()
        rows = purchase.list_requests(session)
        st.subheader({'buyer': 'Phiếu nhu cầu của tôi', 'seller': 'Nhu cầu được phân cho đơn vị của tôi', 'admin': 'Quản lý và theo dõi nhu cầu'}[actor['role']])
        if not rows:
            st.info('Chưa có phiếu nhu cầu trong phạm vi quyền của bạn.')
            return
        st.dataframe([{'Mã': r['id'], 'Tiêu đề': r['title'], 'Trạng thái': STATES[r['status']],
                       'Số lượng': str(r['quantity']), 'Đơn vị': r['unit'], 'Hạn giao': r['delivery_deadline']} for r in rows], hide_index=True)
        ids = [r['id'] for r in rows]
        focus = st.session_state.pop('purchase_focus', None)
        request_id = st.selectbox('Phiếu nhu cầu', options=ids, index=ids.index(focus) if focus in ids else 0)
        detail = purchase.request_detail(session, request_id)
        row = detail['request']
        st.subheader(row['title'])
        st.write('Trạng thái: ' + STATES[row['status']])
        st.write(row['description'])
        st.write(f"Danh mục: {row['category'] or 'Chưa cập nhật'} · Số lượng: {row['quantity']} {row['unit']}")
        st.write(f"Giao tại: {row['delivery_location']} · Hạn giao: {row['delivery_deadline']}")
        st.write('Yêu cầu bổ sung: ' + (row['additional_requirements'] or 'Chưa cập nhật'))
        st.write('Ngân sách: ' + ('Chưa cập nhật' if row['budget'] is None else f"{row['budget']} VND / " + ('đơn vị' if row['budget_type'] == 'per_unit' else 'tổng')))
        if row['source']:
            product = next((p for p in suppliers.catalog_items() if (p['source'], p['product_id']) == (row['source'], row['product_id'])), None)
            st.caption(f"Tham chiếu: {product['product_name'] if product else 'Sản phẩm không còn trong catalog'} ({row['source']} · {row['product_id']})")
        if actor['role'] == 'buyer' and row['status'] == 'open':
            with st.expander('Sửa nhu cầu trước khi phân công'):
                request_form(row)
        if actor['role'] == 'admin' and row['status'] in ('open', 'assigned', 'quoted'):
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
        if detail['matches']:
            st.subheader('Tiến độ phân công')
            match_states = {'assigned': 'Đã phân, chờ phản hồi', 'quoted': 'Đã báo giá',
                            'declined': 'Không thể đáp ứng', 'selected': 'Đã được buyer chọn'}
            st.dataframe([{'Đơn vị': m['supplier_name'], 'Trạng thái': match_states[m['status']],
                           'Thời điểm phân': m['assigned_at']} for m in detail['matches']], hide_index=True)
        _quotes(detail, actor, session)
        if actor['role'] == 'seller':
            _seller_response(detail, session)
        if detail['contacts']:
            st.subheader('Thông tin liên hệ sau lựa chọn')
            for label, value in detail['contacts'].items():
                labels = {'supplier_name': 'Nhà cung cấp', 'supplier_email': 'Email nhà cung cấp',
                          'supplier_phone': 'Điện thoại nhà cung cấp', 'contact_name': 'Tên liên hệ buyer',
                          'contact_email': 'Email buyer', 'contact_phone': 'Điện thoại buyer'}
                st.write(f"{labels[label]}: {value or 'Chưa cập nhật'}")
            st.info('Lựa chọn này chưa phải đơn hàng hoặc bằng chứng giao dịch thành công.')
        if actor['role'] in ('buyer', 'admin') and row['status'] not in purchase.TERMINAL:
            if actor['role'] == 'buyer' and row['status'] == 'selected':
                if st.button('Xác nhận đã kết nối để trao đổi'):
                    purchase.close_request(session, request_id, 'connected')
                    _done('Đã ghi nhận buyer xác nhận kết nối.')
            if st.button('Hủy phiếu nhu cầu'):
                purchase.close_request(session, request_id, 'cancelled')
                _done('Đã hủy phiếu. Bạn có thể tạo nhu cầu mới.')
            if row['status'] in ('open', 'assigned', 'quoted') and st.button('Đóng vì không tìm được phương án'):
                purchase.close_request(session, request_id, 'closed_no_match')
                _done('Đã đóng phiếu không có phương án phù hợp.')
        st.subheader('Lịch sử xử lý')
        for event in detail['events']:
            st.write(f"{event['created_at']} · #{event['actor_id']} · {event['content']}")
    except (auth.AccessDenied, ValueError) as error:
        st.error(str(error))
    except (psycopg.Error, duckdb.Error, OSError):
        st.error('Không thể xử lý nhu cầu lúc này. Nội dung form được giữ để thử lại.')
