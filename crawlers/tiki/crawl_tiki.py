import csv
import json
import logging
import re
import shutil
import subprocess
import sys
import time
import unicodedata
from datetime import datetime
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import pandas as pd
import requests
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.common.exceptions import WebDriverException
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By

ROOT = Path(__file__).resolve().parent
OUTPUT = ROOT / 'ocop_output'
OUTPUT.mkdir(exist_ok=True)
CSV_PATH = OUTPUT / 'products_tiki.csv'
URL_FILE = ROOT / 'urls.txt'
DEFAULT_URLS = ['https://tiki.vn/dac-san-phu-quoc-hop-6-chai-thuy-tinh-nuoc-mam-phu-quoc-khai-hoan-43-do-dam-90ml-chai-ocop-5-sao-p94737269.html?spid=94737270']
KEEP_CHROME_OPEN = True
WAIT_SECONDS = 3

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


logging.basicConfig(level=logging.INFO, format='%(message)s')


def load_urls():
    if URL_FILE.exists():
        urls = [x.strip() for x in URL_FILE.read_text(encoding='utf-8-sig').splitlines() if x.strip() and not x.lstrip().startswith('#')]
        return list(dict.fromkeys(urls))
    return DEFAULT_URLS


def ids_from_url(url):
    m = re.search(r'-p(\d+)\.html', url)
    spid = parse_qs(urlparse(url).query).get('spid', [''])[0]
    return (m.group(1) if m else '', spid)


def find_product_jsonld(soup):
    def walk(value):
        if isinstance(value, list):
            for v in value:
                found = walk(v)
                if found:
                    return found
        if isinstance(value, dict):
            typ = value.get('@type', [])
            if isinstance(typ, str):
                typ = [typ]
            if 'Product' in typ:
                return value
            for key in ('@graph', 'mainEntity'):
                found = walk(value.get(key))
                if found:
                    return found
        return None
    for script in soup.select('script[type="application/ld+json"]'):
        try:
            found = walk(json.loads(script.string or script.get_text()))
            if found:
                return found
        except (ValueError, TypeError):
            pass
    return {}


def normalize_images(value):
    if isinstance(value, str):
        return [value] if value.startswith('http') else []
    if isinstance(value, dict):
        return normalize_images(value.get('url') or value.get('contentUrl'))
    if isinstance(value, list):
        out = []
        for item in value:
            out.extend(normalize_images(item))
        return list(dict.fromkeys(out))
    return []


def clean_text(value):
    if not value:
        return ''
    soup = BeautifulSoup(str(value), 'html.parser')
    for tag in soup(['script', 'style', 'noscript']):
        tag.decompose()
    return soup.get_text('\n', strip=True)


def is_truncated(value):
    return bool(re.search(r'(?:\.\.\.|…)[\s\"\']*$', (value or '').strip()))


def choose_description(candidates):
    cleaned = [(html, clean_text(html)) for html in candidates if html]
    cleaned = [(h, t) for h, t in cleaned if t]
    if not cleaned:
        return '', ''
    # Prefer non-truncated, longer candidates; no fabricated continuation.
    return max(cleaned, key=lambda x: (not is_truncated(x[1]), len(x[1])))


def embedded_candidates(soup):
    """Find description/specifications in embedded page JSON, if present."""
    descriptions, specs = [], {}
    def walk(obj, depth=0):
        if depth > 25:
            return
        if isinstance(obj, list):
            for v in obj:
                walk(v, depth + 1)
        elif isinstance(obj, dict):
            for k, v in obj.items():
                key = str(k).lower()
                if key in ('description', 'description_html', 'product_description') and isinstance(v, str) and len(v) > 80:
                    descriptions.append(v)
                if key in ('specifications', 'specification') and isinstance(v, list):
                    for group in v:
                        if not isinstance(group, dict):
                            continue
                        attrs = group.get('attributes') or []
                        for attr in attrs if isinstance(attrs, list) else []:
                            if isinstance(attr, dict):
                                label = attr.get('display_name') or attr.get('name')
                                value = attr.get('value')
                                if label and value is not None:
                                    specs[str(label)] = str(value)
                if isinstance(v, (dict, list)):
                    walk(v, depth + 1)
    for script in soup.select('script[type="application/json"], script#__NEXT_DATA__'):
        try:
            walk(json.loads(script.string or script.get_text()))
        except (ValueError, TypeError, RecursionError):
            pass
    return descriptions, specs


