"""Conservative display-time enrichment for Bưu điện catalog records."""
import json
import re
import sys
from pathlib import Path

if not __package__:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from crawlers.provinces import PROVINCE_ALIASES, infer_province_hint, normalize_location_text


_PLACE_HINTS_ONLY = {'Phan Thiết', 'Lý Sơn', 'Phú Quốc'}
_PROVINCE_LOOKUP = {
    normalize_location_text(label): province
    for province, aliases in PROVINCE_ALIASES.items()
    for label in [province, *aliases]
    if label not in _PLACE_HINTS_ONLY
}


def canonical_province(value):
    """Accept province names and explicit variants, never arbitrary localities."""
    key = normalize_location_text(value or '')
    result = _PROVINCE_LOOKUP.get(key)
    if result:
        return result
    for prefix in ('tinh ', 'thanh pho ', 'tp '):
        if key.startswith(prefix):
            return _PROVINCE_LOOKUP.get(key[len(prefix):], '')
    return ''


def buudien_province(value, name, description):
    current = canonical_province(value)
    if current:
        return current
    title_hint = infer_province_hint(name or '')
    title_candidates = json.loads(title_hint['province_hint_candidates_json'])
    if title_candidates:
        return title_hint['province_hint'] or 'Chưa cập nhật'
    # Require an explicit origin field; do not infer from arbitrary addresses,
    # delivery destinations or mentions of ingredients elsewhere in descriptions.
    text = description if isinstance(description, str) else ''
    fields = re.findall(r'(?:xuất xứ|nơi sản xuất|sản xuất tại)\s*[:：-]?\s*([^.;\n]+)', text, re.I)
    candidates = set()
    for field in fields:
        result = infer_province_hint(field)
        candidates.update(json.loads(result['province_hint_candidates_json']))
    return next(iter(candidates)) if len(candidates) == 1 else 'Chưa cập nhật'


def buudien_stars(value, name, description):
    current = str(value or '').strip()
    if current:
        return current
    # Require the OCOP label close to the rating and reject ambiguous values.
    text = ' '.join(part for part in (name, description) if isinstance(part, str))
    pattern = re.compile(r'\bOCOP\s*[-:]?\s*([1-5])\s*sao\b|\b([1-5])\s*sao\s*[-:]?\s*OCOP\b', re.I)
    values = set()
    for match in pattern.finditer(text):
        prefix = text[max(0, match.start() - 25):match.start()]
        if re.search(r'(?:không|chưa|chẳng|khong|chua)\s+(?:đạt\s+|phải\s+)?$', prefix, re.I):
            continue
        values.add(match.group(1) or match.group(2))
    return next(iter(values)) if len(values) == 1 else ''
