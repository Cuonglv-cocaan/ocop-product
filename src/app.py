"""OCOP Connect — Streamlit demo portal.

Run: streamlit run app.py
Products: DuckDB; leads: configurable business storage.
"""
from __future__ import annotations

import html
import math
import sys
from pathlib import Path
from urllib.parse import urlparse

import pandas as pd
import streamlit as st

BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR.parent))
from data.database import DUCKDB_PATH, read_products
from data.leads import save_lead, LeadStorageError
from data import auth
from src.ui_labels import role_label
from src.product_cards import money, star_label, source_badge, product_card_html
from src.catalog_cache import catalog_version
from src.styles import APP_STYLES
from src import auth_ui
from src import supplier_ui
from src import purchase_ui
from src import dashboard_ui
from src.search import product_discovery
from src import search as search_module

st.set_page_config(page_title="OCOP Connect | Đặc sản Việt", page_icon="🌿", layout="wide", initial_sidebar_state="collapsed")

st.markdown(APP_STYLES, unsafe_allow_html=True)



def escape(value: object) -> str:
    return html.escape(str(value), quote=True)


def valid_http_url(value: object) -> str:
    """Accept only absolute HTTP(S) links from data files."""
    if pd.isna(value):
        return ""
    url = str(value).strip()
    parts = urlparse(url)
    return url if parts.scheme in ("http", "https") and parts.netloc else ""


@st.cache_data(ttl=600, max_entries=8, show_spinner=False)
def load_products(catalog_signature=None) -> pd.DataFrame:
    """catalog_signature is a cache key supplied from catalog_version()."""
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


@st.dialog("Chi tiết sản phẩm", width="large")
def product_detail(p: dict):
    left, right = st.columns([1, 1.15], gap="medium")
    with left:
        if p["image_url"]:
            st.image(p["image_url"], width="stretch")
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
            st.link_button("↗ Xem gian hàng / sàn TMĐT", p["source_url"], type="primary", width="stretch")
        else:
            st.info("Sản phẩm demo chưa có liên kết mua hàng.")
        if (actor is None or actor['role'] == 'buyer') and st.button("Yêu cầu kết nối nhà cung cấp", key=f"ask_{p['source']}_{p['product_id']}", width="stretch"):
            st.session_state['purchase_reference'] = {'source': p['source'], 'product_id': p['product_id'],
                                                       'title': p['product_name'], 'category': p['category_name']}
            st.session_state["page"] = "Nhu cầu"
            st.rerun()


def product_card(p: dict):
    st.markdown(product_card_html(p), unsafe_allow_html=True)
    if st.button("Xem chi tiết →", key=f"detail_{p['source']}_{p['product_id']}", width="stretch"):
        product_detail(p)


def clear_product_filters():
    for key, value in {
        "category": "Tất cả", "stars_filter": "Tất cả",
        "province": "Tất cả", "source_filter": "Tất cả", "product_sort": "Mặc định",
    }.items():
        st.session_state[key] = value
    reset_catalog_page()


def reset_catalog_page():
    st.session_state['catalog_page'] = 1


def source_label(source: str) -> str:
    return {"TIKI": "Tiki", "TIKTOK": "TikTok Shop", "TIKTOKSHOP": "TikTok Shop", "BUUDIEN": "Bưu điện"}.get(source, source)


def directory(df: pd.DataFrame):
    st.markdown('<div class="section-kicker">Gian hàng OCOP</div>', unsafe_allow_html=True)
    st.header("Khám phá sản phẩm vùng miền")
    st.markdown('<div class="section-desc">Tìm kiếm, so sánh và kết nối đến nguồn bán từ nhiều kênh thương mại điện tử.</div>', unsafe_allow_html=True)

    product_discovery(key_prefix="directory_discovery")
    directory_listing()


