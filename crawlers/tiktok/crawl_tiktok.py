"""Visible Chrome crawler. Python 3.10+. No private API or CAPTCHA bypass."""
import argparse
import csv
import json
import logging
from decimal import Decimal, InvalidOperation
import os
import re
import subprocess
import sys
import shutil
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from crawlers.provinces import infer_province_hint

DEFAULT_URL = 'https://www.tiktok.com/shop/vn/pdp/1729548084941785497'
OCOP_FIELDS = ['product_id', 'product_name', 'brand', 'category_name', 'province_name',
               'ocop_stars', 'description', 'source_url', 'image_url', 'price', 'source']
FIELDS = ['product_id', 'product_name', 'brand', 'category_name', 'province_name',
          'ocop_stars', 'description', 'source_url', 'image_url', 'price', 'source',
          'currency', 'rating_avg', 'review_count', 'images_json', 'ocop_stars_basis',
          'extraction_method', 'crawl_status', 'crawled_at', 'seller_name', 'sale_price']


def product_id(url):
    u = urlsplit(url)
    if u.scheme != 'https' or not (u.hostname == 'tiktok.com' or (u.hostname or '').endswith('.tiktok.com')):
        raise ValueError('Chi nhan URL HTTPS thuoc tiktok.com')
    m = re.search(r'/pdp/(?:[^/?]+/)?(\d+)(?:/|$)', u.path)
    if not m:
        raise ValueError('URL phai co /pdp/<product_id> hoac /pdp/<slug>/<product_id>')
    return m[1]


def walk(value):
    if isinstance(value, dict):
        yield value
        for item in value.values():
            yield from walk(item)
    elif isinstance(value, list):
        for item in value:
            yield from walk(item)


def clean(value):
    return re.sub(r'\s+', ' ', str('' if value is None else value)).strip()


def dom_details(soup, url):
    """Read product fields, retaining the crossed-out list price when present."""
    root = soup.select_one('main') or soup
    result = {}
    money = re.compile(r'(?:[₫đ]\s*([0-9]+(?:[.,\s][0-9]{3})*)|([0-9]+(?:[.,\s][0-9]{3})*)\s*(?:₫|đ|VND))', re.I)
    for el in root.select('del, s, [style*="line-through"], [class*="line-through"], [class*="original-price"], [class*="originalPrice"]'):
        if el.find_parent(attrs={'hidden': True}) or el.has_attr('hidden'):
            continue
        match = money.search(el.get_text(' ', strip=True))
        if match:
            result['original_price'] = int(re.sub(r'\D', '', match[1] or match[2]))
            from bs4 import BeautifulSoup
            price_block = BeautifulSoup(str(el.parent), 'html.parser')
            for old in price_block.select('del, s, [style*="line-through"], [class*="line-through"]'):
                old.decompose()
            current = money.search(price_block.get_text(' ', strip=True))
            if current:
                result['price'] = int(re.sub(r'\D', '', current[1] or current[2]))
                result['currency'] = 'VND'
            break
    for el in root.select('script, style, noscript, del, s, [hidden], [aria-hidden="true"]'):
        el.decompose()
    def value(el):
        return clean(el.get('content') or el.get_text(' ', strip=True))
    for field, selector in {
        'brand': '[itemprop="brand"], [data-testid="product-brand"]',
        'description': '[itemprop="description"], [data-testid="product-description"], [class*="product-description"], [class*="productDescription"]',
        'seller_name': '[data-testid="seller-name"], [class*="seller-name"], [class*="sellerName"]',
    }.items():
        el = root.select_one(selector)
        if el:
            result[field] = value(el)
    # Breadcrumb links exclude the shop home and the current product.
    crumbs = root.select('[itemtype*="BreadcrumbList"] [itemprop="name"], nav[aria-label*="readcrumb"] a, [class*="breadcrumb"] a, [class*="Breadcrumb"] a')
    categories = [value(el) for el in crumbs if value(el)
                  and value(el).lower() != 'tiktok shop'
                  and '/pdp/' not in el.get('href', '')]
    if not categories:
        categories = [value(el) for el in root.select('a[href*="/shop/"][href*="/category/"]') if value(el)]
    if categories:
        result['category_name'] = ' > '.join(dict.fromkeys(categories))
    labels = {'product description', 'mô tả sản phẩm', 'description'}
    for heading in root.find_all(['h2', 'h3', 'h4', 'div', 'span', 'button']):
        label = clean(heading.get_text(' ', strip=True)).rstrip(':').lower()
        if label not in labels:
            continue
        # Accordion content is commonly a sibling of a header wrapper.
        node = heading
        for _ in range(3):
            sibling = node.find_next_sibling()
            if sibling and sibling.name not in ('script', 'style'):
                result.setdefault('description', value(sibling))
                break
            node = node.parent
            if node is None or node is root:
                break
    lines = list(root.stripped_strings)
    for index, line in enumerate(lines):
        seller_vi = re.fullmatch(r'Do\s+(.+?)\s+bán', line, re.I)
        if seller_vi:
            result.setdefault('seller_name', clean(seller_vi[1]))
        match = re.fullmatch(r'(?:Sold by|Bán bởi|Người bán)\s*:?\s*(.*)', line, re.I)
        if match:
            result.setdefault('seller_name', clean(match[1]) or (clean(lines[index + 1]) if index + 1 < len(lines) else ''))
        if line.rstrip(':').lower() in ('brand', 'thương hiệu') and index + 1 < len(lines):
            result.setdefault('brand', clean(lines[index + 1]))
    price_nodes = root.select('[itemprop="price"], [data-testid*="price"], [class*="price"], [class*="Price"]')
    # Only accept amounts explicitly marked as VND. Exclude crossed-out prices.
    money = re.compile(r'(?:[₫đ]\s*([0-9]+(?:[.,\s][0-9]{3})*)|([0-9]+(?:[.,\s][0-9]{3})*)\s*(?:₫|đ|VND))', re.I)
    for el in price_nodes:
        if any(re.search(r'original|old|origin|line-through', str(n.get('class', '')) + str(n.get('style', '')), re.I) for n in [el, *el.parents]):
            continue
        match = money.search(value(el))
        if match:
            result.setdefault('price', int(re.sub(r'\D', '', match[1] or match[2])))
            result['currency'] = 'VND'
            break
    return result


