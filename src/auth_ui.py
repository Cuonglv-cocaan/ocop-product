"""Streamlit login and private pages; passwords and private results aren't cached."""
import psycopg
import streamlit as st
from data import accounts, auth, leads


def login():
    st.header('Đăng nhập')
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
            auth.logout(st.session_state)
            st.session_state['auth_session'] = session
            st.session_state['page'] = 'Trang chủ'
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


def requests_page(admin=False):
    st.header('Quản lý yêu cầu' if admin else 'Yêu cầu của tôi')
    session = st.session_state.get('auth_session')
    try:
        if admin:
            users = accounts.list_accounts(session)
        rows = leads.read_leads(session)
        if rows:
            st.dataframe(rows, hide_index=True)
            with st.form('edit_request'):
                lead_id = st.selectbox('Yêu cầu cần sửa', options=[row['id'] for row in rows])
                note = st.text_area('Nội dung cập nhật', key='private_note')
                submitted = st.form_submit_button('Lưu nội dung')
            if submitted:
                leads.update_note(session, lead_id, note)
                st.success('Đã lưu nội dung.')
        else:
            st.info('Chưa có yêu cầu.')
        if admin:
            st.subheader('Tài khoản')
            st.dataframe(users, hide_index=True)
            with st.form('account_status'):
                user_id = st.selectbox('Tài khoản', options=[u['id'] for u in users],
                                       format_func=lambda uid: next(u['username'] for u in users if u['id'] == uid))
                active = st.checkbox('Hoạt động', value=True)
                submitted = st.form_submit_button('Cập nhật trạng thái')
            if submitted:
                accounts.set_active(session, user_id, active)
                st.success('Đã cập nhật trạng thái.')
    except auth.AccessDenied as error:
        st.error(str(error))
    except (leads.LeadStorageError, psycopg.Error, OSError, ValueError):
        st.error('Không thể thực hiện thao tác lúc này. Vui lòng thử lại.')