def extract_tiki_description(driver):
    """Read the actual expanded Tiki description, not SEO preview."""
    container_css = 'div.content:has(a[data-view-id="pdp_view_description_button"])'
    button_css = 'a[data-view-id="pdp_view_description_button"]'
    try:
        buttons = driver.find_elements(By.CSS_SELECTOR, button_css)
        for button in buttons:
            if not button.is_displayed():
                continue
            driver.execute_script('arguments[0].scrollIntoView({block:"center"});', button)
            time.sleep(0.3)
            if any(t in button.text.lower() for t in ('xem thêm', 'xem tất cả', 'đọc thêm')):
                driver.execute_script('arguments[0].click();', button)
                time.sleep(0.8)
            # 'Thu gọn' means expanded; never click it.
        containers = driver.find_elements(By.CSS_SELECTOR, container_css)
        candidates = []
        for el in containers:
            if not el.is_displayed():
                continue
            # The inner content is the sibling of the expand/collapse link.
            html = driver.execute_script('''
                const el = arguments[0];
                const link = el.querySelector('a[data-view-id="pdp_view_description_button"]');
                const parent = link ? link.parentElement : el;
                const content = parent ? [...parent.children].filter(n => n !== link) : [];
                return content.map(n => n.outerHTML).join('\n');
            ''', el) or ''
            if html:
                candidates.append(html)
        return choose_description(candidates)
    except WebDriverException as exc:
        logging.warning('  Không đọc được mô tả DOM Tiki: %s', exc)
        return '', ''


def extract_dom_description(soup):
    selectors = [
        '#product-description',
        '[data-view-id="pdp_main_view_description"]',
        '[class*="ProductDescription"]',
        '[class*="product-description"]',
        '[class*="Description__Wrapper"]',
        '[class*="description"]',
        'div.content:has(a[data-view-id="pdp_view_description_button"])',
    ]
    candidates = []
    for selector in selectors:
        for element in soup.select(selector):
            candidates.append(element.decode_contents())
    return candidates


def parse_specifications(soup):
    result = {}
    selectors = [
        '[data-view-id="pdp_main_view_specification"]',
        '[class*="Specification"]',
        '[class*="specification"]',
        '[class*="ProductDetail"]',
    ]
    for selector in selectors:
        for section in soup.select(selector):
            for row in section.select('tr'):
                cells = row.find_all(['td', 'th'], recursive=False)
                if len(cells) >= 2:
                    key, val = [x.get_text(' ', strip=True) for x in cells[:2]]
                    if key and val and len(key) < 120:
                        result[key] = val
            for row in section.select('[class*="Row"], [class*="row"]'):
                children = row.find_all(recursive=False)
                if len(children) == 2:
                    key, val = [x.get_text(' ', strip=True) for x in children]
                    if key and val and len(key) < 120 and len(val) < 1500 and key != val:
                        result.setdefault(key, val)
    return result


def click_expand_buttons(driver):
    xpath = ('//*[self::button or self::a or @role="button" or self::div or self::span]'
             '[contains(normalize-space(.), "Xem thêm") or '
             'contains(normalize-space(.), "Xem tất cả") or '
             'contains(normalize-space(.), "Xem chi tiết") or '
             'contains(normalize-space(.), "Đọc thêm")]')
    for element in driver.find_elements(By.XPATH, xpath):
        try:
            label = element.text.strip()
            if not label or len(label) > 75 or not element.is_displayed() or 'thu gọn' in label.lower():
                continue
            driver.execute_script('arguments[0].scrollIntoView({block:"center"});', element)
            time.sleep(0.3)
            element.click()
            time.sleep(0.8)
        except WebDriverException:
            continue


