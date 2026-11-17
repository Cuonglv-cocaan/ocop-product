"""Shared product presentation for the catalog and AI recommendations."""
import base64
import html
import math
from functools import lru_cache
from pathlib import Path
from urllib.parse import urlparse


def safe_url(value):
    url = str(value or '').strip()
    parts = urlparse(url)
    return url if parts.scheme in ('http', 'https') and parts.netloc else ''


def money(value):
    try:
        amount = float(value)
    except (TypeError, ValueError):
        return 'Giá chưa cập nhật'
    if not math.isfinite(amount) or amount < 0:
        return 'Giá chưa cập nhật'
    return f'{amount:,.0f}'.replace(',', '.') + ' ₫'


def star_label(value):
    return f'★ {int(value)} sao' if value in (3, 4, 5) else 'Chưa cập nhật'


@lru_cache(maxsize=8)
def source_badge(source):
    key = source.strip().upper().replace(' ', '').replace('_', '').replace('-', '')
    brands = {'TIKI': ('tiki.png', 'image/png', 'Tiki'),
              'TIKTOK': ('tiktokshop.webp', 'image/webp', 'TikTok Shop'),
              'TIKTOKSHOP': ('tiktokshop.webp', 'image/webp', 'TikTok Shop')}
    logo, label = '', source
    if key in brands:
        filename, mime, label = brands[key]
        path = Path(__file__).resolve().parents[1] / 'data' / 'icons' / filename
        if path.is_file():
            encoded = base64.b64encode(path.read_bytes()).decode('ascii')
            logo = f'<img class="source-logo" src="data:{mime};base64,{encoded}" alt="" aria-hidden="true">'
    return f'<div class="source-chip">{logo}<span class="source-name">{html.escape(label)}</span></div>'


def product_card_html(product):
    esc = lambda value: html.escape(str(value or ''), quote=True)
    image_url = safe_url(product.get('image_url'))
    image = (f'<img class="product-photo" src="{esc(image_url)}" alt="Ảnh minh họa sản phẩm" loading="lazy">'
             if image_url else '<div class="product-photo product-photo-placeholder">🌿</div>')
    stars = product.get('ocop_stars')
    stars = int(stars) if stars in (3, 4, 5) else 0
    name = esc(product.get('product_name'))
    return (
        f'<div class="product-card">{image}<div class="product-card-body">'
        f'<div class="product-category">{esc(product.get("category_name"))}</div>'
        f'<div class="product-name" title="{name}">{name}</div>'
        f'<div class="product-meta">🗺️ {esc(product.get("province_name") or "Chưa cập nhật")} '
        f'<span class="star-chip star-chip-{stars}">{star_label(stars)}</span></div>'
        f'<div class="product-price">{money(product.get("price"))}</div>'
        f'{source_badge(str(product.get("source") or ""))}</div></div>'
    )