@st.fragment
def directory_listing():
    # Re-check the file on fragment runs as well as full application runs.
    df = load_products(catalog_version())
    st.subheader("Danh sách sản phẩm")
    st.caption("Lọc danh sách theo danh mục, hạng OCOP, tỉnh/thành và nguồn. Gợi ý AI ở trên hoạt động độc lập.")
    c2, c3, c4, c5 = st.columns([1.5, 1, 1.2, 1.1], gap="small")
    with c2:
        categories = ["Tất cả"] + sorted(df["category_name"].astype(str).unique().tolist())
        cat = st.selectbox("Danh mục", categories, key="category", on_change=reset_catalog_page)
    with c3:
        star_options = {"3 sao": 3, "4 sao": 4, "5 sao": 5, "Chưa cập nhật": 0}
        stars = st.selectbox("Hạng OCOP", ["Tất cả", *star_options], key="stars_filter", on_change=reset_catalog_page)
    with c4:
        provinces = ["Tất cả"] + sorted(df["province_name"].astype(str).unique().tolist())
        province = st.selectbox("Tỉnh/Thành", provinces, key="province", on_change=reset_catalog_page)
    with c5:
        sources = ["Tất cả"] + sorted(df["source"].unique().tolist())
        source = st.selectbox("Nguồn", sources, format_func=source_label, key="source_filter", on_change=reset_catalog_page)

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
                            label_visibility="collapsed", key="product_sort", on_change=reset_catalog_page)
    with reset:
        active = any(value != "Tất cả" for value in (cat, stars, province, source)) or sort != "Mặc định"
        st.button("Xóa bộ lọc", key="clear_filters", on_click=clear_product_filters,
                  disabled=not active, width="stretch",
                  help="Đặt lại bộ lọc và sắp xếp của danh sách sản phẩm. Giữ nguyên hội thoại AI.")
    filter_signature = (cat, stars, province, source, sort)
    if st.session_state.get('_catalog_filter_signature') != filter_signature:
        reset_catalog_page()
        st.session_state['_catalog_filter_signature'] = filter_signature
    if sort == "Giá tăng dần":
        filtered = filtered.sort_values("price", kind='stable')
    elif sort == "Giá giảm dần":
        filtered = filtered.sort_values("price", ascending=False, kind='stable')
    elif sort == "Sao cao nhất":
        filtered = filtered.sort_values("ocop_stars", ascending=False, kind='stable')

    if filtered.empty:
        reset_catalog_page()
        st.warning("Không tìm thấy sản phẩm phù hợp. Hãy thử bộ lọc khác.")
        return
    page_size = 12
    page_count = math.ceil(len(filtered) / page_size)
    page_number = max(1, min(st.session_state.get('catalog_page', 1), page_count))
    st.session_state['catalog_page'] = page_number
    first = (page_number - 1) * page_size
    st.caption(f'Trang {page_number} / {page_count} · Sản phẩm {first + 1}–{min(first + page_size, len(filtered))} trong {len(filtered)} kết quả')
    rows = filtered.iloc[first:first + page_size].to_dict("records")
    for start in range(0, len(rows), 4):
        cols = st.columns(4, gap="medium")
        for col, p in zip(cols, rows[start:start+4]):
            with col:
                product_card(p)
    if page_count > 1:
        previous, selector, following = st.columns([1, 1, 1], vertical_alignment='bottom')
        with previous:
            st.button('← Trang trước', key='catalog_previous', disabled=page_number == 1,
                      on_click=st.session_state.__setitem__, args=('catalog_page', page_number - 1),
                      width="stretch")
        with selector:
            st.number_input('Trang', min_value=1, max_value=page_count, step=1, key='catalog_page')
        with following:
            st.button('Trang sau →', key='catalog_next', disabled=page_number == page_count,
                      on_click=st.session_state.__setitem__, args=('catalog_page', page_number + 1),
                      width="stretch")


