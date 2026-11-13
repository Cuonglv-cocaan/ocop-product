"""Streamlit login and private pages; passwords and private results aren't cached."""
import psycopg
import streamlit as st
from data import accounts, auth, leads
from src.ui_labels import time_label, role_label


def login():
    st.title('Đăng nhập')
    with st.form('internal_login', clear_on_submit=True):
        username = st.text_input('Tên đăng nhập', key='login_username')
        password = st.text_input('Mật khẩu', type='password', key='login_password')
        submitted = st.form_submit_button('Đăng nhập')
    if submitted:
        try:
            session = auth.authenticate(username, password)
        except auth.AccessDenied as error:
            st.error(str(error))
        except (psycopg.Error, OSError, ValueError):
            st.error('Không thể đăng nhập lúc này. Vui lòng thử lại.')
        else:
            reference = st.session_state.get('purchase_reference')
            auth.logout(st.session_state)
            st.session_state['auth_session'] = session
            if isinstance(reference, dict):
                st.session_state['purchase_reference'] = {key: reference.get(key, '') for key in ('source', 'product_id', 'title', 'category')}
            st.session_state['page'] = 'Nhu cầu' if reference else 'Trang chủ'
            st.rerun()


def identity():
    session = st.session_state.get('auth_session')
    if session is None:
        return None
    try:
        return auth.current_user(session)
    except auth.AccessDenied:
        auth.logout(st.session_state)
        st.warning('Phiên đăng nhập đã hết hiệu lực. Vui lòng đăng nhập lại.')
    except (psycopg.Error, OSError, ValueError):
        st.warning('Không thể kiểm tra phiên đăng nhập lúc này.')
    return None


def requests_page(admin=False, embedded=False, legacy=False):
    if embedded:
        st.header('Yêu cầu liên hệ' if admin else ('Yêu cầu liên hệ cũ' if legacy else 'Yêu cầu đã gửi'))
    else:
        st.title('Quản lý yêu cầu' if admin else 'Yêu cầu của tôi')
    session = st.session_state.get('auth_session')
    try:
        notice = st.session_state.pop('_lead_notice', None)
        if notice:
            st.success(notice)
        if admin:
            users = accounts.list_accounts(session)
        rows = leads.read_leads(session)
        if rows:
            st.dataframe([{'Mã': r['id'], 'Ngày gửi': time_label(r.get('created_at')),
                           'Loại yêu cầu': r.get('kind') or 'Chưa cập nhật',
                           'Tên liên hệ': r.get('name') or 'Chưa cập nhật',
                           'Email': r.get('email') or 'Chưa cung cấp',
                           'Điện thoại': r.get('phone') or 'Chưa cung cấp',
                           'Nội dung': r.get('note') or 'Chưa cập nhật'} for r in rows], hide_index=True)
            lead_id = st.selectbox('Yêu cầu cần sửa', options=[row['id'] for row in rows])
            current = next(row for row in rows if row['id'] == lead_id)
            if st.session_state.get('_editing_lead') != lead_id:
                st.session_state['private_note'] = current['note']
                st.session_state['_editing_lead'] = lead_id
            with st.form('edit_request'):
                note = st.text_area('Nội dung cập nhật', key='private_note')
                submitted = st.form_submit_button('Lưu nội dung', type='primary')
            if submitted:
                leads.update_note(session, lead_id, note)
                st.session_state['_lead_notice'] = 'Đã lưu nội dung.'
                st.rerun()
        else:
            st.info('Chưa có yêu cầu trước đây.' if legacy else
                    ('Bạn chưa gửi yêu cầu nào. Điền biểu mẫu phía trên để gửi yêu cầu đầu tiên.'
                     if embedded else 'Chưa có yêu cầu.'))
        if admin and users:
            st.header('Tài khoản')
            st.dataframe([{'Mã': u['id'], 'Tài khoản': u['username'], 'Vai trò': role_label(u['role']),
                           'Trạng thái': 'Hoạt động' if u['active'] else 'Đã khóa'} for u in users], hide_index=True)
            user_id = st.selectbox('Tài khoản', options=[u['id'] for u in users],
                                   format_func=lambda uid: next(u['username'] for u in users if u['id'] == uid))
            user = next(u for u in users if u['id'] == user_id)
            with st.form('account_status'):
                active = st.checkbox('Hoạt động', value=user['active'], key=f'account_active_{user_id}')
                submitted = st.form_submit_button('Cập nhật trạng thái')
            if submitted:
                accounts.set_active(session, user_id, active)
                st.session_state['_lead_notice'] = 'Đã cập nhật trạng thái.'
                st.rerun()
    except auth.AccessDenied as error:
        st.error(str(error))
    except (leads.LeadStorageError, psycopg.Error, OSError, ValueError):
        st.error('Không thể thực hiện thao tác lúc này. Vui lòng thử lại.')