def parse_html(html, url, rendered=None):
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(html, 'html.parser')
    pid = product_id(url)
    candidates = []
    for script in soup.select('script[type="application/ld+json"]'):
        try:
            for obj in walk(json.loads(script.string or script.get_text())):
                types = obj.get('@type', [])
                if 'Product' in ([types] if isinstance(types, str) else types):
                    candidates.append(obj)
        except (ValueError, TypeError):
            continue
    # Avoid silently selecting a recommendation when several Product objects exist.
    matches = [p for p in candidates if str(p.get('productID', '')) == pid
               or str(p.get('sku', '')) == pid or pid in str(p.get('url', ''))]
    p = matches[0] if matches else (candidates[0] if len(candidates) == 1 else {})
    def meta(key):
        el = soup.find('meta', attrs={'property': key})
        return clean(el.get('content')) if el else ''
    h1 = soup.find('h1')
    name = clean(p.get('name')) or (clean(h1.get_text(' ')) if h1 else '') or meta('og:title')
    if not name or re.search(r'^(TikTok(?: Shop)?|Log in|Đăng nhập|Access Denied|Just a moment)[.!…\s]*$', name, re.I):
        raise ValueError('Khong tim thay ten san pham; trang co the dang bi chan/dang nhap')
    offers = p.get('offers') or {}
    if isinstance(offers, list):
        offers = offers[0] if offers else {}
    if not isinstance(offers, dict):
        offers = {}
    # Only use explicit price, never infer a price from unrelated page numbers.
    raw_price = offers.get('price')
    price = ''
    currency = clean(offers.get('priceCurrency')).upper()
    if raw_price is not None and currency == 'VND':
        try:
            amount = Decimal(str(raw_price))
            if amount.is_finite() and amount >= 0 and amount == amount.to_integral_value():
                price = int(amount)
        except (InvalidOperation, TypeError, ValueError):
            pass
    images = p.get('image') or []
    if not isinstance(images, list):
        images = [images]
    images = [x.get('url', '') if isinstance(x, dict) else x for x in images]
    images = [x for x in images if isinstance(x, str) and x.startswith('http')]
    if not images and meta('og:image'):
        images = [meta('og:image')]
    brand = p.get('brand') or ''
    if isinstance(brand, dict):
        brand = brand.get('name', '')
    rating = p.get('aggregateRating') or {}
    if not isinstance(rating, dict):
        rating = {}
    stars = re.search(r'OCOP\s*([1-5])\s*(?:sao|star)', name, re.I)
    desc = BeautifulSoup(str(p.get('description') or ''), 'html.parser').get_text(' ', strip=True)
    fallback = dom_details(soup, url)
    # Selenium can inspect rendered text and computed styles even with hashed classes.
    for key, val in (rendered or {}).items():
        if key in ('price', 'original_price', 'currency', 'category_name', 'seller_name') and val != '' and val is not None:
            fallback[key] = val
    row = dict(zip(FIELDS, [pid, name, clean(brand), clean(p.get('category')), 'Chưa cập nhật',
        int(stars[1]) if stars else '', desc, url, images[0] if images else '', price, 'TIKTOK',
        currency, rating.get('ratingValue', ''),
        rating.get('reviewCount', rating.get('ratingCount', '')), json.dumps(images, ensure_ascii=False),
        'Tên sản phẩm, chưa xác minh chứng nhận' if stars else '',
        'json_ld' if p else 'dom_meta', 'ok' if p and price != '' else 'partial',
        datetime.now(timezone.utc).isoformat(), '', '']))
    used_dom = False
    original_price = fallback.pop('original_price', '')
    for key, val in fallback.items():
        if row.get(key, '') == '' and val != '':
            row[key] = val
            used_dom = True
    row['sale_price'] = row['price']
    if original_price != '':
        row['price'] = original_price
        row['currency'] = 'VND'
        used_dom = True
    # User's dataset defines brand as the store shown after "Sold by".
    if row['seller_name']:
        row['brand'] = row['seller_name']
        used_dom = True
    row['extraction_method'] = 'json_ld+dom' if p and used_dom else ('json_ld' if p else 'dom_meta')
    row['crawl_status'] = 'ok' if all(row[k] != '' for k in ('price', 'category_name', 'description')) else 'partial'
    return row