def home(df: pd.DataFrame):
    st.markdown('''<div class="hero"><div class="eyebrow">NỀN TẢNG KẾT NỐI CUNG — CẦU OCOP</div>
        <h1>Đặc sản Việt, <span>kết nối muôn nơi.</span></h1>
        <p>Khám phá đặc sản địa phương, tìm nhà cung cấp và điều hướng đến sản phẩm trên các kênh thương mại điện tử trong một cổng thông tin thống nhất.</p>
        <div class="info-strip">🌱 Đa dạng sản phẩm vùng miền &nbsp; • &nbsp; 🧭 Tìm kiếm dễ dàng &nbsp; • &nbsp; 🤝 Kết nối nhà cung cấp</div></div>''', unsafe_allow_html=True)
    product_discovery()
    if st.button("Khám phá sản phẩm →", type="primary", width="content"):
        st.session_state["page"] = "Sản phẩm OCOP"
        st.rerun()
    banners = [
        "http://ocop.gov.vn/upload/2005578/20210618/banner_footer1_549f9.jpg",
        "http://ocop.gov.vn/upload/2005578/20210618/banner_footer2_01611.jpg",
        "http://ocop.gov.vn/upload/2005578/20210618/banner_footer3_42c65.jpg",
    ]
    for col, banner in zip(st.columns(3, gap="small"), banners):
        with col:
            st.image(banner, width="stretch")
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
                if st.button("Khám phá →", key=f"cat_home_{category}", width="stretch"):
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
    name_filter = st.text_input("Lọc tên tỉnh/thành", key="region_name_filter").strip()
    grouped = df.groupby("province_name", as_index=False).agg(products=("product_id", "count"))
    grouped = (
        grouped.assign(is_unknown=grouped["province_name"].eq("Chưa cập nhật"))
        .sort_values(["is_unknown", "products", "province_name"], ascending=[True, False, True])
        .drop(columns="is_unknown")
    )
    if name_filter:
        grouped = grouped[grouped["province_name"].str.contains(name_filter, case=False, regex=False, na=False)]
    if grouped.empty:
        st.info("Không tìm thấy tỉnh/thành phù hợp.")
    for start in range(0, len(grouped), 3):
        for col, row in zip(st.columns(3), grouped.iloc[start:start+3].to_dict("records")):
            with col:
                st.markdown(
                    f'<div class="region-tile"><div class="region-heading"><span class="region-icon">🗺️</span>'
                    f'<h3 class="region-name">{escape(row["province_name"])}</h3></div>'
                    f'<div class="region-count"><strong>{int(row["products"]):,}</strong><span>sản phẩm</span></div></div>',
                    unsafe_allow_html=True,
                )
                if st.button("Khám phá sản phẩm →", key=f"province_{row['province_name']}", width="stretch"):
                    st.session_state["province"] = row["province_name"]
                    st.session_state["page"] = "Sản phẩm OCOP"
                    st.rerun()


