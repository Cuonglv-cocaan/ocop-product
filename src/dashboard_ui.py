"""Business connection metrics, restricted to authenticated administrators."""
from datetime import datetime, timedelta

import psycopg
import streamlit as st
from data import auth, metrics, postgres, suppliers
from src.ui_labels import time_label


def page():
    session = st.session_state.get('auth_session')
    try:
        # Authorize before rendering filters, supplier names or any business data.
        with postgres.transaction() as connection:
            auth.require_user(connection, session, {'admin'})
        st.title('Hiệu quả kết nối')
        today = datetime.now(metrics.ZONE).date()
        start = st.date_input('Yêu cầu tạo từ ngày', format='DD/MM/YYYY', value=today - timedelta(days=30))
        end = st.date_input('Đến hết ngày', format='DD/MM/YYYY', value=today)
        units = suppliers.list_suppliers(session, admin=True)
        names = {None: 'Tất cả nhà cung cấp', **{s['id']: s['name'] for s in units}}
        supplier_id = st.selectbox('Nhà cung cấp', options=list(names), format_func=names.get)
        result = metrics.dashboard(session, start, end, supplier_id=supplier_id)
        st.caption('Nhóm yêu cầu theo ngày tạo tại Asia/Ho_Chi_Minh; kết quả phản ánh trạng thái đến '
                   + time_label(result['viewed_at']))
        st.caption('Lọc nhà cung cấp: chỉ các yêu cầu từng phân cho đơn vị đó; báo giá/phản hồi tính riêng lượt phân của đơn vị. '
                   'Chọn báo giá/kết nối là kết quả của yêu cầu, không quy công cho đơn vị đang lọc.')
        labels = {'created': 'Yêu cầu được tạo', 'assigned': 'Yêu cầu đã phân',
                  'selected': 'Yêu cầu người mua đã chọn báo giá', 'connected': 'Người mua xác nhận đã kết nối',
                  'cancelled': 'Yêu cầu đã hủy', 'closed_no_match': 'Đóng không tìm được nguồn'}
        for key, label in labels.items():
            st.metric(label, result[key])
        st.metric('Tỷ lệ yêu cầu đã phân có ít nhất một báo giá',
                  'Chưa có dữ liệu' if result['quote_rate'] is None else f"{result['quote_rate']:.1%}")
        latency = result['median_first_quote_hours']
        st.metric('Trung vị từ lúc phân đến báo giá đầu mỗi lượt phân (giờ)',
                  'Chưa có dữ liệu' if latency is None else f'{latency:.2f}')
        st.caption('Đếm yêu cầu duy nhất, gồm mọi phiên bản báo giá đã gửi. Từ chối là phản hồi, không phải báo giá. '
                   'Thời gian chỉ tính trên các yêu cầu/lượt phân đã có phản hồi tương ứng; chưa phản hồi không tính thành 0. '
                   'Connected là xác nhận kết nối trao đổi, không phải doanh thu hay giao dịch thành công.')
        table = [{'Nhà cung cấp': s['supplier_name'], 'Lượt được phân': s['assigned'],
                  'Lượt phản hồi': s['responded'], 'Lượt có báo giá': s['quoted'],
                  'Trung vị phản hồi (giờ)': 'Chưa có dữ liệu' if s['median_response_hours'] is None
                  else f"{s['median_response_hours']:.2f}"} for s in result['suppliers']]
        if table:
            st.dataframe(table, hide_index=True)
        else:
            st.info('Chưa có dữ liệu nhà cung cấp trong nhóm yêu cầu đã chọn.')
    except (auth.AccessDenied, ValueError) as error:
        st.error(str(error))
    except (psycopg.Error, OSError):
        st.error('Không thể đọc dashboard. Kiểm tra kết nối và migration 006.')
