"""OCOP Connect — Streamlit demo portal.

Run: streamlit run app.py
Data: ../data/products_ocop.csv; leads: DuckDB configured by DUCKDB_PATH.
"""
from __future__ import annotations

import html
import sys
from pathlib import Path
from urllib.parse import urlparse

import pandas as pd
import streamlit as st
import duckdb

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR.parent / "data"
DATA_FILE = DATA_DIR / "products_ocop.csv"
sys.path.insert(0, str(BASE_DIR.parent))
from data.database import save_lead

st.set_page_config(page_title="OCOP Connect | Đặc sản Việt", page_icon="🌿", layout="wide", initial_sidebar_state="collapsed")

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Be+Vietnam+Pro:wght@400;500;600;700;800&display=swap');
html, body, [class*="css"], [data-testid="stApp"] {font-family: 'Be Vietnam Pro', sans-serif;}
[data-testid="stHeader"] {display: none;}
[data-testid="stToolbar"] {display: none;}
.block-container {
    max-width: 1210px;
    padding-top: 3rem;
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
.site-brand {font-weight:800;font-size:clamp(18px,2.1vw,25px);color:#164c38;margin-top:4px;letter-spacing:-.7px;white-space:nowrap;line-height:1.4;}
.site-brand span {color:#39975f}
.tagline {font-size:10px;letter-spacing:1.1px;color:#809385;font-weight:700;margin-top:2px;line-height:1.5;}
.hero {background:#F7F9F1;border:1px solid #eaf0e5;border-radius:22px;padding:40px 42px;min-height:290px;margin:12px 0 24px}
.hero h1 {font-size:clamp(31px,4vw,50px);line-height:1.25;margin:13px 0;font-weight:800}
.hero h1 span {color:#2d8459}
.hero p {font-size:14px;line-height:1.85;color:#62796b}
.eyebrow {font-size:11px;font-weight:800;color:#2c8556;letter-spacing:2px}
.info-strip {background:#eef6e9;border-radius:12px;padding:17px 18px;color:#315e40;font-size:13px;line-height:1.7;margin-top:12px}
.section-kicker{font-size:11px;letter-spacing:2px;font-weight:800;color:#2b8857;text-transform:uppercase;margin-top:24px}
.section-desc {font-size:13px;color:#708176;margin-top:-7px}
.product-card {border:1px solid #e5ebe3;border-radius:14px;overflow:hidden;background:white;margin-bottom:4px;min-height:355px;}
.product-photo {width:100%;height:172px;object-fit:contain;background:#fff;display:block;padding:12px;box-sizing:border-box;border-bottom:1px solid #f0f0f0;}
.product-card-body {padding:13px 14px 5px;min-height:142px}
.product-category {font-size:10px;letter-spacing:.5px;color:#39835b;font-weight:800;text-transform:uppercase}
.product-name {font-size:13px;font-weight:800;min-height:41px;color:#000;line-height:1.55;margin-top:6px}
.product-meta{font-size:11px;color:#819186;margin-top:5px}
.product-price{font-size:18px;color:#c62828;font-weight:800;margin:10px 0}
.product-price-detail{font-size:26px;line-height:1.4}
.star-chip {background:#fff4d9;color:#9c6a09;font-weight:700;padding:4px 7px;border-radius:5px;font-size:10px}
.star-chip-4 {background:#e8f5ec;color:#216e39}
.star-chip-5 {background:#fdebec;color:#b42332}
.star-chip-detail {display:inline-block;font-size:14px;padding:6px 10px;margin:4px 0 8px}
.source-chip {font-size:10px;color:#7d8f80}
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


@st.cache_data(show_spinner=False)
def load_products(path: str, modified_at: float) -> pd.DataFrame:
    df = pd.read_csv(
        path,
        dtype={"product_id": "string"}
    ).fillna("")

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
    ).fillna(0)

    df["ocop_stars"] = pd.to_numeric(
        df["ocop_stars"], errors="coerce"
    ).fillna(0).astype(int)

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
            f'<span class="star-chip star-chip-{int(p["ocop_stars"])} star-chip-detail">★ Điểm OCOP: {int(p["ocop_stars"])} sao</span>',
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


def product_card(p: dict):
    image = (f'<img class="product-photo" src="{escape(p["image_url"])}" alt="Ảnh minh họa sản phẩm">'
             if p["image_url"] else '<div class="product-photo" style="display:grid;place-items:center">🌿</div>')
    st.markdown(f"""<div class="product-card">{image}<div class="product-card-body">
    <div class="product-category">{escape(p['category_name'])}</div>
    <div class="product-name">{escape(p['product_name'])}</div>
    <div class="product-meta">🗺️ {escape(p['province_name'])} &nbsp; <span class="star-chip star-chip-{int(p['ocop_stars'])}">★ {p['ocop_stars']} sao</span></div>
    <div class="product-price">{money(p['price'])}</div>
    <div class="source-chip">{escape(p['source'])}</div>
    </div></div>""", unsafe_allow_html=True)
    if st.button("Xem chi tiết →", key=f"detail_{p['source']}_{p['product_id']}", use_container_width=True):
        product_detail(p)


def directory(df: pd.DataFrame):
    st.markdown('<div class="section-kicker">Gian hàng OCOP</div>', unsafe_allow_html=True)
    st.header("Khám phá sản phẩm vùng miền")
    st.markdown('<div class="section-desc">Tìm kiếm, so sánh và kết nối đến nguồn bán từ nhiều kênh thương mại điện tử.</div>', unsafe_allow_html=True)

    left, c2, c3, c4 = st.columns([2.3, 1.3, 1.2, 1.3], gap="small")
    with left:
        q = st.text_input("Tìm kiếm", placeholder="Tên sản phẩm, tỉnh, danh mục...", key="query")
    with c2:
        categories = ["Tất cả"] + sorted(df["category_name"].astype(str).unique().tolist())
        cat = st.selectbox("Danh mục", categories, key="category")
    with c3:
        stars = st.selectbox("Hạng OCOP", ["Tất cả", "3 sao", "4 sao", "5 sao"], key="stars_filter")
        if stars != "Tất cả":
            st.markdown(
                f'<span class="star-chip star-chip-{int(stars.split()[0])}">★ {stars}</span>',
                unsafe_allow_html=True,
            )
    with c4:
        provinces = ["Tất cả"] + sorted(df["province_name"].astype(str).unique().tolist())
        province = st.selectbox("Tỉnh/Thành", provinces, key="province")

    filtered = df.copy()
    if q.strip():
        search_columns = filtered[["product_name", "category_name", "province_name", "description"]].astype(str).agg(" ".join, axis=1)
        filtered = filtered[search_columns.str.contains(q.strip(), case=False, regex=False, na=False)]
    if cat != "Tất cả":
        filtered = filtered[filtered["category_name"] == cat]
    if stars != "Tất cả":
        filtered = filtered[filtered["ocop_stars"] == int(stars.split()[0])]
    if province != "Tất cả":
        filtered = filtered[filtered["province_name"] == province]

    a, b = st.columns([3, 1.3])
    with a:
        st.caption(f"Hiển thị {len(filtered)} / {len(df)} sản phẩm")
    with b:
        sort = st.selectbox("Sắp xếp", ["Mặc định", "Giá tăng dần", "Giá giảm dần", "Sao cao nhất"], label_visibility="collapsed")
    if sort == "Giá tăng dần":
        filtered = filtered.sort_values("price")
    elif sort == "Giá giảm dần":
        filtered = filtered.sort_values("price", ascending=False)
    elif sort == "Sao cao nhất":
        filtered = filtered.sort_values("ocop_stars", ascending=False)

    if filtered.empty:
        st.warning("Không tìm thấy sản phẩm phù hợp. Hãy thử từ khóa hoặc bộ lọc khác.")
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
        "Gia Vị và Chế Biến": "🧂",
        "Thực phẩm Đóng hộp và Khô": "🥫",
        "Đồ Ăn Vặt": "🍪",
        "Đồ uống": "🍵",
        "Sản phẩm thiên nhiên & Khác": "🌿",
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
                except (duckdb.Error, OSError):
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
if not DATA_FILE.exists():
    st.error(f"Không tìm thấy file dữ liệu: {DATA_FILE}")
    st.stop()
try:
    products = load_products(str(DATA_FILE), DATA_FILE.stat().st_mtime)
except Exception as exc:
    st.error(f"Không đọc được dữ liệu sản phẩm: {exc}")
    st.stop()

head_a, head_b = st.columns([1, 3.6], vertical_alignment="center")
with head_a:
    st.markdown(
        '<a href="?page=home" class="logo-link" target="_self"><div class="site-brand">🌿 OCOP <span>Connect</span></div><div class="tagline">ĐẶC SẢN VIỆT · KẾT NỐI MUÔN NƠI</div></a>',
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