def guest_purchase():
    from data.leads import save_guest_lead
    st.title('Nhu cầu mua hàng')
    st.caption('Gửi nhu cầu hoặc nhờ tìm sản phẩm, không cần đăng nhập.')
    notice = st.session_state.pop('_guest_notice', None)
    if notice:
        st.success(notice)
    st.info('Để lại email hoặc số điện thoại để quản trị viên liên hệ hỗ trợ. Thông tin không hiển thị công khai.')
    with st.form(f'guest_purchase_form_{st.session_state.get("guest_form_generation", 0)}'):
        kind = st.selectbox('Bạn cần hỗ trợ gì?', ['Nhu cầu mua hàng', 'Nhờ tìm sản phẩm'])
        reference = st.session_state.get('purchase_reference', {})
        default_note = st.session_state.get('request_product') or (
            f"Tôi muốn tìm mua: {reference.get('title', '')}" if reference else '')
        note = st.text_area('Nội dung *', value=default_note, max_chars=5000,
                            placeholder='Ví dụ: Tìm 20 hộp trà OCOP làm quà, ngân sách 200.000đ/hộp, giao tại Hà Nội tuần tới.')
        name = st.text_input('Tên liên hệ *', max_chars=200)
        email = st.text_input('Email', max_chars=254)
        phone = st.text_input('Số điện thoại', max_chars=30)
        st.caption('Nhập ít nhất email hoặc số điện thoại.')
        submitted = st.form_submit_button('Gửi yêu cầu', type='primary')
    if submitted:
        try:
            lead_id = save_guest_lead(kind, name, email, phone, note)
        except ValueError as error:
            st.error(str(error))
        except LeadStorageError:
            st.error('Chưa gửi được yêu cầu. Vui lòng thử lại, thông tin vẫn được giữ trong biểu mẫu.')
        else:
            st.session_state['_guest_notice'] = f'Đã gửi yêu cầu #{lead_id}. Quản trị viên sẽ liên hệ qua thông tin bạn cung cấp.'
            st.session_state.pop('purchase_reference', None)
            st.session_state.pop('request_product', None)
            st.session_state['guest_form_generation'] = st.session_state.get('guest_form_generation', 0) + 1
            st.rerun()


def connect():
    actor = auth_ui.identity()
    st.title('Yêu cầu của tôi' if actor and actor['role'] == 'buyer' else 'Kết nối cung cầu')
    if actor is None:
        st.info('Vui lòng đăng nhập để gửi yêu cầu.')
        auth_ui.login()
        return
    if actor['role'] not in ('buyer', 'seller'):
        st.info('Admin quản lý yêu cầu tại trang Quản trị.')
        return
    if actor['role'] == 'seller':
        st.info('Đăng ký và quản lý đơn vị cung cấp tại trang Nhà cung cấp. Quyền cung ứng được kiểm tra theo từng đơn vị đã duyệt.')
        if st.button('Mở hồ sơ nhà cung cấp', key='open_supplier_profile'):
            st.session_state['page'] = 'Nhà cung cấp'
            st.rerun()
        return
    st.caption('Gửi yêu cầu mua sỉ hoặc tìm nguồn hàng, xem lại và cập nhật nội dung ngay trên trang này.')
    st.subheader('Gửi yêu cầu mới')
    st.info("Thông tin được lưu khi bạn nhấn Gửi yêu cầu để phục vụ việc liên hệ và kết nối cung cầu.")
    with st.form("lead_form", clear_on_submit=False):
        from data.leads import KINDS
        kind = KINDS[actor['role']]
        st.caption(kind)
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
                    lead_id = save_lead(kind, name, email, phone, note,
                                        session=st.session_state.get('auth_session'))
                except auth.AccessDenied as error:
                    st.error(str(error))
                except LeadStorageError:
                    st.error("Không thể lưu yêu cầu lúc này. Thông tin vẫn được giữ trong biểu mẫu, vui lòng thử lại.")
                else:
                    st.success(f"Đã lưu yêu cầu của bạn. Mã yêu cầu: #{lead_id}.")
                    st.session_state["request_product"] = ""
    st.divider()
    auth_ui.requests_page(embedded=True)


PAGE_SLUGS = {
    'Trang chủ': 'home', 'Sản phẩm OCOP': 'products', 'Vùng miền': 'regions',
    'Nhu cầu mua hàng': 'demand', 'Đăng nhập': 'login',
    'Yêu cầu báo giá': 'quotes', 'Quản lý cung ứng': 'supply',
    'Đăng ký cung cấp': 'supplier-registration', 'Quản trị': 'admin',
    'Hiệu quả kết nối': 'dashboard',
    'Kết nối cung cầu': 'connection', 'Nhu cầu': 'requests',
}
SLUG_PAGES = {slug: page for page, slug in PAGE_SLUGS.items()}


