"""Business connection metrics, restricted to authenticated administrators."""
from datetime import datetime, timedelta

import psycopg
import streamlit as st
from data import auth, metrics, postgres, suppliers
from src.ui_labels import time_label


NO_DATA = 'Chưa có dữ liệu'
KPI_DEFINITIONS = (
    ('created', 'Yêu cầu tạo', 'Số phiếu duy nhất được tạo trong khoảng ngày đã chọn.', 'count'),
    ('assigned', 'Đã phân NCC', 'Số phiếu duy nhất có ít nhất một lượt phân nhà cung cấp.', 'count'),
    ('quoted_requests', 'Có báo giá',
     'Số phiếu duy nhất có ít nhất một báo giá; tính cả lịch sử phiên bản. Từ chối không phải báo giá.', 'count'),
    ('connected', 'Đã kết nối',
     'Số phiếu có trạng thái hiện tại là connected. Không xác nhận thanh toán, giao hàng hoặc doanh thu.', 'count'),
    ('quote_rate', 'Tỷ lệ có báo giá',
     'Số phiếu có báo giá / số phiếu đã phân × 100%. Mẫu số bằng 0: Chưa có dữ liệu.', 'percent'),
    ('median_first_quote_hours', 'Trung vị báo giá đầu (giờ)',
     'Trung vị của (thời điểm báo giá đầu − thời điểm phân) trên từng lượt phân đã có báo giá. '
     'Không tính lượt chưa có báo giá thành 0.', 'hours'),
)
FUNNEL_STAGES = (
    ('created', '1. Tạo yêu cầu'), ('assigned', '2. Phân NCC'),
    ('quoted_requests', '3. Có báo giá'), ('selected', '4. Chọn báo giá'),
    ('connected', '5. Kết nối'),
)


def _value(value, kind='count'):
    if value is None:
        return NO_DATA
    if kind == 'percent':
        return f'{value:.1%}'
    if kind == 'hours':
        return f'{value:.2f}'
    return f'{value:,}'.replace(',', '.')


def _funnel(result):
    st.subheader('Phễu kết nối')
    if not result['created']:
        st.info(NO_DATA)
        return
    total = result['created']
    rows = [{'stage': label, 'count': result[key],
             'share': result[key] / total,
             'left': (total - result[key]) / 2, 'right': (total + result[key]) / 2,
             'center': total / 2} for key, label in FUNNEL_STAGES]
    tooltip = [{'field': 'stage', 'type': 'nominal', 'title': 'Bước'},
               {'field': 'count', 'type': 'quantitative', 'title': 'Số yêu cầu', 'format': ',.0f'},
               {'field': 'share', 'type': 'quantitative', 'title': 'Tỷ lệ trên yêu cầu tạo', 'format': '.1%'}]
    st.vega_lite_chart(spec={
        'data': {'values': rows}, 'height': 280,
        'encoding': {'y': {'field': 'stage', 'type': 'nominal',
                           'sort': [label for _, label in FUNNEL_STAGES],
                           'axis': {'title': None, 'labelFontSize': 13, 'labelPadding': 12,
                                    'labelLimit': 180, 'ticks': False, 'domain': False}},
                     'tooltip': tooltip},
        'layer': [
            {'mark': {'type': 'bar', 'cornerRadius': 5, 'height': 36},
             'encoding': {'x': {'field': 'left', 'type': 'quantitative', 'axis': None,
                                'scale': {'domain': [0, total]}},
                          'x2': {'field': 'right'},
                          'color': {'field': 'stage', 'type': 'nominal', 'legend': None,
                                    'scale': {'domain': [label for _, label in FUNNEL_STAGES],
                                              'range': ['#dceadf', '#bad6c3', '#8cbb9c', '#55966d', '#195b3e']}}}},
            {'mark': {'type': 'text', 'fontSize': 14, 'fontWeight': 'bold'},
             'encoding': {'x': {'field': 'center', 'type': 'quantitative', 'axis': None},
                          'text': {'field': 'count', 'type': 'quantitative', 'format': ',.0f'},
                          'color': {'condition': {'test': "datum.count > 0 && (datum.stage === '4. Chọn báo giá' || datum.stage === '5. Kết nối')", 'value': '#ffffff'},
                                    'value': '#123e2b'}}},
        ], 'config': {'view': {'stroke': None}},
    }, width="stretch")
    st.caption('Mỗi bước đếm yêu cầu duy nhất; tỷ lệ khi di chuột tính trên số yêu cầu tạo. '
               'Chọn báo giá: từng có sự kiện selected hoặc còn selected_quote_id. '
               'Kết nối: trạng thái hiện tại là connected.')


