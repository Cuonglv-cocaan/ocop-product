"""Shared lexical province hints for crawler product titles."""
import json
import re
import unicodedata

# Lexical place labels, including historical province names found in titles.
# This is not an administrative boundary map. Do not infer production origin
# or automatically remap historical names to current provinces.
PROVINCE_NAMES = (
    'An Giang', 'Bà Rịa - Vũng Tàu', 'Bắc Giang', 'Bắc Kạn',
    'Bạc Liêu', 'Bắc Ninh', 'Bến Tre', 'Bình Định', 'Bình Dương',
    'Bình Phước', 'Bình Thuận', 'Cà Mau', 'Cần Thơ', 'Cao Bằng',
    'Đà Nẵng', 'Đắk Lắk', 'Đắk Nông', 'Điện Biên', 'Đồng Nai',
    'Đồng Tháp', 'Gia Lai', 'Hà Giang', 'Hà Nam', 'Hà Nội',
    'Hà Tĩnh', 'Hải Dương', 'Hải Phòng', 'Hậu Giang', 'Hòa Bình',
    'Hưng Yên', 'Khánh Hòa', 'Kiên Giang', 'Kon Tum', 'Lai Châu',
    'Lâm Đồng', 'Lạng Sơn', 'Lào Cai', 'Long An', 'Nam Định',
    'Nghệ An', 'Ninh Bình', 'Ninh Thuận', 'Phú Thọ', 'Phú Yên',
    'Quảng Bình', 'Quảng Nam', 'Quảng Ngãi', 'Quảng Ninh',
    'Quảng Trị', 'Sóc Trăng', 'Sơn La', 'Tây Ninh', 'Thái Bình',
    'Thái Nguyên', 'Thanh Hóa', 'Huế', 'Tiền Giang',
    'TP. Hồ Chí Minh', 'Trà Vinh', 'Tuyên Quang', 'Vĩnh Long',
    'Vĩnh Phúc', 'Yên Bái',
)
PROVINCE_ALIASES = {name: [] for name in PROVINCE_NAMES}
PROVINCE_ALIASES.update({
    'Huế': ['Thừa Thiên Huế'],
    'TP. Hồ Chí Minh': ['Hồ Chí Minh', 'TPHCM', 'TP HCM', 'Sài Gòn'],
    'Đắk Lắk': ['Đăk Lăk', 'Dak Lak'],
    'Đắk Nông': ['Đăk Nông'],
    'Bà Rịa - Vũng Tàu': ['Bà Rịa Vũng Tàu'],
    'Bình Thuận':['Phan Thiết'],
    'Quảng Ngãi': ['Lý Sơn'],
    'An Giang': ['Phú Quốc']
})


def normalize_location_text(text):
    text = unicodedata.normalize('NFD', str(text or ''))
    text = ''.join(c for c in text if unicodedata.category(c) != 'Mn')
    text = text.lower().replace('đ', 'd')
    return re.sub(r'[^a-z0-9]+', ' ', text).strip()


def infer_province_hint(title, province_aliases=None):
    """Title keyword hints only; never confirm manufacturing location."""
    if province_aliases is None:
        province_aliases = PROVINCE_ALIASES
    normalized_title = ' ' + normalize_location_text(title) + ' '
    matches = set()
    for province, aliases in province_aliases.items():
        for alias in [province, *aliases]:
            label = normalize_location_text(alias)
            if label and (' ' + label + ' ') in normalized_title:
                matches.add(province)
                break
    candidates = sorted(matches)
    return {
        'province_hint': candidates[0] if len(candidates) == 1 else '',
        'province_hint_source': 'title' if candidates else '',
        'province_hint_candidates_json': json.dumps(candidates, ensure_ascii=False),
        'production_province': '',
    }