def sync_page_url():
    slug = PAGE_SLUGS.get(st.session_state['page'], 'home')
    if st.query_params.get('page') != slug:
        st.query_params['page'] = slug
    st.session_state['_last_page_slug'] = slug


def navigate(page):
    st.session_state['page'] = page
    sync_page_url()


def sync_navigation():
    selected = st.session_state.get("navigation_page")
    if selected is not None:
        navigate(selected)


actor = auth_ui.identity()
url_slug = st.query_params.get('page')
if 'page' not in st.session_state:
    st.session_state['page'] = SLUG_PAGES.get(url_slug, 'Trang chủ')
elif '_last_page_slug' in st.session_state and url_slug != st.session_state['_last_page_slug']:
    st.session_state['page'] = SLUG_PAGES.get(url_slug, 'Trang chủ')
try:
    products = load_products(catalog_version())
    catalog_ready = not products.empty
    if products.empty:
        st.warning("Chưa có sản phẩm trong database đang được cấu hình.")
        st.caption(f"Database: {DUCKDB_PATH.name}. Trên Community Cloud, đặt DUCKDB_PATH=data/catalog.duckdb và DUCKDB_READ_ONLY=true trong Secrets, rồi khởi động lại ứng dụng. Khi chạy ở máy cá nhân, nhập dữ liệu bằng: python data/database.py --migrate-csv data/products_ocop.csv")
except Exception as exc:
    st.error(f"Không đọc được dữ liệu sản phẩm: {exc}")
    products = pd.DataFrame()
    catalog_ready = False

with st.container(key="site_header"):
    head_a, head_b = st.columns([1.15, 2.85], gap="large", vertical_alignment="center")
with head_a:
    st.button('🌿 OCOP Connect', key='logo_home', on_click=navigate, args=('Trang chủ',),
              help='Về trang chủ')
    st.markdown('<div class="brand-tagline">ĐẶC SẢN VIỆT · KẾT NỐI MUÔN NƠI</div>', unsafe_allow_html=True)
with head_b:
    pages = ["Trang chủ", "Sản phẩm OCOP", "Vùng miền", "Kết nối cung cầu", "Nhu cầu"]
    if actor and actor['role'] == 'buyer':
        pages = ['Trang chủ', 'Sản phẩm OCOP', 'Vùng miền', 'Nhu cầu mua hàng']
        if st.session_state['page'] in ('Kết nối cung cầu', 'Yêu cầu của tôi', 'Nhu cầu'):
            st.session_state['page'] = 'Nhu cầu mua hàng'
    if actor is None:
        pages = ['Trang chủ', 'Sản phẩm OCOP', 'Vùng miền', 'Nhu cầu mua hàng']
        if st.session_state['page'] in ('Kết nối cung cầu', 'Nhu cầu', 'Yêu cầu của tôi'):
            st.session_state['page'] = 'Nhu cầu mua hàng'
        pages.append('Đăng nhập')
    elif actor['role'] == 'seller':
        pages = ['Trang chủ', 'Sản phẩm OCOP', 'Vùng miền', 'Yêu cầu báo giá', 'Quản lý cung ứng']
        if st.session_state['page'] == 'Nhu cầu':
            st.session_state['page'] = 'Yêu cầu báo giá'
        elif st.session_state['page'] in ('Kết nối cung cầu', 'Yêu cầu của tôi', 'Nhà cung cấp'):
            st.session_state['page'] = 'Quản lý cung ứng'
    if actor and actor['role'] == 'buyer':
        pages.append('Đăng ký cung cấp')
        if st.session_state['page'] == 'Nhà cung cấp':
            st.session_state['page'] = 'Đăng ký cung cấp'
    if actor and actor['role'] == 'admin':
        pages.remove('Kết nối cung cầu')
        pages.remove('Nhu cầu')
        if st.session_state['page'] in ('Kết nối cung cầu', 'Nhu cầu', 'Duyệt nhà cung cấp'):
            st.session_state['page'] = 'Quản trị'
        pages.append('Quản trị')
        pages.append('Hiệu quả kết nối')
    if st.session_state['page'] not in pages:
        st.session_state['page'] = 'Trang chủ'
    sync_page_url()
    st.session_state["navigation_page"] = st.session_state["page"]
    st.segmented_control("Điều hướng", options=pages, key="navigation_page", on_change=sync_navigation, label_visibility="collapsed", width="stretch")