def atomic_write(path, writer):
    fd, temp = tempfile.mkstemp(dir=path.parent, suffix='.tmp')
    try:
        with os.fdopen(fd, 'w', encoding='utf-8-sig' if path.suffix == '.csv' else 'utf-8', newline='') as f:
            writer(f)
        os.replace(temp, path)
    finally:
        if os.path.exists(temp):
            os.unlink(temp)


def read_output_rows(folder):
    for name in ('products_tiktok.csv', 'products_ocop.csv', 'products.csv', 'products_detail.csv'):
        path = folder / name
        if not path.exists():
            continue
        with path.open(encoding='utf-8-sig', newline='') as stream:
            reader = csv.DictReader(stream)
            if not {'product_id', 'source'}.issubset(reader.fieldnames or []):
                raise ValueError('CSV thieu product_id/source; dung lai de tranh mat du lieu')
            return list(reader)
    return []


def upsert(folder, row):
    """CSV is authoritative; JSONL is regenerated. Run only one process per folder."""
    folder.mkdir(parents=True, exist_ok=True)
    old = read_output_rows(folder)
    row = normalize_ocop(row)
    key = (row['source'], row['product_id'])
    found = False
    for i, existing in enumerate(old):
        if (existing.get('source'), existing.get('product_id')) == key:
            # Missing fields in partial crawls must not erase previously populated values.
            updates = {k: v for k, v in row.items() if v != '' and v is not None
                       and not (k == 'province_name' and existing.get(k) and existing[k] != 'Chưa cập nhật')
                       and not (k == 'images_json' and v == '[]' and existing.get(k))}
            old[i] = {**existing, **updates}
            found = True
            break
    if not found:
        old.append(row)
    export_ocop(folder, old)


