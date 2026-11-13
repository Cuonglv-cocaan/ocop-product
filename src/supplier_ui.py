"""Vietnamese supplier applications, reviews and catalog supply links."""
import duckdb
from contextlib import nullcontext
import psycopg
import streamlit as st
from data import auth, postgres, suppliers
from crawlers.provinces import PROVINCE_NAMES
from src import auth_ui
from src.ui_labels import field_line, status_label, number_label, money_label, time_label

STATUS_LABELS = {'pending': 'Chờ duyệt', 'approved': 'Đã duyệt',
                 'rejected': 'Bị từ chối', 'suspended': 'Tạm ngưng'}
LABELS = {'name': 'Tên đơn vị *', 'entity_type': 'Loại đơn vị', 'description': 'Mô tả',
          'province': 'Tỉnh / thành', 'email': 'Email', 'phone': 'Điện thoại', 'delivery_areas': 'Khu vực giao hàng'}


def _success(message):
    st.session_state['_supplier_notice'] = message
    st.rerun()


def _fields(row=None, buyer=False):
    row = row or {}
    fields = {}
    for key, label in LABELS.items():
        value = row.get(key) or ''
        if buyer and key == 'delivery_areas':
            fields[key] = value
        elif buyer and key in ('entity_type', 'province'):
            choices = (['Doanh nghiệp', 'Hợp tác xã', 'Tổ hợp tác', 'Hộ kinh doanh',
                        'Cá nhân', 'Khác'] if key == 'entity_type' else PROVINCE_NAMES)
            options = list(dict.fromkeys(['', *choices, *([value] if value else [])]))
            fields[key] = st.selectbox(label, options=options, index=options.index(value),
                                       format_func=lambda item: item or 'Chưa chọn')
        elif buyer and key == 'description':
            fields[key] = st.text_area(
                label, value=value,
                placeholder='Ví dụ: Hợp tác xã chuyên trà và mật ong, tự sản xuất tại địa phương; '
                            'có thể cung cấp khoảng 500 hộp/tháng, nhận đóng gói quà tặng.')
        else:
            fields[key] = (st.text_area if key in ('description', 'delivery_areas') else st.text_input)(
                label, value=value)
    return fields


def _details(row, buyer=False):
    st.subheader(row['name'])
    status_label(row['status'], STATUS_LABELS[row['status']])
    for key, label in LABELS.items():
        if key != 'name' and not (buyer and key == 'delivery_areas'):
            field_line((label, row.get(key) or 'Chưa cập nhật'))
    if row['rejection_reason']:
        st.warning('Lý do từ chối / tạm ngưng: ' + row['rejection_reason'])


def _products(session, row, actor):
    st.header('Sản phẩm có thể cung ứng')
    links = suppliers.list_products(session, row['id'])
    for link in links:
        with st.expander(link['product_name']):
            st.markdown(f"**{link['product_name']}**")
            st.caption(f"{link['source']} · {link['product_id']} · " + ('Đang cung ứng' if link['is_active'] else 'Ngừng cung ứng'))
            for key, label in (('minimum_order', 'Đặt tối thiểu'), ('unit', 'Đơn vị tính'),
                               ('preparation_time', 'Thời gian chuẩn bị'), ('capacity_description', 'Năng lực cung ứng')):
                value = link[key]
                field_line((label, (number_label(value) if key == 'minimum_order' else value) if value not in (None, '') else 'Chưa cập nhật'))
            st.caption('Danh mục khai báo: ' + (link.get('category') or 'Chưa cập nhật')
                       + ' · Khu vực phục vụ: ' + (', '.join(link.get('service_regions', [])) or 'Chưa cập nhật'))
            days = link.get('preparation_days')
            price = link.get('reference_price')
            st.caption('Ngày chuẩn bị khai báo: ' + ('Chưa cập nhật' if days is None else str(days))
                       + ' · Giá tham khảo tự khai báo: '
                       + ('Chưa cập nhật' if price is None else f"{money_label(price)} / {link.get('reference_price_unit') or 'Chưa cập nhật đơn vị'}"))
    if not links:
        st.info('Chưa có sản phẩm cung ứng.')
    if actor['role'] != 'seller' or row['status'] != 'approved':
        st.info('Bạn có thể quản lý sản phẩm sau khi hồ sơ đơn vị được duyệt.')
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
        st.caption('Thông tin dưới đây giúp tìm yêu cầu mua hàng phù hợp với khả năng cung ứng.')
        category = st.text_input('Danh mục cung ứng khai báo', value=current.get('category', ''))
        regions = st.text_area('Tỉnh/thành phục vụ (mỗi dòng một tỉnh/thành, ghi tên đầy đủ)',
                               value='\n'.join(current.get('service_regions', [])))
        days = st.text_input('Số ngày chuẩn bị (số nguyên, trống nếu chưa biết)',
                             value='' if current.get('preparation_days') is None else str(current['preparation_days']))
        price = st.text_input('Giá tham khảo tự khai báo (VND mỗi đơn vị, tùy chọn)',
                              value='' if current.get('reference_price') is None else str(current['reference_price']))
        price_unit = st.text_input('Đơn vị của giá tham khảo', value=current.get('reference_price_unit', ''))
        st.caption('Giá tham khảo chưa xác nhận vận chuyển/thuế; khác giá catalog và báo giá thực tế theo yêu cầu.')
        active = st.checkbox('Đang cung ứng', value=current.get('is_active', True))
        submitted = st.form_submit_button('Lưu cung ứng', type='primary')
        stop = st.form_submit_button('Ngừng cung ứng liên kết hiện có') if current else False
    if submitted:
        suppliers.save_product(session, row['id'], *key, minimum_order=quantity, unit=unit,
                               preparation_time=preparation, capacity_description=capacity, is_active=active,
                               structured=dict(category=category, service_regions=[r.strip() for r in regions.splitlines() if r.strip()],
                                               preparation_days=days, reference_price=price, reference_price_unit=price_unit))
        _success('Đã lưu thông tin cung ứng.')
    if stop:
        suppliers.stop_product(session, row['id'], *key)
        _success('Đã ngừng cung ứng, liên kết lịch sử được giữ nguyên.')


