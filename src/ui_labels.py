"""Consistent field labels and status highlights."""
from html import escape
from decimal import Decimal, InvalidOperation
from datetime import date, datetime
from zoneinfo import ZoneInfo
import re

import streamlit as st


UNIT_OPTIONS = ('kg', 'g', 'lít', 'ml', 'cái', 'chiếc', 'hộp', 'gói', 'túi',
                'chai', 'lọ', 'hũ', 'lon', 'bộ', 'giỏ', 'thùng', 'tấn')

STATES = {'open': 'Mới tạo', 'assigned': 'Đã phân nhà cung cấp', 'quoted': 'Đã có báo giá',
          'selected': 'Đã chọn để trao đổi', 'connected': 'Người mua đã xác nhận kết nối',
          'cancelled': 'Đã hủy', 'closed_no_match': 'Đóng: chưa có phương án'}


def select_existing(label, options, value='', **kwargs):
    """Keep unknown historical values selectable without changing their text."""
    value = value or ''
    options = list(dict.fromkeys(['', *options, *([value] if value else [])]))
    return st.selectbox(label, options=options, index=options.index(value),
                        format_func=lambda item: item or 'Chưa chọn', **kwargs)


NUMBER_HELP = ('Nhập theo định dạng Việt Nam: 1.000.000 là một triệu; 1.000,5 là một nghìn phẩy năm. '
               'Cũng chấp nhận 1000000 và 1000.5. Dấu chấm nhóm 3 chữ số được hiểu là hàng nghìn '
               '(1.000 = 1000); nên dùng dấu phẩy cho phần thập phân. Không thêm ký hiệu tiền hoặc đơn vị.')


def parse_vn_number(text: str) -> Decimal:
    """Parse Vietnamese grouping first; otherwise accept ungrouped decimal dots.

    Ambiguous '1.000' means 1000; use '1,000' for decimal 1.
    Decimal values from the database must be formatted with number_label for editing.
    Business limits (positive, scale, maximum) remain in the data layer.
    """
    if text is None or isinstance(text, str) and not text.strip():
        raise ValueError('Vui lòng nhập một số.')
    if not isinstance(text, str):
        raise ValueError('Số nhập phải là văn bản, ví dụ 1.000,5 hoặc 1000.5.')
    text = text.strip()
    grouped = r'[1-9][0-9]{0,2}(?:\.[0-9]{3})+'
    if ',' in text:
        valid = re.fullmatch(rf'[+-]?(?:[0-9]+|{grouped}),[0-9]+', text)
        normalized = text.replace('.', '').replace(',', '.')
    elif re.fullmatch(rf'[+-]?{grouped}', text):
        valid = True
        normalized = text.replace('.', '')
    else:
        valid = re.fullmatch(r'[+-]?[0-9]+(?:\.[0-9]+)?', text)
        normalized = text
    if not valid:
        raise ValueError('Số không đúng định dạng. Ví dụ hợp lệ: 1.000.000; 1.000,5; 1000000; 1000.5. '
                         'Không nhập ký hiệu tiền, đơn vị hoặc dấu phân cách hàng nghìn sai vị trí.')
    try:
        return Decimal(normalized)
    except InvalidOperation:
        raise ValueError('Không thể đọc số đã nhập. Hãy nhập lại theo mẫu 1.000,5.') from None


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
    if event.get('event_type') == 'unassigned':
        import json
        try:
            payload = json.loads(event.get('content') or '')
            if isinstance(payload, dict) and isinstance(payload.get('message'), str):
                return payload['message']
        except (ValueError, TypeError):
            pass
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


def render_stepper(status):
    """Show the current workflow position, not an inferred event history."""
    steps = (('open', STATES['open']), ('assigned', 'Đã phân NCC'),
             ('quoted', 'Có báo giá'), ('selected', 'Đã chọn'), ('connected', 'Đã kết nối'))
    keys = [key for key, _ in steps]
    if status not in keys:
        status_label(status, STATES.get(status, 'Chưa xác định trạng thái'))
        return
    current = keys.index(status)
    items = []
    for index, (key, label) in enumerate(steps):
        state = 'done' if index < current else 'current' if index == current else 'pending'
        marker = '✓' if index < current else str(index + 1)
        aria = ' aria-current="step"' if index == current else ''
        items.append(f'<li class="ocop-step {state}"{aria} title="{escape(STATES[key])}">'
                     f'<span class="ocop-step-marker" aria-hidden="true">{marker}</span>'
                     f'<span>{escape(label)}</span></li>')
    st.markdown('''<ol class="ocop-stepper" aria-label="Tiến trình xử lý nhu cầu">'''
                + ''.join(items) + '</ol>', unsafe_allow_html=True)