def normalize_ocop(row):
    result = {k: clean(row.get(k)) for k in OCOP_FIELDS}
    result['source'] = result['source'].upper()
    result['province_name'] = province_name(result)
    # Keep IDs as strings; do not guess brand/province/category from the seller name.
    result['ocop_stars'] = None
    try:
        stars = Decimal(str(row.get('ocop_stars', '')))
        if stars.is_finite() and stars == stars.to_integral_value() and 1 <= stars <= 5:
            result['ocop_stars'] = int(stars)
    except (InvalidOperation, ValueError):
        pass
    result['price'] = None
    currency = clean(row.get('currency', 'VND')).upper()
    if currency == 'VND':
        try:
            price = Decimal(str(row.get('price', '')))
            if price.is_finite() and price >= 0 and price == price.to_integral_value():
                result['price'] = int(price)
        except (InvalidOperation, ValueError):
            pass
    return result


def province_name(row):
    """Fill unknown provinces using the same title hints as Tiki."""
    current = clean(row.get('province_name'))
    if current and current.casefold() not in ('chưa cập nhật', 'nan', 'none', 'null', '<na>'):
        return current
    return infer_province_hint(row.get('product_name', ''))['province_hint'] or 'Chưa cập nhật'


def backfill_provinces(folder):
    """Update only unknown province cells; preserve all other CSV columns/values."""
    path = folder / 'products_tiktok.csv'
    if not path.is_file() or not path.stat().st_size:
        return 0
    with path.open(encoding='utf-8-sig', newline='') as stream:
        reader = csv.DictReader(stream)
        fields = list(reader.fieldnames or [])
        if not {'product_name', 'province_name', 'source'}.issubset(fields):
            raise ValueError('CSV thiếu product_name/province_name/source')
        rows = list(reader)
    changed = 0
    for row in rows:
        if clean(row.get('source')).upper() != 'TIKTOK':
            continue
        province = province_name(row)
        if province != 'Chưa cập nhật' and province != row['province_name']:
            row['province_name'] = province
            changed += 1
    if changed:
        backup = path.with_name(path.stem + '_backup_provinces_' + datetime.now().strftime('%Y%m%d_%H%M%S_%f') + '.csv')
        shutil.copy2(path, backup)
        def write_csv(stream):
            writer = csv.DictWriter(stream, fieldnames=fields)
            writer.writeheader()
            writer.writerows(rows)
        atomic_write(path, write_csv)
    return changed


def export_ocop(folder, rows):
    normalized = [normalize_ocop(r) for r in rows]
    def write_csv(f):
        writer = csv.DictWriter(f, fieldnames=OCOP_FIELDS)
        writer.writeheader()
        writer.writerows(normalized)
    atomic_write(folder / 'products_tiktok.csv', write_csv)
    atomic_write(folder / 'products_tiktok.jsonl', lambda f: f.writelines(
        json.dumps(r, ensure_ascii=False, allow_nan=False) + '\n' for r in normalized))