def page():
    session = st.session_state.get('auth_session')
    try:
        # Authorize before rendering filters, supplier names or any business data.
        with postgres.transaction() as connection:
            auth.require_user(connection, session, {'admin'})
        st.title('Hiệu quả kết nối')
        today = datetime.now(metrics.ZONE).date()
        units = suppliers.list_suppliers(session, admin=True)
        names = {None: 'Tất cả nhà cung cấp', **{s['id']: s['name'] for s in units}}
        start_col, end_col, supplier_col = st.columns([1, 1, 1.5], gap='medium')
        with start_col:
            start = st.date_input('Yêu cầu tạo từ ngày', format='DD/MM/YYYY', value=today - timedelta(days=30))
        with end_col:
            end = st.date_input('Đến hết ngày', format='DD/MM/YYYY', value=today)
        with supplier_col:
            supplier_id = st.selectbox('Nhà cung cấp', options=list(names), format_func=names.get)
        result = metrics.dashboard(session, start, end, supplier_id=supplier_id)
        for offset in (0, 3):
            for column, (key, label, formula, kind) in zip(st.columns(3), KPI_DEFINITIONS[offset:offset + 3]):
                with column:
                    st.metric(label, _value(result[key], kind), help=formula)
        st.caption('Nhóm yêu cầu theo ngày tạo tại Asia/Ho_Chi_Minh; kết quả phản ánh trạng thái đến '
                   + time_label(result['viewed_at']))
        st.caption('Lọc nhà cung cấp: chỉ các yêu cầu từng phân cho đơn vị đó; báo giá/phản hồi tính riêng lượt phân của đơn vị. '
                   'Chọn báo giá/kết nối là kết quả của yêu cầu, không quy công cho đơn vị đang lọc.')
        _funnel(result)
        if supplier_id is not None:
            st.caption('Khi lọc NCC, bước báo giá chỉ tính đơn vị đang chọn; bước chọn/kết nối tính ở cấp yêu cầu. '
                       'Vì vậy số ở bước sau có thể lớn hơn bước trước; phễu không thể hiện tỷ lệ chuyển đổi của riêng NCC.')
        st.caption(f"Đã hủy: {_value(result['cancelled'])} · Đóng không tìm được nguồn: {_value(result['closed_no_match'])}")
        st.caption('Đếm yêu cầu duy nhất, gồm mọi phiên bản báo giá đã gửi. Từ chối là phản hồi, không phải báo giá. '
                   'Thời gian chỉ tính trên các yêu cầu/lượt phân đã có phản hồi tương ứng; chưa phản hồi không tính thành 0. '
                   'Connected là xác nhận kết nối trao đổi, không phải doanh thu hay giao dịch thành công.')
        st.subheader('Hiệu quả theo nhà cung cấp')
        table = [{'Nhà cung cấp': s['supplier_name'], 'Lượt được phân': s['assigned'],
                  'Lượt phản hồi': s['responded'], 'Lượt có báo giá': s['quoted'],
                  'Trung vị phản hồi (giờ)': _value(s['median_response_hours'], 'hours')}
                 for s in result['suppliers']]
        if table:
            st.dataframe(table, hide_index=True)
        else:
            st.info(NO_DATA)
    except (auth.AccessDenied, ValueError) as error:
        st.error(str(error))
    except (psycopg.Error, OSError):
        st.error('Không thể đọc dashboard. Kiểm tra kết nối và migration 006.')