def extract_category_levels(*soups):
    """Read category levels 2 and 3, excluding home and product links."""
    for soup in soups:
        links = soup.select(
            '[data-view-id="breadcrumb_container"] '
            'a[data-view-id="breadcrumb_item"][href]'
        )
        names = []
        for link in links:
            href = link.get('href', '')
            name = link.get_text(' ', strip=True)
            if name and re.search(r'/c\d+(?:[/?#]|$)', href):
                names.append(name)
        if names:
            return {
                'category_level_2': names[1] if len(names) >= 2 else '',
                'category_level_3': names[2] if len(names) >= 3 else '',
            }
    return {'category_level_2': '', 'category_level_3': ''}


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


def snapshot_product_data(soup, pid):
    """Select the main product only, never prices of related products."""
    script = soup.select_one('script#__NEXT_DATA__')
    if not script:
        return {}
    try:
        data = json.loads(script.string or script.get_text())
        product = data['props']['initialState']['productv2']['productData']['response']['data']
        if isinstance(product, dict) and str(product.get('id', '')) == str(pid):
            return product
    except (ValueError, TypeError, KeyError):
        pass
    return {}


def numeric_price(value):
    # Structured prices only; avoid guessing locale-dependent display strings.
    if isinstance(value, bool) or value is None:
        return None
    try:
        from decimal import Decimal, InvalidOperation
        amount = Decimal(str(value).strip())
        if not amount.is_finite() or amount < 0:
            return None
        return int(amount) if amount == amount.to_integral_value() else float(amount)
    except (InvalidOperation, ValueError, TypeError, OverflowError):
        return None


def extract_selling_price(product, soup, pid, spid=''):
    data = snapshot_product_data(soup, pid)
    seller = data.get('current_seller') or {}
    if isinstance(seller, dict):
        seller_spid = str(seller.get('product_id') or '')
        if not spid or seller_spid == str(spid):
            price = numeric_price(seller.get('price'))
            if price is not None:
                return price, 'VND'
    offers = product.get('offers') or {}
    if isinstance(offers, dict):
        offers = [offers]
    for offer in offers if isinstance(offers, list) else []:
        if not isinstance(offer, dict):
            continue
        price = numeric_price(offer.get('price'))
        if price is not None:
            return price, offer.get('priceCurrency') or ''
    price = numeric_price(data.get('price'))
    return price, 'VND' if price is not None else ''


def snapshot_record(soup, pid, spid, saved_title=''):
    product = find_product_jsonld(soup)
    data = snapshot_product_data(soup, pid)
    title = product.get('name') or data.get('name') or saved_title
    brand = product.get('brand') or data.get('brand') or ''
    if isinstance(brand, dict):
        brand = brand.get('name') or ''
    price, currency = extract_selling_price(product, soup, pid, spid)
    rating = product.get('aggregateRating') or {}
    if not isinstance(rating, dict):
        rating = {}
    descriptions, specs = embedded_candidates(soup)
    descriptions += extract_dom_description(soup)
    if isinstance(product.get('description'), str):
        descriptions.append(product['description'])
    description_html, description_text = choose_description(descriptions)
    specs.update(parse_specifications(soup))
    for attr in product.get('additionalProperty') or []:
        if isinstance(attr, dict) and attr.get('name') and attr.get('value') is not None:
            specs.setdefault(str(attr['name']), str(attr['value']))
    images = normalize_images(product.get('image'))
    stars = re.search(r'OCOP\s*([3-5])\s*sao', title, re.I)
    sold = data.get('quantity_sold') or {}
    return {
        'title': title, 'brand': brand,
        'price': price, 'currency': currency,
        'rating': rating.get('ratingValue'),
        'review_count': rating.get('reviewCount'),
        'sold_count': sold.get('value') if isinstance(sold, dict) else None,
        'ocop_stars': stars.group(1) if stars else '',
        'description': description_text,
        'description_text': description_text,
        'description_html': description_html,
        'image_url': images[0] if images else '',
        'images_json': json.dumps(images, ensure_ascii=False),
        'specifications_json': json.dumps(specs, ensure_ascii=False),
        **extract_category_levels(soup),
        **infer_province_hint(saved_title or title),
    }


