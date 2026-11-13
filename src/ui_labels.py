"""Consistent field labels and status highlights."""
from html import escape
from decimal import Decimal, InvalidOperation
from datetime import date, datetime
from zoneinfo import ZoneInfo

import streamlit as st


def number_label(value):
    """Vietnamese numeric display without changing stored numeric values."""
    if value is None or value == '':
        return 'Chưa cập nhật'
    try:
        number = Decimal(str(value))
        if not number.is_finite():
            return str(value)
        text = format(number, ',f')
        if '.' in text:
            text = text.rstrip('0').rstrip('.')
        return text.replace(',', '_').replace('.', ',').replace('_', '.')
    except InvalidOperation:
        return str(value)


def money_label(value):
    return 'Chưa cập nhật' if value is None or value == '' else f'{number_label(value)} ₫'


def date_label(value):
    if value is None or value == '':
        return 'Chưa cập nhật'
    try:
        parsed = value if isinstance(value, date) else date.fromisoformat(str(value))
        return parsed.strftime('%d/%m/%Y')
    except (ValueError, TypeError):
        return 'Ngày không hợp lệ'


def time_label(value):
    if value is None or value == '':
        return 'Chưa cập nhật'
    try:
        parsed = value if isinstance(value, datetime) else datetime.fromisoformat(str(value))
        if parsed.tzinfo is None or parsed.utcoffset() is None:
            return parsed.strftime('%d/%m/%Y %H:%M') + ' (chưa xác định múi giờ)'
        return parsed.astimezone(ZoneInfo('Asia/Ho_Chi_Minh')).strftime('%d/%m/%Y %H:%M')
    except (ValueError, TypeError):
        return 'Thời gian không hợp lệ'


def role_label(role):
    return {'buyer': 'Người mua', 'seller': 'Nhà cung cấp', 'admin': 'Quản trị viên'}.get(role, 'Chưa xác định vai trò')


def event_label(event):
    """Translate known legacy system messages without rewriting user notes."""
    legacy = {
        'Buyer tạo phiếu nhu cầu.': 'Người mua tạo phiếu nhu cầu.',
        'Buyer cập nhật phiếu trước khi phân công.': 'Người mua cập nhật phiếu trước khi phân công.',
        'Buyer chọn phương án để tiếp tục trao đổi; chưa phải đơn hàng hay giao dịch thành công.':
            'Người mua chọn phương án để tiếp tục trao đổi; chưa phải đơn hàng hay giao dịch thành công.',
        'Buyer xác nhận đã kết nối để trao đổi, không xác nhận thanh toán hoặc giao dịch.':
            'Người mua xác nhận đã kết nối để trao đổi, không xác nhận thanh toán hoặc giao dịch.',
    }
    text = event.get('content') or 'Chưa có nội dung'
    return legacy.get(text, text) if event.get('event_type') in {'created', 'edited', 'selected', 'connected'} else text


def field_line(*fields):
    text = ' · '.join(f'<strong>{escape(str(label))}:</strong> {escape(str(value if value is not None and value != "" else "Chưa cập nhật"))}'
                      for label, value in fields)
    st.markdown(f'<p>{text}</p>', unsafe_allow_html=True)


def status_label(status, label):
    if status in {'approved', 'selected', 'connected'}:
        color, background, icon = '#166534', '#dcfce7', '✓'
    elif status in {'rejected', 'suspended', 'cancelled', 'closed_no_match'}:
        color, background, icon = '#991b1b', '#fee2e2', '!'
    else:
        color, background, icon = '#854d0e', '#fef9c3', '◷'
    st.markdown(
        '<p><strong>Trạng thái:</strong> '
        f'<span style="display:inline-block;padding:5px 12px;border-radius:8px;'
        f'background:{background};color:{color};font-weight:700;">'
        f'{icon} {escape(str(label))}</span></p>', unsafe_allow_html=True)
