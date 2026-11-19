"""Collect Buu Dien product details into the OCOP Connect import schema."""
import argparse
import csv
import json
import re
import subprocess
import sys
import unicodedata
from pathlib import Path
from tempfile import NamedTemporaryFile
from time import sleep
from urllib.parse import parse_qs, urljoin, urlsplit

from bs4 import BeautifulSoup

BASE = "https://buudien.vn"
ROOT = Path(__file__).resolve().parents[2]
CRAWLER_DIR = Path(__file__).resolve().parent
FIELDS = (
    "product_id", "product_name", "brand", "category_name", "province_name",
    "ocop_stars", "description", "source_url", "image_url", "price", "source",
)


def site_url(value):
    parts = urlsplit(urljoin(BASE, value))
    if parts.scheme not in {"http", "https"} or parts.netloc.lower() not in {
        "buudien.vn", "nongsan.buudien.vn",
    }:
        raise ValueError("URL phải thuộc sàn Bưu điện")
    return parts._replace(scheme="https", fragment="").geturl()


def product_id(url):
    parts = urlsplit(url)
    if parts.path.lower() != "/home/goods/index.html":
        return ""
    value = parse_qs(parts.query).get("goods_id", [""])[0]
    return value if re.fullmatch(r"[0-9]+", value) else ""


def product_links(soup, page_url):
    found = {}
    for tag in soup.select("a[href]"):
        candidate = urljoin(page_url, tag["href"])
        key = product_id(candidate)
        if key and urlsplit(candidate).netloc.lower() in {
            "buudien.vn", "nongsan.buudien.vn",
        }:
            found.setdefault(key, site_url(candidate))
    return found.values()


def plain_text(soup, selector):
    node = soup.select_one(selector)
    return unicodedata.normalize("NFC", node.get_text(" ", strip=True)) if node else ""


def parse_product(soup, page_url=""):
    canonical = soup.select_one('meta[property="og:url"]')
    url = site_url(page_url or (canonical.get("content", "") if canonical else ""))
    key = product_id(url)
    name = plain_text(soup, ".name_product_details h2")
    if not key or not name:
        raise ValueError("HTML thiếu trang chi tiết sản phẩm hoặc trang bị chặn")

    spec = {}
    for script in soup.find_all("script", src=False):
        match = re.search(r"\bvar\s+spec_param\s*=\s*(\[.*?\])\s*;", script.string or "", re.S)
        if match:
            entries = json.loads(match.group(1))
            spec = next((row for row in entries if str(row.get("goods_id")) == key), {})
            break

    categories = soup.select('.breadcrumb a[href*="cate_id="]')
    desc = plain_text(soup, "#tab_1 .wp_content_tab_description_product")
    store = plain_text(soup, ".box_store .info_store h3")
    brand = plain_text(soup, '[itemprop="brand"]') or store
    stars = re.search(r"\bOCOP\s*[-:]?\s*([1-5])\s*sao\b", f"{name} {desc}", re.I)
    image = soup.select_one('meta[property="og:image"]')
    image_url = spec.get("goods_image") or (image.get("content", "") if image else "")
    price = spec.get("goods_promotion_price") or spec.get("goods_price")
    return {
        "product_id": key,
        "product_name": name,
        "brand": brand,
        "category_name": categories[-1].get_text(" ", strip=True) if categories else "",
        "province_name": plain_text(soup, ".kv_store_info .drop_kv_giaohang") or "Chưa cập nhật",
        "ocop_stars": stars.group(1) if stars else "",
        "description": desc,
        "source_url": url,
        "image_url": urljoin(url, image_url) if image_url else "",
        "price": price if price is not None else "",
        "source": "BUUDIEN",
    }


def crawl_live(urls, collect_listings, rows, on_product=None):
    from selenium import webdriver
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import WebDriverWait

    driver = None

    def load(url):
        nonlocal driver
        if driver is None:
            driver = webdriver.Chrome()
            driver.set_page_load_timeout(30)
        driver.get(url)
        selector = (
            ".name_product_details h2" if product_id(url)
            else 'a[href*="goods_id="]'
        )

        def ready(browser):
            title = browser.title.lower()
            if "403" in title or "truy cập bị từ chối" in title:
                raise ValueError(f"Trang từ chối truy cập: {url}")
            return browser.find_elements(By.CSS_SELECTOR, selector)

        WebDriverWait(driver, 15).until(ready, message=f"Không thấy dữ liệu: {url}")
        soup = BeautifulSoup(driver.page_source, "html.parser")
        sleep(1)
        return soup, site_url(driver.current_url)

    try:
        seen = set(rows)
        for original in urls:
            url = site_url(original)
            if product_id(url):
                links = [url]
            elif collect_listings and urlsplit(url).path.lower() == "/home/search/index.html":
                soup, resolved = load(url)
                links = list(product_links(soup, resolved))
                if not links:
                    raise ValueError(f"Không thấy link sản phẩm trên trang kết quả: {url}")
            else:
                raise ValueError(f"URL không hợp lệ cho chế độ hiện tại: {url}")
            for link in links:
                key = product_id(link)
                if key in seen:
                    print(f"Đã có sản phẩm {key}, bỏ qua")
                    continue
                soup, resolved = load(link)
                row = parse_product(soup, resolved)
                if row["product_id"] != key:
                    raise ValueError(f"Trang chuyển sang mã sản phẩm khác: {resolved}")
                rows[key] = row
                if on_product:
                    on_product(row)
                seen.add(key)
    finally:
        if driver is not None:
            driver.quit()