def empty_csv_value(value):
    return value is None or str(value).strip().lower() in (
        '', 'nan', 'none', 'null', '<na>', '{}', '[]'
    )


COLUMN_MAPPING = {
    'title': 'product_name',
    'category_level_2': 'category_name',
    'province_hint': 'province_name',
}
OCOP_COLUMNS = [
    'product_id', 'product_name', 'brand', 'category_name', 'province_name',
    'ocop_stars', 'description', 'source_url', 'image_url', 'price', 'source',
]


def normalize_ocop_record(record, defaults=True):
    record = dict(record)
    for old, new in COLUMN_MAPPING.items():
        if old in record:
            value = record.pop(old)
            if empty_csv_value(record.get(new)):
                record[new] = value
    if defaults:
        record['source'] = 'TIKI'
        if empty_csv_value(record.get('province_name')):
            record['province_name'] = 'Chưa cập nhật'
    return record


def migrate_ocop_csv():
    """Rename legacy columns locally; preserve values and create a backup."""
    if not CSV_PATH.exists() or not CSV_PATH.stat().st_size:
        return
    with CSV_PATH.open('r', encoding='utf-8-sig', newline='') as f:
        reader = csv.DictReader(f)
        old_fields = list(reader.fieldnames or [])
        old_rows = list(reader)
    rows = [normalize_ocop_record(row) for row in old_rows]
    fields = list(OCOP_COLUMNS)
    for row in rows:
        for key in row:
            if key not in fields:
                fields.append(key)
    if fields == old_fields and rows == old_rows:
        return
    backup = CSV_PATH.with_name(CSV_PATH.stem + '_backup_schema_' +
                               datetime.now().strftime('%Y%m%d_%H%M%S_%f') + '.csv')
    temporary = CSV_PATH.with_suffix('.csv.tmp')
    with temporary.open('w', encoding='utf-8-sig', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    shutil.copy2(CSV_PATH, backup)
    temporary.replace(CSV_PATH)
    logging.info('Đã chuẩn hóa cột OCOP. Backup: %s', backup)


def backfill_from_debug():
    """Fill empty CSV cells from saved HTML only, without network/browser."""
    if not CSV_PATH.exists() or not CSV_PATH.stat().st_size:
        return
    with CSV_PATH.open('r', encoding='utf-8-sig', newline='') as f:
        reader = csv.DictReader(f)
        fields = list(reader.fieldnames or [])
        rows = list(reader)
    if not {'source', 'product_id', 'spid'}.issubset(fields):
        raise ValueError('CSV thiếu cột source/product_id/spid; không chỉnh sửa dữ liệu cũ.')
    changed_rows = changed_cells = 0
    cache = {}
    for row in rows:
        if row.get('source', '').upper() != 'TIKI':
            continue
        pid, spid = row.get('product_id', ''), row.get('spid', '')
        if not re.fullmatch(r'\d+', pid):
            continue
        path = OUTPUT / f'debug_{pid}.html'
        if not path.exists():
            continue
        try:
            if pid not in cache:
                cache[pid] = BeautifulSoup(path.read_text(encoding='utf-8'), 'lxml')
            soup = cache[pid]
            # A debug file is named by product_id, but sellers can have different
            # prices. Require evidence of the requested spid before backfilling.
            meta = soup.select_one('meta[name="product"]')
            snapshot_spid = str(meta.get('content') or '') if meta else ''
            data = snapshot_product_data(soup, pid)
            seller = data.get('current_seller') or {}
            if not snapshot_spid and isinstance(seller, dict):
                snapshot_spid = str(seller.get('product_id') or '')
            if spid and snapshot_spid != spid:
                logging.warning('Bỏ qua %s: spid trong HTML không khớp %s.', path.name, spid)
                continue
            candidate = normalize_ocop_record(
                snapshot_record(soup, pid, spid, row.get('product_name', '')),
                defaults=False,
            )
            updated = 0
            for column, value in candidate.items():
                if (empty_csv_value(row.get(column)) or
                    (column == 'province_name' and row.get(column) == 'Chưa cập nhật')) and not empty_csv_value(value):
                    row[column] = value
                    if column not in fields:
                        fields.append(column)
                    updated += 1
            if updated:
                changed_rows += 1
                changed_cells += updated
                logging.info('Bổ sung %s ô trống từ %s.', updated, path.name)
        except Exception:
            logging.exception('Không đọc được %s; giữ nguyên dòng sản phẩm.', path.name)
    if not changed_cells:
        logging.info('Không có ô trống nào có thể bổ sung từ debug HTML.')
        return
    # Preserve an exact backup before replacing the CSV.
    backup = CSV_PATH.with_name(
        CSV_PATH.stem + '_backup_' + datetime.now().strftime('%Y%m%d_%H%M%S_%f') + '.csv'
    )
    temporary = CSV_PATH.with_suffix('.csv.tmp')
    with temporary.open('w', encoding='utf-8-sig', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    shutil.copy2(CSV_PATH, backup)
    temporary.replace(CSV_PATH)
    logging.info('Đã bổ sung %s ô / %s sản phẩm. Backup: %s', changed_cells, changed_rows, backup)


def scrape(url, driver, session):
    pid, spid = ids_from_url(url)
    if not pid:
        raise ValueError('Không tìm thấy product_id trong URL')
    html = ''
    try:
        response = session.get(url, timeout=25)
        if response.ok:
            html = response.text
        else:
            logging.warning('  Requests HTTP %s; thử Selenium', response.status_code)
    except requests.RequestException as exc:
        logging.warning('  Requests lỗi: %s; thử Selenium', exc)

    driver.get(url)
    time.sleep(WAIT_SECONDS)
    for fraction in (0.25, 0.55, 0.8, 1):
        driver.execute_script('window.scrollTo(0, document.body.scrollHeight * arguments[0]);', fraction)
        time.sleep(0.8)
    # Expand the exact description section before generic expansion.
    tiki_description_html, tiki_description_text = extract_tiki_description(driver)
    click_expand_buttons(driver)
    time.sleep(0.8)
    # Re-read after other expansion actions, but never collapse description.
    newer_html, newer_text = extract_tiki_description(driver)
    if len(newer_text) > len(tiki_description_text):
        tiki_description_html, tiki_description_text = newer_html, newer_text
    # Preserve modal/expanded content before dismissing anything.
    rendered_html = driver.page_source
    (OUTPUT / f'debug_{pid}.html').write_text(rendered_html, encoding='utf-8')

    soup = BeautifulSoup(rendered_html, 'lxml')
    raw_soup = BeautifulSoup(html, 'lxml') if html else soup
    category_levels = extract_category_levels(soup, raw_soup)
    product = find_product_jsonld(soup) or find_product_jsonld(raw_soup)
    offers = product.get('offers') or {}
    if isinstance(offers, list):
        offers = offers[0] if offers else {}
    if not isinstance(offers, dict):
        offers = {}
    rating = product.get('aggregateRating') or {}
    if not isinstance(rating, dict):
        rating = {}
    brand = product.get('brand')
    if isinstance(brand, dict):
        brand = brand.get('name')
    images = normalize_images(product.get('image'))
    if not images:
        tag = soup.select_one('meta[property="og:image"]')
        images = normalize_images(tag.get('content') if tag else None)
    title = product.get('name') or (soup.select_one('h1').get_text(' ', strip=True) if soup.select_one('h1') else '')

    embedded_desc, embedded_specs = embedded_candidates(soup)
    raw_embedded_desc, raw_embedded_specs = embedded_candidates(raw_soup)
    candidates = (extract_dom_description(soup) + extract_dom_description(raw_soup)
                  + embedded_desc + raw_embedded_desc)
    if isinstance(product.get('description'), str):
        candidates.append(product['description'])
    description_html, description_text = choose_description(candidates)
    # The exact expanded description DOM is more authoritative than SEO metadata.
    if tiki_description_text and (not is_truncated(tiki_description_text)):
        description_html, description_text = tiki_description_html, tiki_description_text

    specs = {**raw_embedded_specs, **embedded_specs, **parse_specifications(soup)}
    raw_specs = product.get('specifications') or []
    if isinstance(raw_specs, dict):
        raw_specs = [raw_specs]
    if isinstance(raw_specs, list):
        for group in raw_specs:
            if not isinstance(group, dict):
                continue
            for attr in group.get('attributes', []):
                if isinstance(attr, dict):
                    key = attr.get('display_name') or attr.get('name')
                    value = attr.get('value')
                    if key and value is not None:
                        specs.setdefault(str(key), str(value))
    stars = re.search(r'OCOP\s*([3-5])\s*sao', title, re.I)
    selling_price, price_currency = extract_selling_price(product, soup, pid, spid)
    if selling_price is None:
        selling_price, price_currency = extract_selling_price(product, raw_soup, pid, spid)
    record = {
        'source': 'tiki', 'product_id': pid, 'spid': spid,
        'title': title, 'brand': brand,
        **category_levels,
        **infer_province_hint(title),
        'description': description_text,
        'description_html': description_html,
        'description_text': description_text,
        'description_truncated': is_truncated(description_text) or not bool(description_text),
        'description_source': 'tiki_expanded_dom' if description_text == tiki_description_text and tiki_description_text else 'fallback',
        'description_length': len(description_text),
        'price': selling_price, 'currency': price_currency,
        'rating': rating.get('ratingValue'), 'review_count': rating.get('reviewCount'),
        'sold_count': None, 'ocop_stars': stars.group(1) if stars else None,
        'image_url': images[0] if images else None,
        'images_json': json.dumps(images, ensure_ascii=False),
        'specifications_json': json.dumps(specs, ensure_ascii=False),
        'specification_count': len(specs), 'source_url': url,
        'crawled_at': datetime.now().isoformat(timespec='seconds')
    }
    logging.info('  %s | mô tả: %s ký tự | rút gọn: %s | specs: %s',
                 title[:75], len(description_text), record['description_truncated'], len(specs))
    return normalize_ocop_record(record)


def missing(value):
    if value is None:
        return True
    if isinstance(value, (list, dict)):
        return not bool(value)
    try:
        if bool(pd.isna(value)):
            return True
    except (TypeError, ValueError):
        pass
    return isinstance(value, str) and value.strip() in ('', '{}', '[]')


def load_existing_keys():
    """Use saved CSV records as the crawl checkpoint."""
    if not CSV_PATH.exists() or CSV_PATH.stat().st_size == 0:
        return set()
    with CSV_PATH.open('r', encoding='utf-8-sig', newline='') as f:
        reader = csv.DictReader(f)
        required = {'source', 'product_id', 'spid'}
        if not required.issubset(reader.fieldnames or []):
            raise ValueError('CSV thiếu cột source/product_id/spid; không ghi đè dữ liệu cũ.')
        return {
            (row['source'].upper(), row['product_id'], row['spid'])
            for row in reader
        }


def pending_urls(urls, existing_keys):
    pending = []
    seen = set(existing_keys)
    for url in urls:
        pid, spid = ids_from_url(url)
        if not pid:
            logging.warning('Bỏ qua URL không có product_id: %s', url)
            continue
        key = ('TIKI', pid, spid)
        if key in seen:
            logging.info('Bỏ qua sản phẩm đã có hoặc link trùng: %s', url)
            continue
        pending.append(url)
        seen.add(key)
    return pending


def upsert(records):
    """Insert only: never update or deduplicate existing saved rows."""
    existing_keys = load_existing_keys()
    additions = []
    for record in records:
        record = normalize_ocop_record(record)
        key = tuple(str(record.get(k, '')) for k in ('source', 'product_id', 'spid'))
        if key not in existing_keys:
            additions.append(record)
            existing_keys.add(key)
    if not additions:
        return len(existing_keys)

    old_rows, fields = [], []
    if CSV_PATH.exists() and CSV_PATH.stat().st_size:
        with CSV_PATH.open('r', encoding='utf-8-sig', newline='') as f:
            reader = csv.DictReader(f)
            fields = list(reader.fieldnames or [])
            old_rows = list(reader)
    original_fields = list(fields)
    for record in additions:
        for field in record:
            if field not in fields:
                fields.append(field)

    if original_fields and fields == original_fields:
        # Append without rewriting existing rows.
        with CSV_PATH.open('a', encoding='utf-8', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=fields)
            writer.writerows(additions)
    else:
        # Schema expansion preserves old field values; new columns stay blank
        # for old products. Replace only once the complete file is written.
        temporary = CSV_PATH.with_suffix('.csv.tmp')
        with temporary.open('w', encoding='utf-8-sig', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=fields)
            writer.writeheader()
            writer.writerows(old_rows)
            writer.writerows(additions)
        temporary.replace(CSV_PATH)
    return len(old_rows) + len(additions)


def main():
    migrate_ocop_csv()
    backfill_from_debug()
    urls = pending_urls(load_urls(), load_existing_keys())
    if not urls:
        logging.info('Không có link mới cần crawl. Đã kiểm tra bổ sung ô trống từ debug HTML.')
        return
    logging.info('Có %s link mới cần crawl.', len(urls))
    options = Options()
    options.add_argument('--start-maximized')
    options.add_argument('--lang=vi-VN')
    if KEEP_CHROME_OPEN:
        options.add_experimental_option('detach', False)
    driver = webdriver.Chrome(options=options)
    session = requests.Session()
    session.headers.update({'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/125.0 Safari/537.36', 'Accept-Language': 'vi-VN,vi;q=0.9'})
    records = []
    try:
        for i, url in enumerate(urls, 1):
            logging.info('[%s/%s] %s', i, len(urls), url)
            try:
                record = scrape(url, driver, session)
                records.append(record)
                count = upsert([record])
                logging.info('  Đã lưu CSV; tổng %s sản phẩm', count)
            except Exception:
                logging.exception('  Crawl thất bại')
            if i < len(urls):
                time.sleep(3)
    finally:
        session.close()
        if not KEEP_CHROME_OPEN:
            driver.quit()
    logging.info('Hoàn tất. CSV: %s | thành công: %s/%s', CSV_PATH, len(records), len(urls))
    if KEEP_CHROME_OPEN:
        logging.info('Chrome được giữ mở để kiểm tra; tự đóng cửa sổ khi xong.')


def sync_master():
    """Merge saved crawler data into the shared master, including on no-new-URL runs."""
    if not CSV_PATH.is_file() or not CSV_PATH.stat().st_size:
        logging.info('No crawler CSV to sync: %s', CSV_PATH)
        return
    pipeline = ROOT.parents[1] / 'pipelines' / 'sync_products.py'
    subprocess.run(
        [sys.executable, '-X', 'utf8', str(pipeline),
         '--source', 'TIKI', '--input', str(CSV_PATH)],
        check=True,
    )


if __name__ == '__main__':
    main()
    sync_master()