def rendered_details(driver):
    """Read visible product price and breadcrumbs without depending on CSS class names."""
    return driver.execute_script(r'''
        const result = {};
        const visible = el => {
            const r = el.getBoundingClientRect();
            const s = getComputedStyle(el);
            return r.width > 0 && r.height > 0 && s.visibility !== 'hidden' && s.display !== 'none';
        };
        const text = el => (el.innerText || '').replace(/\s+/g, ' ').trim();
        const seller = [...document.querySelectorAll('span, div, p')].find(el =>
            visible(el) && (/^(?:Sold by|Bán bởi|Người bán)\s*:?\s*\S/i.test(text(el)) || /^Do\s+.+?\s+bán$/i.test(text(el))) && text(el).length < 150);
        if (seller) result.seller_name = text(seller).replace(/^(?:Sold by|Bán bởi|Người bán)\s*:?\s*/i, '').replace(/^Do\s+(.+?)\s+bán$/i, '$1').trim();
        // Breadcrumbs need not be links or have a stable breadcrumb class.
        const home = [...document.querySelectorAll('a')].find(el => visible(el) && /^TikTok Shop$/i.test(text(el)));
        if (home) {
            let node = home.parentElement;
            for (let depth = 0; node && depth < 5; depth++, node = node.parentElement) {
                const links = [...node.querySelectorAll('a')].filter(visible);
                if (links.length < 3) continue;
                if (text(node).length > 700) break;
                const categories = links.filter(el => el !== home && !/\/pdp\//.test(el.href))
                    .map(text).filter(Boolean);
                if (categories.length) {
                    result.category_name = [...new Set(categories)].join(' > ');
                    break;
                }
            }
        }
        const heading = document.querySelector('h1');
        if (!heading) return result;
        const titleY = heading.getBoundingClientRect().top;
        const money = /(?:[₫đ]\s*(\d+(?:[.,\s]\d{3})*)|(\d+(?:[.,\s]\d{3})*)\s*(?:₫|đ|VND))/i;
        const crossed = el => {
            for (let node = el; node && node !== document.body; node = node.parentElement) {
                if (['DEL', 'S'].includes(node.tagName) || getComputedStyle(node).textDecorationLine.includes('line-through')) return true;
            }
            return false;
        };
        const amounts = [...document.querySelectorAll('span, div, p, strong, b, del, s')].filter(el => {
            if (!visible(el)) return false;
            const t = text(el), r = el.getBoundingClientRect();
            if (el.closest('[role="dialog"]') || /shipping|vận chuyển/i.test(t)) return false;
            if (t.length > 100 || !money.test(t) || Math.abs(r.top - titleY) > 500) return false;
            return true;
        });
        const originals = amounts.filter(crossed);
        originals.sort((a, b) => Math.abs(a.getBoundingClientRect().top - titleY) - Math.abs(b.getBoundingClientRect().top - titleY));
        if (originals.length) {
            const match = text(originals[0]).match(money);
            result.original_price = Number((match[1] || match[2]).replace(/\D/g, ''));
            const block = originals[0].parentElement.cloneNode(true);
            for (const el of block.querySelectorAll('del, s, [class*="line-through"], [style*="line-through"]')) el.remove();
            const current = block.textContent.replace(/\s+/g, ' ').match(money);
            if (current) {
                result.price = Number((current[1] || current[2]).replace(/\D/g, ''));
                result.currency = 'VND';
            }
        }
        const candidates = amounts.filter(el => !crossed(el));
        // Prefer a price element without a nested price element; avoid a wrapper
        // combining the current price with the original crossed-out amount.
        const leaves = candidates.filter(el => !candidates.some(other => other !== el && el.contains(other)));
        leaves.sort((a, b) => Math.abs(a.getBoundingClientRect().top - titleY) - Math.abs(b.getBoundingClientRect().top - titleY));
        if (leaves.length && result.price === undefined) {
            const match = text(leaves[0]).match(money);
            result.price = Number((match[1] || match[2]).replace(/\D/g, ''));
            result.currency = 'VND';
        }
        return result;
    ''') or {}


def saved_product_ids(folder):
    return {row['product_id'] for row in read_output_rows(folder) if row['source'].upper() == 'TIKTOK'}


def pending_urls(urls, completed, attempted):
    """Deduplicate by product ID, including URLs with a different slug/query."""
    for url in urls:
        try:
            pid = product_id(url)
        except ValueError:
            logging.warning('Bo qua URL khong hop le: %s', url)
            continue
        if pid in completed or pid in attempted:
            continue
        attempted.add(pid)
        yield url


def watch_urls(urls_file, explicit_urls, folder, once=False, poll_interval=2):
    attempted = set()
    while True:
        urls = list(explicit_urls)
        if urls_file:
            try:
                urls += [line.strip() for line in urls_file.read_text(encoding='utf-8-sig').splitlines()
                         if line.strip() and not line.lstrip().startswith('#')]
            except FileNotFoundError:
                logging.warning('Chua tim thay %s; dang cho file', urls_file)
        yield from pending_urls(urls, saved_product_ids(folder), attempted)
        if once:
            return
        time.sleep(max(0.2, poll_interval))


