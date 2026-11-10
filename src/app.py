"""OCOP Connect — Streamlit demo portal.

Run: streamlit run app.py
Products: DuckDB; leads: SQLite.
"""
from __future__ import annotations

import base64
import html
import importlib
import inspect
import math
import sys
from functools import lru_cache
from pathlib import Path
from urllib.parse import urlparse

import pandas as pd
import streamlit as st
import sqlite3

BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR.parent))
from data.database import DUCKDB_PATH, read_products, save_lead
from src import search as search_module

# Streamlit can retain an imported module while rerunning the edited app.
# Refresh the older discovery API once when upgrading a running session.
if "key_prefix" not in inspect.signature(search_module.product_discovery).parameters:
    importlib.reload(search_module)
product_discovery = search_module.product_discovery

st.set_page_config(page_title="OCOP Connect | Đặc sản Việt", page_icon="🌿", layout="wide", initial_sidebar_state="collapsed")

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap');
:root {--ocop-font: 'Inter', system-ui, -apple-system, 'Segoe UI', sans-serif;}
html, body, [data-testid="stApp"] {
    font-family: var(--ocop-font);
    -webkit-font-smoothing: antialiased;
}
[data-testid="stApp"] :is(h1, h2, h3, h4, h5, h6, p, label, input, textarea, button, select),
[data-testid="stMarkdownContainer"],
[data-testid="stChatMessage"],
[data-testid="stChatInput"] textarea,
[data-baseweb="select"],
[data-baseweb="popover"] [role="option"],
[role="dialog"] :is(h1, h2, h3, p, label, input, textarea, button) {
    font-family: var(--ocop-font) !important;
}
[data-testid="stHeader"] {display: none;}
[data-testid="stToolbar"] {display: none;}
.block-container {
    max-width: 1210px;
    padding-top: 2rem;
    padding-bottom: 3rem;
}
h1,h2,h3 {letter-spacing:-.6px; color:#123E2B;}
#MainMenu, footer {visibility:hidden;}
.logo-link, .logo-link:visited {display:inline-block;max-width:100%;text-decoration:none;color:#164c38;}
[data-testid="stMarkdownContainer"] a.logo-link,
[data-testid="stMarkdownContainer"] a.logo-link:link,
[data-testid="stMarkdownContainer"] a.logo-link:visited,
[data-testid="stMarkdownContainer"] a.logo-link:hover,
[data-testid="stMarkdownContainer"] a.logo-link:focus,
[data-testid="stMarkdownContainer"] a.logo-link:active,
[data-testid="stMarkdownContainer"] a.logo-link * {text-decoration:none !important;}
.logo-link:focus-visible {outline:2px solid #39975f;outline-offset:4px;border-radius:4px;}
[data-testid="stMarkdownContainer"] a.logo-link {color:#164c38 !important;display:inline-flex;flex-direction:column;max-width:100%;}
[data-testid="stMarkdownContainer"] .logo-link .site-brand {display:block;font-weight:800;font-size:clamp(18px,2.1vw,25px);color:#164c38 !important;margin:0;letter-spacing:-.7px;white-space:nowrap;line-height:1.4;}
[data-testid="stMarkdownContainer"] .logo-link .brand-accent {color:#39975f !important;}
[data-testid="stMarkdownContainer"] .logo-link .tagline {display:block;font-size:9px;letter-spacing:.7px;color:#809385 !important;font-weight:700;margin-top:2px;line-height:1.5;}
.st-key-site_header {padding:8px 0;}
.st-key-site_header [data-testid="stHorizontalBlock"] {align-items:center;gap:2rem;}
.st-key-site_header [data-testid="stColumn"] {min-width:0;}
.st-key-site_header [data-testid="stVerticalBlock"] {gap:0;justify-content:center;}
.st-key-site_header .logo-link {display:flex;flex-direction:column;justify-content:center;width:fit-content;}
.st-key-site_header [data-testid="stSegmentedControl"] {margin:0;}
.st-key-site_header [data-testid="stSegmentedControl"] [data-baseweb="button-group"] {width:100%;display:flex;align-items:stretch;}
.st-key-site_header [data-testid="stSegmentedControl"] button {flex:1 1 0;min-width:0;min-height:44px;padding:8px 12px;}
.st-key-site_header [data-testid="stSegmentedControl"] button p {white-space:nowrap;font-size:13px;line-height:1.4;}
@media(max-width:900px){
    .st-key-site_header [data-testid="stHorizontalBlock"] {flex-wrap:wrap;gap:1rem;}
    .st-key-site_header [data-testid="stColumn"] {width:100%!important;flex:1 1 100%!important;}
    .st-key-site_header .logo-link {margin-inline:auto;text-align:center;}
}
@media(max-width:480px){
    .st-key-site_header [data-testid="stSegmentedControl"] [data-baseweb="button-group"] {display:grid;grid-template-columns:repeat(2,minmax(0,1fr));}
    .st-key-site_header [data-testid="stSegmentedControl"] button {width:100%;}
}
.hero {background:#F7F9F1;border:1px solid #eaf0e5;border-radius:22px;padding:40px 42px;min-height:290px;margin:12px 0 24px}
.hero h1 {font-size:clamp(31px,4vw,50px);line-height:1.25;margin:13px 0;font-weight:800}
.hero h1 span {color:#2d8459}
.hero p {font-size:14px;line-height:1.85;color:#62796b}
.eyebrow {font-size:11px;font-weight:800;color:#2c8556;letter-spacing:2px}
.info-strip {background:#eef6e9;border-radius:12px;padding:17px 18px;color:#315e40;font-size:13px;line-height:1.7;margin-top:12px}
.section-kicker{font-size:11px;letter-spacing:2px;font-weight:800;color:#2b8857;text-transform:uppercase;margin-top:24px}
.section-desc {font-size:13px;color:#708176;margin-top:-7px}
.product-card {border:1px solid #e5ebe3;border-radius:14px;overflow:hidden;background:white;margin-bottom:4px;}
.product-photo {width:100%;height:172px;object-fit:contain;background:#fff;display:block;padding:12px;box-sizing:border-box;border-bottom:1px solid #f0f0f0;}
.product-card-body {padding:13px 14px 14px;display:flex;flex-direction:column;gap:8px}
.product-card .product-category {height:30px;line-height:15px;overflow:hidden;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical}
.product-card .product-name {height:80.6px;min-height:0;margin:0;overflow:hidden;display:-webkit-box;-webkit-line-clamp:4;-webkit-box-orient:vertical;overflow-wrap:anywhere}
.product-card .product-meta {height:38px;margin:0;display:flex;align-items:center;flex-wrap:wrap;column-gap:8px;row-gap:4px;line-height:17px;overflow:hidden}
.product-card .star-chip {display:inline-block;flex-shrink:0;white-space:nowrap}
.product-card .product-price {height:27px;line-height:27px;margin:0;white-space:nowrap}
.product-card .source-chip {height:24px;min-width:0;}
.product-category {font-size:10px;letter-spacing:.5px;color:#39835b;font-weight:800;text-transform:uppercase}
.product-name {font-size:13px;font-weight:800;min-height:41px;color:#000;line-height:1.55;margin-top:6px}
.product-meta{font-size:11px;color:#819186;margin-top:5px}
.product-price{font-size:18px;color:#c62828;font-weight:800;margin:10px 0}
.product-price-detail{font-size:26px;line-height:1.4}
.star-chip {background:#fff4d9;color:#9c6a09;font-weight:700;padding:4px 7px;border-radius:5px;font-size:10px}
.star-chip-0 {background:#f1f3f5;color:#667085}
.star-chip-4 {background:#e8f5ec;color:#216e39}
.star-chip-5 {background:#fdebec;color:#b42332}
.star-chip-detail {display:inline-block;font-size:14px;padding:6px 10px;margin:4px 0 8px}
.source-chip {display:flex;align-items:center;gap:6px;font-size:11px;font-weight:600;line-height:16px;color:#59665e}
.source-logo {width:28px;height:20px;object-fit:contain;flex-shrink:0;border-radius:3px;display:block}
.source-name {overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.stat {padding:15px 18px;border:1px solid #e7ede4;border-radius:14px;background:#fff}
.stat strong{display:block;font-size:25px;color:#164c38}
.stat small{font-size:11px;color:#789082}
.category-tile {background:#fff;border:1px solid #e3e9e5;border-radius:14px;text-align:center;padding:16px 10px;height:150px;box-sizing:border-box;display:flex;flex-direction:column;align-items:center;justify-content:center;gap:10px}
.category-icon {font-size:30px;line-height:1;width:52px;height:52px;border-radius:14px;background:#f0f6f1;display:flex;align-items:center;justify-content:center;flex-shrink:0}
.category-tile strong{display:flex;align-items:center;justify-content:center;color:#202720;font-size:12px;line-height:1.5;min-height:36px}
.region-tile{border-radius:12px;background:#f3f8f1;border:1px solid #e0ecdf;padding:16px 18px;margin:6px 0;min-height:100px;box-sizing:border-box}
.region-heading{display:flex;align-items:center;gap:8px}
.region-icon{font-size:18px;line-height:1;flex-shrink:0}
.region-name{margin:0!important;padding:0!important;font-size:17px!important;font-weight:700!important;line-height:1.4!important;color:#000!important}
.region-count{display:flex;align-items:baseline;gap:5px;margin-top:8px;padding-left:26px}
.region-count strong{font-size:20px;line-height:1.3;font-weight:700;color:#27583b;font-variant-numeric:tabular-nums}
.region-count span{font-size:13px;color:#59665e;font-weight:400}
.fineprint{font-size:11px;color:#77877c;line-height:1.7}
[data-testid="stButton"] button[kind="primary"] {background:#195b3e;border-color:#195b3e}
[data-testid="stButton"] button {border-radius:9px}
@media(max-width:720px){.hero{padding:22px}.product-photo{height:150px}.block-container{padding-left:1rem;padding-right:1rem}}
</style>
""", unsafe_allow_html=True)


def escape(value: object) -> str:
    return html.escape(str(value), quote=True)


def valid_http_url(value: object) -> str:
    """Accept only absolute HTTP(S) links from data files."""
    if pd.isna(value):
        return ""
    url = str(value).strip()
    parts = urlparse(url)
    return url if parts.scheme in ("http", "https") and parts.netloc else ""


def load_products() -> pd.DataFrame:
    df = read_products().fillna("")

    required = {
        "product_id",
        "product_name",
        "brand",
        "category_name",
        "province_name",
        "ocop_stars",
        "description",
        "source_url",
        "image_url",
        "price",
        "source",
    }

    missing = required - set(df.columns)

    if missing:
        raise ValueError(
            f"Thiếu các cột dữ liệu: {', '.join(sorted(missing))}"
        )

    df["price"] = pd.to_numeric(
        df["price"], errors="coerce"
    )
    df["price"] = df["price"].where(df["price"].map(lambda x: pd.notna(x) and math.isfinite(x) and x >= 0))

    stars = pd.to_numeric(df["ocop_stars"], errors="coerce")
    df["ocop_stars"] = stars.where(stars.isin([3, 4, 5]), 0).fillna(0).astype(int)

    df["image_url"] = df["image_url"].map(valid_http_url)
    df["source_url"] = df["source_url"].map(valid_http_url)

    df["province_name"] = (
        df["province_name"]
        .replace("", "Chưa cập nhật")
    )

    return df.drop_duplicates(
        subset=["source", "product_id"],
        keep="last"
    )


def money(value: float) -> str:
    if pd.isna(value) or not math.isfinite(value) or value < 0:
        return "Giá chưa cập nhật"
    return f"{value:,.0f}".replace(",", ".") + " ₫"


@st.dialog("Chi tiết sản phẩm", width="large")
def product_detail(p: dict):
    left, right = st.columns([1, 1.15], gap="medium")
    with left:
        if p["image_url"]:
            st.image(p["image_url"], use_container_width=True)
        else:
            st.info("Chưa có ảnh sản phẩm")
    with right:
        st.subheader(p["product_name"])
        st.write(f"🗺️ {p['province_name']}  ·  {p['category_name']}")
        st.markdown(
            f'<span class="star-chip star-chip-{int(p["ocop_stars"])} star-chip-detail">{star_label(p["ocop_stars"])}</span>',
            unsafe_allow_html=True,
        )
        st.markdown(
            f'<div class="product-price product-price-detail">Giá bán: {money(p["price"])}</div>',
            unsafe_allow_html=True,
        )
        st.write(p["description"] or "Chưa có mô tả.")
        st.caption(f"Nguồn: {p['source']} · Nhà bán: {p['brand'] or 'Chưa có thông tin'}")
        if p["source_url"]:
            st.link_button("↗ Xem gian hàng / sàn TMĐT", p["source_url"], type="primary", use_container_width=True)
        else:
            st.info("Sản phẩm demo chưa có liên kết mua hàng.")
        if st.button("Yêu cầu kết nối nhà cung cấp", key=f"ask_{p['source']}_{p['product_id']}", use_container_width=True):
            st.session_state["request_product"] = p["product_name"]
            st.session_state["page"] = "Kết nối cung cầu"
            st.rerun()


def star_label(value):
    return f"★ {int(value)} sao" if value in (3, 4, 5) else "Chưa cập nhật"


@lru_cache(maxsize=8)
def source_badge(source: str) -> str:
    key = source.strip().upper().replace(" ", "").replace("_", "").replace("-", "")
    brands = {
        "TIKI": ("tiki.png", "image/png", "Tiki"),
        "TIKTOK": ("tiktokshop.webp", "image/webp", "TikTok Shop"),
        "TIKTOKSHOP": ("tiktokshop.webp", "image/webp", "TikTok Shop"),
    }
    brand = brands.get(key)
    logo = ""
    label = source
    if brand:
        filename, mime_type, label = brand
        icon_path = BASE_DIR.parent / "data" / "icons" / filename
        if icon_path.is_file():
            encoded = base64.b64encode(icon_path.read_bytes()).decode("ascii")
            logo = f'<img class="source-logo" src="data:{mime_type};base64,{encoded}" alt="" aria-hidden="true">'
    return f'<div class="source-chip">{logo}<span class="source-name">{escape(label)}</span></div>'


def product_card(p: dict):
    image = (f'<img class="product-photo" src="{escape(p["image_url"])}" alt="Ảnh minh họa sản phẩm">'
             if p["image_url"] else '<div class="product-photo" style="display:grid;place-items:center">🌿</div>')
    st.markdown(f"""<div class="product-card">{image}<div class="product-card-body">
    <div class="product-category">{escape(p['category_name'])}</div>
    <div class="product-name">{escape(p['product_name'])}</div>
    <div class="product-meta">🗺️ {escape(p['province_name'])} &nbsp; <span class="star-chip star-chip-{int(p['ocop_stars'])}">{star_label(p['ocop_stars'])}</span></div>
    <div class="product-price">{money(p['price'])}</div>
    {source_badge(p['source'])}
    </div></div>""", unsafe_allow_html=True)
    if st.button("Xem chi tiết →", key=f"detail_{p['source']}_{p['product_id']}", use_container_width=True):
        product_detail(p)


def clear_product_filters():
    for key, value in {
        "category": "Tất cả", "stars_filter": "Tất cả",
        "province": "Tất cả", "source_filter": "Tất cả", "product_sort": "Mặc định",
    }.items():
        st.session_state[key] = value


def source_label(source: str) -> str:
    return {"TIKI": "Tiki", "TIKTOK": "TikTok Shop", "TIKTOKSHOP": "TikTok Shop"}.get(source, source)


def directory(df: pd.DataFrame):
    st.markdown('<div class="section-kicker">Gian hàng OCOP</div>', unsafe_allow_html=True)
    st.header("Khám phá sản phẩm vùng miền")
    st.markdown('<div class="section-desc">Tìm kiếm, so sánh và kết nối đến nguồn bán từ nhiều kênh thương mại điện tử.</div>', unsafe_allow_html=True)

    product_discovery(key_prefix="directory_discovery")
    st.subheader("Danh sách sản phẩm")
    st.caption("Lọc danh sách theo danh mục, hạng OCOP, tỉnh/thành và nguồn. Gợi ý AI ở trên hoạt động độc lập.")
    c2, c3, c4, c5 = st.columns([1.5, 1, 1.2, 1.1], gap="small")
    with c2:
        categories = ["Tất cả"] + sorted(df["category_name"].astype(str).unique().tolist())
        cat = st.selectbox("Danh mục", categories, key="category")
    with c3:
        star_options = {"3 sao": 3, "4 sao": 4, "5 sao": 5, "Chưa cập nhật": 0}
        stars = st.selectbox("Hạng OCOP", ["Tất cả", *star_options], key="stars_filter")
    with c4:
        provinces = ["Tất cả"] + sorted(df["province_name"].astype(str).unique().tolist())
        province = st.selectbox("Tỉnh/Thành", provinces, key="province")
    with c5:
        sources = ["Tất cả"] + sorted(df["source"].unique().tolist())
        source = st.selectbox("Nguồn", sources, format_func=source_label, key="source_filter")

    filtered = df.copy()
    if cat != "Tất cả":
        filtered = filtered[filtered["category_name"] == cat]
    if stars != "Tất cả":
        filtered = filtered[filtered["ocop_stars"] == star_options[stars]]
    if province != "Tất cả":
        filtered = filtered[filtered["province_name"] == province]
    if source != "Tất cả":
        filtered = filtered[filtered["source"] == source]

    a, b, reset = st.columns([2.5, 1.5, 1.1], gap="small", vertical_alignment="center")
    with a:
        st.caption(f"Hiển thị {len(filtered)} / {len(df)} sản phẩm")
    with b:
        sort = st.selectbox("Sắp xếp", ["Mặc định", "Giá tăng dần", "Giá giảm dần", "Sao cao nhất"],
                            label_visibility="collapsed", key="product_sort")
    with reset:
        active = any(value != "Tất cả" for value in (cat, stars, province, source)) or sort != "Mặc định"
        st.button("Xóa bộ lọc", key="clear_filters", on_click=clear_product_filters,
                  disabled=not active, use_container_width=True,
                  help="Đặt lại bộ lọc và sắp xếp của danh sách sản phẩm. Giữ nguyên hội thoại AI.")
    if sort == "Giá tăng dần":
        filtered = filtered.sort_values("price")
    elif sort == "Giá giảm dần":
        filtered = filtered.sort_values("price", ascending=False)
    elif sort == "Sao cao nhất":
        filtered = filtered.sort_values("ocop_stars", ascending=False)

    if filtered.empty:
        st.warning("Không tìm thấy sản phẩm phù hợp. Hãy thử bộ lọc khác.")
        return
    rows = filtered.to_dict("records")
    for start in range(0, len(rows), 4):
        cols = st.columns(4, gap="medium")
        for col, p in zip(cols, rows[start:start+4]):
            with col:
                product_card(p)


def home(df: pd.DataFrame):
    st.markdown('''<div class="hero"><div class="eyebrow">NỀN TẢNG KẾT NỐI CUNG — CẦU OCOP</div>
        <h1>Đặc sản Việt, <span>kết nối muôn nơi.</span></h1>
        <p>Khám phá đặc sản địa phương, tìm nhà cung cấp và điều hướng đến sản phẩm trên các kênh thương mại điện tử trong một cổng thông tin thống nhất.</p>
        <div class="info-strip">🌱 Đa dạng sản phẩm vùng miền &nbsp; • &nbsp; 🧭 Tìm kiếm dễ dàng &nbsp; • &nbsp; 🤝 Kết nối nhà cung cấp</div></div>''', unsafe_allow_html=True)
    product_discovery()
    if st.button("Khám phá sản phẩm →", type="primary", use_container_width=False):
        st.session_state["page"] = "Sản phẩm OCOP"
        st.rerun()
    banners = [
        "http://ocop.gov.vn/upload/2005578/20210618/banner_footer1_549f9.jpg",
        "http://ocop.gov.vn/upload/2005578/20210618/banner_footer2_01611.jpg",
        "http://ocop.gov.vn/upload/2005578/20210618/banner_footer3_42c65.jpg",
    ]
    for col, banner in zip(st.columns(3, gap="small"), banners):
        with col:
            st.image(banner, use_container_width=True)
    stats = [ (str(len(df))+"+", "Sản phẩm"), (str(df["province_name"].nunique()), "Tỉnh/thành"), (str(df["category_name"].nunique()), "Danh mục"), (str(df["source"].nunique()), "Nguồn dữ liệu") ]
    for col, (num, label) in zip(st.columns(4, gap="small"), stats):
        with col:
            st.markdown(f'<div class="stat"><strong>{num}</strong><small>{label}</small></div>', unsafe_allow_html=True)
    st.markdown('<div class="section-kicker">KHÁM PHÁ</div>', unsafe_allow_html=True)
    st.header("Danh mục nổi bật")
    icons = {
        "Gia vị và chế biến": "🧂",
        "Thực phẩm đóng hộp và khô": "🥫",
        "Đồ ăn vặt": "🍪",
        "Đồ uống": "🍵",
        "Sản phẩm thiên nhiên và khác": "🌿",
        "Bột và nguyên liệu làm bánh": "🌾",
        "Chăm sóc cơ thể": "🧴",
        "Sản phẩm hỗ trợ sức khỏe": "💚",
        "Hương thơm và đồ thờ cúng": "🪔",
        "Rượu, bia và nước lên men": "🍷",
        "Đồ dùng cho bé": "🍼",
        "Thực phẩm": "🍯",
        "Thủy hải sản": "🐟",
        "Trái cây": "🥭",
        "Thảo dược": "🌱",
        "Thủ công mỹ nghệ": "🧺",
    }
    categories = sorted(df["category_name"].unique())
    for start in range(0, len(categories), 4):
        for col, category in zip(st.columns(4, gap="medium"), categories[start:start + 4]):
            with col:
                st.markdown(
                    f'<div class="category-tile"><span class="category-icon">{icons.get(category, "📦")}</span><strong>{escape(category)}</strong></div>',
                    unsafe_allow_html=True,
                )
                if st.button("Khám phá →", key=f"cat_home_{category}", use_container_width=True):
                    st.session_state["category"] = category
                    st.session_state["page"] = "Sản phẩm OCOP"
                    st.rerun()
    st.markdown('<div class="section-kicker">SẢN PHẨM TIÊU BIỂU</div>', unsafe_allow_html=True)
    st.header("Đặc sản được giới thiệu")
    for col, p in zip(st.columns(4, gap="medium"), df.head(4).to_dict("records")):
        with col:
            product_card(p)
    


def regions(df: pd.DataFrame):
    st.markdown('<div class="section-kicker">BẢN ĐỒ ĐẶC SẢN</div>', unsafe_allow_html=True)
    st.header("Khám phá theo địa phương")
    grouped = df.groupby("province_name", as_index=False).agg(products=("product_id", "count"))
    for start in range(0, len(grouped), 3):
        for col, row in zip(st.columns(3), grouped.iloc[start:start+3].to_dict("records")):
            with col:
                st.markdown(
                    f'<div class="region-tile"><div class="region-heading"><span class="region-icon">🗺️</span>'
                    f'<h3 class="region-name">{escape(row["province_name"])}</h3></div>'
                    f'<div class="region-count"><strong>{int(row["products"]):,}</strong><span>sản phẩm</span></div></div>',
                    unsafe_allow_html=True,
                )
                if st.button("Khám phá sản phẩm →", key=f"province_{row['province_name']}", use_container_width=True):
                    st.session_state["province"] = row["province_name"]
                    st.session_state["page"] = "Sản phẩm OCOP"
                    st.rerun()


def connect():
    st.markdown('<div class="section-kicker">KẾT NỐI CUNG — CẦU</div>', unsafe_allow_html=True)
    st.header("Gửi nhu cầu mua sỉ hoặc đăng ký nhà cung cấp")
    st.info("Thông tin được lưu khi bạn nhấn Gửi yêu cầu để phục vụ việc liên hệ và kết nối cung cầu.")
    with st.form("lead_form", clear_on_submit=False):
        kind = st.radio("Bạn muốn", ["Nhận báo giá / tìm nguồn hàng", "Đăng ký nhà cung cấp"], horizontal=True)
        name = st.text_input("Họ tên / Doanh nghiệp *")
        email = st.text_input("Email *")
        phone = st.text_input("Số điện thoại *")
        note = st.text_area("Nhu cầu / Thông tin sản phẩm *", value=st.session_state.get("request_product", ""))
        submitted = st.form_submit_button("Gửi yêu cầu", type="primary")
        if submitted:
            if not (name.strip() and email.strip() and phone.strip() and note.strip()):
                st.error("Vui lòng điền đầy đủ thông tin bắt buộc.")
            elif "@" not in email or "." not in email.split("@")[-1]:
                st.error("Email chưa đúng định dạng.")
            else:
                try:
                    lead_id = save_lead(kind, name, email, phone, note)
                except (sqlite3.Error, OSError):
                    st.error("Không thể lưu yêu cầu lúc này. Thông tin vẫn được giữ trong biểu mẫu, vui lòng thử lại.")
                else:
                    st.success(f"Đã lưu yêu cầu của bạn. Mã yêu cầu: #{lead_id}.")
                    st.session_state["request_product"] = ""


def sync_navigation():
    selected = st.session_state.get("navigation_page")
    if selected is not None:
        st.session_state["page"] = selected


if "page" not in st.session_state:
    st.session_state["page"] = "Trang chủ"
try:
    products = load_products()
    if products.empty:
        st.warning("Chưa có sản phẩm trong database đang được cấu hình.")
        st.caption(f"Database: {DUCKDB_PATH.name}. Trên Community Cloud, đặt DUCKDB_PATH=data/catalog.duckdb và DUCKDB_READ_ONLY=true trong Secrets, rồi khởi động lại ứng dụng. Khi chạy ở máy cá nhân, nhập dữ liệu bằng: python data/database.py --migrate-csv data/products_ocop.csv")
        st.stop()
except Exception as exc:
    st.error(f"Không đọc được dữ liệu sản phẩm: {exc}")
    st.stop()

with st.container(key="site_header"):
    head_a, head_b = st.columns([1.15, 2.85], gap="large", vertical_alignment="center")
with head_a:
    st.markdown(
        '<a href="?page=home" class="logo-link" target="_self" aria-label="OCOP Connect - Trang chủ"><span class="site-brand">🌿 OCOP <span class="brand-accent">Connect</span></span><span class="tagline">ĐẶC SẢN VIỆT · KẾT NỐI MUÔN NƠI</span></a>',
        unsafe_allow_html=True,
    )
with head_b:
    pages = ["Trang chủ", "Sản phẩm OCOP", "Vùng miền", "Kết nối cung cầu"]
    st.session_state["navigation_page"] = st.session_state["page"]
    st.segmented_control("Điều hướng", options=pages, key="navigation_page", on_change=sync_navigation, label_visibility="collapsed", width="stretch")
st.divider()

current_page = st.session_state["page"]
if current_page == "Trang chủ":
    home(products)
elif current_page == "Sản phẩm OCOP":
    directory(products)
elif current_page == "Vùng miền":
    regions(products)
else:
    connect()

st.divider()
st.markdown('<div class="fineprint">© 2026 OCOP Connect </div>', unsafe_allow_html=True)