def page(admin=False, embedded=False):
    notice = st.session_state.pop('_supplier_notice', None)
    if notice:
        st.success(notice)
    session = st.session_state.get('auth_session')
    try:
        actor = auth.current_user(session)
        buyer = actor['role'] == 'buyer' and not admin
        if not embedded:
            st.title('Duyệt nhà cung cấp' if admin else
                      ('Đăng ký cung cấp' if buyer else 'Quản lý cung ứng'))
        if buyer:
            st.caption('Gửi hồ sơ để đăng ký làm nhà cung cấp và theo dõi kết quả duyệt tại đây.')
        if admin:
            # Check permission before rendering any admin controls or list.
            with postgres.transaction() as connection:
                auth.require_user(connection, session, {'admin'})
            status = st.selectbox('Lọc trạng thái', options=[None, *suppliers.STATUSES], index=1,
                                  format_func=lambda value: 'Tất cả' if value is None else STATUS_LABELS[value])
            rows = suppliers.list_suppliers(session, admin=True, status=status)
        else:
            rows = suppliers.list_suppliers(session)
        seller = actor['role'] == 'seller' and not admin
        profile_tab, products_tab = st.tabs(['Hồ sơ đơn vị', 'Sản phẩm cung ứng']) if seller else (None, None)
        if rows:
            if admin:
                st.dataframe([{'Mã hồ sơ': r['id'], 'Tên đơn vị': r['name'],
                               'Trạng thái': STATUS_LABELS[r['status']],
                               'Tỉnh / thành': r['province'] or 'Chưa cập nhật'} for r in rows], hide_index=True)
            supplier_id = st.selectbox('Đơn vị', options=[r['id'] for r in rows],
                                      format_func=lambda sid: next(r['name'] for r in rows if r['id'] == sid))
            row = suppliers.get_supplier(session, supplier_id)
            if seller:
                if row['status'] == 'approved':
                    st.success('Hồ sơ đã duyệt · Bạn có thể cập nhật sản phẩm và phản hồi yêu cầu báo giá.')
                elif row['status'] == 'pending':
                    st.info('Hồ sơ đang chờ duyệt · Bạn có thể cập nhật thông tin đơn vị.')
                elif row['status'] == 'rejected':
                    st.warning('Hồ sơ bị từ chối · Xem lý do, cập nhật hồ sơ và gửi duyệt lại.')
                else:
                    st.warning('Hồ sơ đang tạm ngưng · Xem lý do trong Hồ sơ đơn vị.')
            with profile_tab if seller else nullcontext():
                with st.expander('Thông tin hồ sơ') if seller else nullcontext():
                    _details(row, buyer=buyer)
                if admin:
                    st.caption(f"Người tạo: #{row['created_by']} · Người duyệt: {row['reviewed_by'] or 'Chưa cập nhật'} · "
                               f"Thời điểm duyệt: {time_label(row['reviewed_at'])}")
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
                        fields = _fields(row, buyer=buyer)
                        save = st.form_submit_button('Lưu hồ sơ', type='primary')
                        resubmit = st.form_submit_button('Gửi duyệt lại') if row['status'] == 'rejected' else False
                    if save or resubmit:
                        suppliers.edit_profile(session, supplier_id, fields, resubmit=resubmit)
                        _success('Đã gửi duyệt lại.' if resubmit else 'Đã lưu hồ sơ.')
            with products_tab if seller else nullcontext():
                _products(session, row, actor)
        else:
            st.info('Bạn chưa có hồ sơ đăng ký.' if buyer or seller else 'Chưa có hồ sơ phù hợp.')
            if seller:
                with products_tab:
                    st.info('Đăng ký hồ sơ đơn vị và chờ duyệt để quản lý sản phẩm cung ứng.')
        with profile_tab if seller else nullcontext():
            if not admin and actor['role'] in ('buyer', 'seller'):
                with st.expander('Đăng ký đơn vị mới', expanded=not rows):
                    with st.form('register_supplier'):
                        fields = _fields(buyer=buyer)
                        submitted = st.form_submit_button('Gửi hồ sơ đăng ký')
                    if submitted:
                        supplier_id = suppliers.create_application(session, fields)
                        _success(f'Đã gửi hồ sơ #{supplier_id}, đang chờ admin duyệt.')
            if seller:
                with st.expander('Đăng ký trước đây'):
                    st.caption('Các đăng ký đã gửi qua biểu mẫu cũ.')
                    auth_ui.requests_page(embedded=True, legacy=True)
    except (auth.AccessDenied, ValueError) as error:
        st.error(str(error))
    except (psycopg.Error, duckdb.Error, OSError):
        st.error('Không thể truy cập nhà cung cấp lúc này. Nội dung form được giữ để thử lại.')