def read_csv(path):
    if not path.exists():
        return {}
    with path.open(encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        if not reader.fieldnames or not set(FIELDS).issubset(reader.fieldnames):
            raise ValueError(f"CSV thiếu các cột bắt buộc: {path}")
        rows = {}
        for row in reader:
            key = row["product_id"].strip()
            if not key or not row["product_name"].strip() or row["source"].strip().upper() != "BUUDIEN":
                raise ValueError(f"CSV chứa sản phẩm không hợp lệ: {path}")
            if key in rows:
                raise ValueError(f"CSV có mã sản phẩm trùng: {key}")
            rows[key] = {field: row[field] for field in FIELDS}
        return rows


def write_csv(output, rows):
    output.parent.mkdir(parents=True, exist_ok=True)
    with NamedTemporaryFile(
        mode="w", encoding="utf-8-sig", newline="", dir=output.parent, delete=False
    ) as tmp:
        name = Path(tmp.name)
        writer = csv.DictWriter(tmp, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows.values())
    try:
        name.replace(output)
    finally:
        name.unlink(missing_ok=True)


def sync_csv(path):
    subprocess.run(
        [sys.executable, "-X", "utf8", str(ROOT / "pipelines" / "sync_products.py"),
         "--source", "BUUDIEN", "--input", str(path.resolve())],
        check=True,
    )


class ProductBatch:
    def __init__(self, output, rows, sync=True):
        self.output = output
        self.rows = rows
        self.sync = sync
        self.pending = []

    def save_product(self, row):
        write_csv(self.output, self.rows)
        if self.sync:
            self.pending.append(row)
        print(f"Đã lưu CSV sản phẩm {row['product_id']}", flush=True)
        if len(self.pending) >= 10:
            self.flush()

    def flush(self):
        if not self.pending:
            return
        with NamedTemporaryFile(mode="w", encoding="utf-8-sig", newline="",
                                suffix=".csv", delete=False) as stream:
            temporary = Path(stream.name)
            writer = csv.DictWriter(stream, fieldnames=FIELDS)
            writer.writeheader()
            writer.writerows(self.pending)
        try:
            sync_csv(temporary)
        finally:
            temporary.unlink(missing_ok=True)
        print(f"Đã đồng bộ {len(self.pending)} sản phẩm vào database", flush=True)
        self.pending.clear()


def main():
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="backslashreplace")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--html", nargs="+", type=Path, help="File hoặc thư mục HTML chi tiết")
    parser.add_argument("--url", action="append", default=[], help="URL chi tiết hoặc trang kết quả")
    parser.add_argument("--urls-file", type=Path, help="Danh sách URL, mỗi dòng một link")
    parser.add_argument("--listing", action="store_true", help="Cho phép lấy link từ trang kết quả")
    parser.add_argument("--output", type=Path, default=CRAWLER_DIR / "ocop_output" / "products_buudien.csv")
    parser.add_argument("--no-sync", action="store_true", help="Chỉ xuất CSV, không đồng bộ DuckDB")
    args = parser.parse_args()
    if not (args.html or args.url or args.urls_file):
        args.urls_file = CRAWLER_DIR / "urls_buudien.txt"

    try:
        rows = read_csv(args.output)
        if rows and not args.no_sync:
            print("Đang đồng bộ CSV hiện có trước khi crawl...", flush=True)
            sync_csv(args.output)

        batch = ProductBatch(args.output, rows, sync=not args.no_sync)

        for path in args.html or []:
            files = sorted(path.glob("*.htm*")) if path.is_dir() else [path]
            if not files:
                raise ValueError(f"Không tìm thấy file HTML: {path}")
            for file in files:
                try:
                    row = parse_product(BeautifulSoup(file.read_bytes(), "html.parser"))
                except ValueError as exc:
                    raise ValueError(f"{file}: {exc}") from exc
                rows[row["product_id"]] = row
                batch.save_product(row)
        urls = args.url
        if args.urls_file:
            urls.extend(
                line.strip() for line in args.urls_file.read_text(encoding="utf-8-sig").splitlines()
                if line.strip() and not line.lstrip().startswith("#")
            )
        if urls:
            crawl_live(urls, args.listing, rows, batch.save_product)
        if not rows:
            raise ValueError("Không có sản phẩm để xuất")
        batch.flush()
    except Exception as exc:
        print(f"Dừng crawl: {exc}. Dữ liệu đã lưu trong CSV có thể đồng bộ lại khi chạy tiếp.", file=sys.stderr)
        return 1
    print(f"Đã xuất {len(rows)} sản phẩm: {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
