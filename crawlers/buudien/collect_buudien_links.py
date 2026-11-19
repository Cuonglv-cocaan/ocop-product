import argparse
import time
from pathlib import Path
from urllib.parse import parse_qs, urljoin, urlsplit

import requests
from bs4 import BeautifulSoup

BASE = "https://buudien.vn"
SEARCH_URL = f"{BASE}/home/Search/index.html"
OUTPUT = Path(__file__).resolve().parent / "urls_buudien.txt"


def get_product_id(url):
    parts = urlsplit(url)
    if parts.hostname != "buudien.vn":
        return None
    if parts.path.lower() != "/home/goods/index.html":
        return None
    goods_id = parse_qs(parts.query).get("goods_id", [""])[0]
    return goods_id if goods_id.isascii() and goods_id.isdigit() else None


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--start", type=int, default=2)
    parser.add_argument("--end", type=int, default=143)
    args = parser.parse_args()

    if not 1 <= args.start <= args.end:
        parser.error("Cần 1 <= --start <= --end")

    links = {}
    if OUTPUT.exists():
        for line in OUTPUT.read_text(encoding="utf-8-sig").splitlines():
            url = line.strip()
            if goods_id := get_product_id(url):
                links.setdefault(goods_id, url)

    with requests.Session() as session:
        for page in range(args.start, args.end + 1):
            try:
                response = session.get(
                    SEARCH_URL,
                    params={"keyword": "OCOP", "page": page},
                    timeout=20,
                )
                response.raise_for_status()
            except requests.RequestException as exc:
                parser.exit(1, f"Dừng ở trang {page}: {exc}\n")

            soup = BeautifulSoup(response.content, "html.parser")
            page_ids = set()
            for tag in soup.select('a[href*="goods_id="]'):
                url = urljoin(response.url, tag["href"])
                if goods_id := get_product_id(url):
                    page_ids.add(goods_id)

            if not page_ids:
                parser.exit(1, f"Dừng ở trang {page}: không thấy link sản phẩm.\n")

            before = len(links)
            for goods_id in sorted(page_ids, key=int):
                links.setdefault(
                    goods_id, f"{BASE}/home/Goods/index.html?goods_id={goods_id}"
                )

            temp = OUTPUT.with_suffix(".tmp")
            temp.write_text("\n".join(links.values()) + "\n", encoding="utf-8")
            temp.replace(OUTPUT)
            print(f"Trang {page}: +{len(links) - before} link mới | Tổng {len(links)}")
            time.sleep(1)


if __name__ == "__main__":
    main()