st.divider()

if st.session_state.get('auth_session') is not None:
    with st.container(key='account_bar'):
        identity_col, logout_col = st.columns([6, 1], gap='small', vertical_alignment='center')
        with identity_col:
            if actor:
                role = actor['role'] if actor['role'] in ('buyer', 'seller', 'admin') else ''
                st.markdown(
                    f'<div class="account-identity"><span>Tài khoản</span>'
                    f'<span class="account-name">{html.escape(actor["username"])}</span>'
                    f'<span class="account-role account-role-{role}">{html.escape(role_label(actor["role"]))}</span></div>',
                    unsafe_allow_html=True)
            else:
                st.caption('Chưa xác minh được tài khoản')
        with logout_col:
            if st.button('Đăng xuất', key='logout', on_click=auth.logout, args=(st.session_state,), width="stretch"):
                st.rerun()

current_page = st.session_state["page"]
with st.container(key='public_workspace' if current_page in ('Trang chủ', 'Sản phẩm OCOP', 'Vùng miền') else 'business_workspace'):
    if current_page in ('Trang chủ', 'Sản phẩm OCOP', 'Vùng miền') and not catalog_ready:
        st.info('Catalog chưa sẵn sàng. Bạn vẫn có thể đăng nhập và quản lý hồ sơ của mình.')
    elif current_page == "Trang chủ":
        home(products)
    elif current_page == "Sản phẩm OCOP":
        directory(products)
    elif current_page == "Vùng miền":
        regions(products)
    elif current_page == 'Đăng nhập':
        auth_ui.login()
    elif current_page == 'Nhu cầu mua hàng':
        if actor is None:
            guest_purchase()
        else:
            purchase_ui.page(title='Nhu cầu mua hàng')
            if not st.session_state.get('_buyer_create_open'):
                with st.expander('Yêu cầu trước đây'):
                    st.caption('Các yêu cầu liên hệ đã gửi qua biểu mẫu cũ.')
                    auth_ui.requests_page(embedded=True, legacy=True)
    elif current_page == 'Yêu cầu của tôi':
        if actor and actor['role'] == 'buyer':
            connect()
        else:
            auth_ui.requests_page()
    elif current_page == 'Quản trị':
        st.title('Quản trị')
        demand_tab, request_tab, supplier_tab = st.tabs(
            ['Nhu cầu mua hàng', 'Yêu cầu & tài khoản', 'Duyệt nhà cung cấp'])
        with demand_tab:
            purchase_ui.page(title=None)
        with request_tab:
            auth_ui.requests_page(admin=True, embedded=True)
        with supplier_tab:
            supplier_ui.page(admin=True, embedded=True)
    elif current_page in ('Nhà cung cấp', 'Đăng ký cung cấp', 'Quản lý cung ứng'):
        supplier_ui.page()
    elif current_page == 'Yêu cầu báo giá':
        purchase_ui.page(title='Yêu cầu báo giá')
    elif current_page == 'Duyệt nhà cung cấp':
        supplier_ui.page(admin=True)
    elif current_page == 'Nhu cầu':
        purchase_ui.page()
    elif current_page == 'Hiệu quả kết nối':
        dashboard_ui.page()
    else:
        connect()

st.divider()
search_module.floating_chat()
st.markdown('<div class="fineprint">© 2026 OCOP Connect </div>', unsafe_allow_html=True)
if st.session_state.pop('_chat_refresh', False):
    st.rerun()