def sync_master(folder):
    """Import saved TikTok products, including runs with no new URLs."""
    csv_path = folder / 'products_tiktok.csv'
    if not csv_path.is_file() or not csv_path.stat().st_size:
        logging.info('No crawler CSV to sync: %s', csv_path)
        return
    pipeline = Path(__file__).resolve().parents[2] / 'pipelines' / 'sync_products.py'
    subprocess.run(
        [sys.executable, '-X', 'utf8', str(pipeline),
         '--source', 'TIKTOK', '--input', str(csv_path.resolve())],
        check=True,
    )


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--url', action='append', help='Co the lap lai nhieu lan')
    ap.add_argument('--urls-file', type=Path)
    ap.add_argument('--once', action='store_true', help='Chi doc file mot lan (mac dinh)')
    ap.add_argument('--watch', action='store_true', help='Tuy chon: theo doi file de crawl link moi lien tuc')
    ap.add_argument('--poll-interval', type=float, default=2, help='So giay giua cac lan kiem tra urls_tiktok.txt')
    ap.add_argument('--output', type=Path, default=Path(__file__).resolve().parent / 'ocop_output')
    ap.add_argument('--profile', type=Path, default=Path(__file__).resolve().parent / 'chrome_profile')
    ap.add_argument('--manual', action='store_true', help='Tuy chon: cho Enter moi trang de kiem tra thu cong')
    ap.add_argument('--delay', type=float, default=4)
    ap.add_argument('--save-html', action='store_true', help='Luu HTML de debug; co the chua du lieu phien')
    ap.add_argument('--backfill-provinces', action='store_true', help='Chi bo sung tinh con thieu trong CSV da co, khong crawl')
    args = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
    changed = backfill_provinces(args.output)
    logging.info('Đã bổ sung province_name cho %s sản phẩm TikTok.', changed)
    if args.backfill_provinces:
        return
    if not args.url and not args.urls_file:
        args.urls_file = Path(__file__).resolve().parent / 'urls_tiktok.txt'
    once = args.once or not args.watch or args.urls_file is None
    args.output.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
    from selenium import webdriver
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import WebDriverWait
    options = webdriver.ChromeOptions()
    options.add_argument('--user-data-dir=' + str(args.profile.resolve()))
    options.add_argument('--lang=vi-VN')
    options.add_argument('--start-maximized')
    driver = None
    failures = 0
    try:
        if not once:
            logging.info('Dang theo doi %s; chi crawl san pham chua luu. Ctrl+C de dung.', args.urls_file)
        for url in watch_urls(args.urls_file, args.url or [], args.output, once, args.poll_interval):
            try:
                if driver is None:
                    driver = webdriver.Chrome(options=options)
                    driver.set_page_load_timeout(60)
                logging.info('Crawl san pham moi: %s', url)
                driver.get(url)
                WebDriverWait(driver, 30).until(lambda d: d.find_elements(By.TAG_NAME, 'body'))
                time.sleep(max(0, args.delay))
                if args.manual:
                    input('Dang nhap/giai CAPTCHA thu cong neu co, mo mo ta. Nhan Enter khi san pham hien day du: ')
                html = driver.page_source
                if args.save_html:
                    (args.output / (product_id(url) + '.html')).write_text(html, encoding='utf-8')
                # Check redirect so a different product cannot be saved under the requested ID.
                if product_id(driver.current_url) != product_id(url):
                    raise ValueError('Trang chuyen sang san pham khac')
                row = parse_html(html, url, rendered_details(driver))
                if row['crawl_status'] == 'partial' and not args.manual:
                    logging.info('Du lieu chua day du; tu dong cho them roi doc lai trang')
                    time.sleep(max(0, args.delay))
                    html = driver.page_source
                    if product_id(driver.current_url) != product_id(url):
                        raise ValueError('Trang chuyen sang san pham khac')
                    if args.save_html:
                        (args.output / (product_id(url) + '.html')).write_text(html, encoding='utf-8')
                    row = parse_html(html, url, rendered_details(driver))
                if row['crawl_status'] == 'partial':
                    missing = [key for key in ('price', 'category_name', 'description') if row[key] == '']
                    logging.warning('Luu du lieu partial, cac truong con thieu: %s', ', '.join(missing))
                upsert(args.output, row)
                logging.info('Da luu: %s | price=%s | status=%s', row['product_name'], row['price'], row['crawl_status'])
            except Exception:
                failures += 1
                logging.exception('Khong luu san pham nay; khong tu lap lai trong phien nay. Khoi dong lai de thu lai.')
    except KeyboardInterrupt:
        logging.info('Da dung theo doi urls_tiktok.txt')
    finally:
        try:
            if driver is not None:
                driver.quit()
        finally:
            sync_master(args.output)
    if failures:
        raise SystemExit(1)


if __name__ == '__main__':
    main()

