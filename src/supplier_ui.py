"""Vietnamese supplier applications, reviews and catalog supply links."""
import duckdb
import psycopg
import streamlit as st
from data import auth, postgres, suppliers

STATUS_LABELS = {'pending': 'Chờ duyệt', 'approved': 'Đã duyệt',
                 'rejected': 'Bị từ chối', 'suspended': 'Tạm ngưng'}
LABELS = {'name': 'Tên đơn vị *', 'entity_type': 'Loại đơn vị', 'description': 'Mô tả',
          'province': 'Tỉnh / thành', 'email': 'Email', 'phone': 'Điện thoại', 'delivery_areas': 'Khu vực giao hàng'}


def _success(message):
    st.session_state['_supplier_notice'] = message
    st.rerun()


def _fields(row=None):
    row = row or {}
    return {key: (st.text_area if key in ('description', 'delivery_areas') else st.text_input)(
        label, value=row.get(key) or '') for key, label in LABELS.items()}


def _details(row):
    if row['is_demo']:
        st.warning('Dữ liệu mô phỏng cho demo môn học, chưa xác minh thực tế.')
    st.subheader(row['name'])
    st.write('Trạng thái: ' + STATUS_LABELS[row['status']])
    for key, label in LABELS.items():
        if key != 'name':
            st.write(f"{label}: {row.get(key) or 'Chưa cập nhật'}")
    if row['rejection_reason']:
        st.warning('Lý do từ chối / tạm ngưng: ' + row['rejection_reason'])


def _products(session, row, actor):
    st.subheader('Sản phẩm có thể cung ứng')
    links = suppliers.list_products(session, row['id'])
    for link in links:
        st.markdown(f"**{link['product_name']}**")
        st.caption(f"{link['source']} · {link['product_id']} · " + ('Đang cung ứng' if link['is_active'] else 'Ngừng cung ứng'))
        for key, label in (('minimum_order', 'Đặt tối thiểu'), ('unit', 'Đơn vị tính'),
                           ('preparation_time', 'Thời gian chuẩn bị'), ('capacity_description', 'Năng lực cung ứng')):
            value = link[key]
            st.write(f"{label}: {value if value not in (None, '') else 'Chưa cập nhật'}")
    if not links:
        st.info('Chưa có sản phẩm cung ứng.')
    if actor['role'] != 'seller' or row['status'] != 'approved':
        st.info('Quản lý sản phẩm cần đơn vị đã duyệt và tài khoản seller là thành viên.')
        return
    catalog = suppliers.catalog_items()
    options = {(p['source'], p['product_id']): p['product_name'] or 'Chưa cập nhật' for p in catalog}
    # Retain removed catalog keys for viewing/deactivating historical links.
    for link in links:
        options.setdefault((link['source'], link['product_id']), link['product_name'])
    if not options:
        st.info('Catalog chưa có sản phẩm để liên kết.')
        return
    key = st.selectbox('Chọn sản phẩm', options=list(options),
                       format_func=lambda k: f'{options[k]} ({k[0]} · {k[1]})', key=f'supply_key_{row["id"]}')
    current = next((link for link in links if (link['source'], link['product_id']) == key), {})
    with st.form(f'supply_{row["id"]}_{key[0]}_{key[1]}'):
        quantity = st.text_input('Số lượng đặt tối thiểu (để trống nếu chưa biết)',
                                 value=str(current.get('minimum_order') or ''))
        unit = st.text_input('Đơn vị tính', value=current.get('unit', ''))
        preparation = st.text_input('Thời gian chuẩn bị', value=current.get('preparation_time', ''))
        capacity = st.text_area('Năng lực cung ứng', value=current.get('capacity_description', ''))
        active = st.checkbox('Đang cung ứng', value=current.get('is_active', True))
        submitted = st.form_submit_button('Lưu cung ứng')
        stop = st.form_submit_button('Ngừng cung ứng liên kết hiện có') if current else False
    if submitted:
        suppliers.save_product(session, row['id'], *key, minimum_order=quantity, unit=unit,
                               preparation_time=preparation, capacity_description=capacity, is_active=active)
        _success('Đã lưu thông tin cung ứng.')
    if stop:
        suppliers.stop_product(session, row['id'], *key)
        _success('Đã ngừng cung ứng, liên kết lịch sử được giữ nguyên.')


def page(admin=False):
    st.header('Duyệt nhà cung cấp' if admin else 'Nhà cung cấp của tôi')
    notice = st.session_state.pop('_supplier_notice', None)
    if notice:
        st.success(notice)
    session = st.session_state.get('auth_session')
    try:
        actor = auth.current_user(session)
        if admin:
            # Check permission before rendering any admin controls or list.
            with postgres.transaction() as connection:
                auth.require_user(connection, session, {'admin'})
            status = st.selectbox('Lọc trạng thái', options=[None, *suppliers.STATUSES], index=1,
                                  format_func=lambda value: 'Tất cả' if value is None else STATUS_LABELS[value])
            rows = suppliers.list_suppliers(session, admin=True, status=status)
        else:
            rows = suppliers.list_suppliers(session)
        if rows:
            if admin:
                st.dataframe([{'Mã hồ sơ': r['id'], 'Tên đơn vị': r['name'],
                               'Trạng thái': STATUS_LABELS[r['status']],
                               'Tỉnh / thành': r['province'] or 'Chưa cập nhật'} for r in rows], hide_index=True)
            supplier_id = st.selectbox('Đơn vị', options=[r['id'] for r in rows],
                                      format_func=lambda sid: next(r['name'] for r in rows if r['id'] == sid))
            row = suppliers.get_supplier(session, supplier_id)
            _details(row)
            if admin:
                st.caption(f"Người tạo: #{row['created_by']} · Người duyệt: {row['reviewed_by'] or 'Chưa cập nhật'} · "
                           f"Thời điểm duyệt: {row['reviewed_at'] or 'Chưa cập nhật'}")
                allowed = {'pending': ['approved', 'rejected'], 'approved': ['suspended'],
                           'rejected': ['approved'], 'suspended': ['approved']}[row['status']]
                with st.form(f'review_supplier_{supplier_id}'):
                    decision = st.selectbox('Quyết định', options=allowed, format_func=lambda value: STATUS_LABELS[value])
                    reason = st.text_area('Lý do từ chối / tạm ngưng')
                    submit = st.form_submit_button('Xác nhận quyết định')
                if submit:
                    suppliers.review_application(session, supplier_id, decision, reason)
                    _success('Đã cập nhật quyết định.')
            elif row['status'] != 'suspended':
                with st.form(f'profile_{supplier_id}'):
                    fields = _fields(row)
                    save = st.form_submit_button('Lưu hồ sơ')
                    resubmit = st.form_submit_button('Gửi duyệt lại') if row['status'] == 'rejected' else False
                if save or resubmit:
                    suppliers.edit_profile(session, supplier_id, fields, resubmit=resubmit)
                    _success('Đã gửi duyệt lại.' if resubmit else 'Đã lưu hồ sơ.')
            _products(session, row, actor)
        else:
            st.info('Chưa có hồ sơ phù hợp.')
        if not admin and actor['role'] in ('buyer', 'seller'):
            with st.expander('Đăng ký đơn vị mới', expanded=not rows):
                with st.form('register_supplier'):
                    fields = _fields()
                    submitted = st.form_submit_button('Gửi hồ sơ đăng ký')
                if submitted:
                    supplier_id = suppliers.create_application(session, fields)
                    _success(f'Đã gửi hồ sơ #{supplier_id}, đang chờ admin duyệt.')
    except (auth.AccessDenied, ValueError) as error:
        st.error(str(error))
    except (psycopg.Error, duckdb.Error, OSError):
        st.error('Không thể truy cập nhà cung cấp lúc này. Nội dung form được giữ để thử lại.')
