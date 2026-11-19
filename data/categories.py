"""Shared Vietnamese display taxonomy; source categories stay intact in storage."""
import unicodedata
import re


def category_key(value: str) -> str:
    return " ".join(unicodedata.normalize("NFC", value).casefold().split())


CATEGORY_ALIASES = {
    "Gia vị và chế biến": [
        "Food & Beverages > Staples & Cooking Essentials > Cooking Pastes & Seasoning Kits",
        "Food & Beverages > Staples & Cooking Essentials > Cooking Sauces",
        "Gia vị dạng lỏng", "Gia vị dạng nước", "Gia vị dạng bột", "Dầu ăn",
    ],
    "Thực phẩm đóng hộp và khô": [
        "Đồ khô sấy", "Thịt hộp", "Thực phẩm khô khác", "Đồ hộp",
        "Thực phẩm chay đóng hộp", "Rau củ, trái cây đóng hộp",
        "Thực phẩm khô dạng sợi",
    ],
    "Đồ ăn vặt": ["Food & Beverages > Snacks > Dried Snacks", "Bánh", "Kẹo",
                    "Chocolate", "Bánh kẹo khác", "Các loại đồ ăn vặt khác"],
    "Đồ uống": ["Trà", "Cà phê", "Các loại đồ uống dạng bột khác", "Nước hoa quả",
                 "Nước khoáng, nước tinh khiết", "Nước ngọt", "Sữa nước", "Sữa dạng bột"],
    "Rượu, bia và nước lên men": ["Đồ uống có cồn"],
    "Bột và nguyên liệu làm bánh": ["Food & Beverages > Baking > Baking Flours"],
    "Chăm sóc cơ thể": ["Beauty & Personal Care > Bath & Body Care > Body & Massage Oil",
                         "Dầu gội", "Dầu xả", "Dưỡng thể", "Mặt nạ", "Chăm sóc răng miệng",
                         "Chăm sóc tóc và da đầu", "Sản phẩm khử mùi"],
    "Sản phẩm hỗ trợ sức khỏe": [
        "Health > Nutrition & Wellness > Vitamins, Minerals & Wellness Supplements",
        "Thực phẩm chức năng thiên nhiên", "Thực phẩm chức năng sức khỏe",
        "Hỗ trợ cơ xương khớp", "Thực phẩm cho sắc đẹp",
    ],
    "Hương thơm và đồ thờ cúng": [
        "Đồ thờ cúng", "Home Supplies > Home Care Supplies > Home Fragrances",
        "Phụ kiện làm thơm phòng", "Hương, nhang", "Phụ kiện thờ cúng", "Bộ đồ thờ", "Bàn thờ",
    ],
    "Đồ dùng cho bé": [],
    "Sản phẩm thiên nhiên và khác": ["Sản phẩm thiên nhiên & Khác"],
    "Thực phẩm": ["Thực phẩm bảo quản mát", "Gạo", "Rau - Củ", "Thực phẩm dạng sợi",
                   "Thực phẩm tươi", "Thực phẩm ăn liền", "Ngũ cốc", "Đậu và các loại hạt",
                   "Thực phẩm bổ dưỡng", "Tổ yến", "Sữa chua", "Thực phẩm bảo quản đông lạnh"],
    "Thủy hải sản": ["Thủy sản khô", "Thủy sản đông lạnh", "Thủy sản tươi sống", "Cá hộp"],
    "Trái cây": ["Hoa quả tươi"],
    "Thảo dược": [],
    "Thủ công mỹ nghệ": ["Đồ gỗ - Mây tre đan", "Đồ đồng - Kim khí", "Thêu ren - Dệt may",
                          "Hoa khô - Đồ handmade", "Quà lưu niệm"],
    "Chưa phân loại": [],
}
CATEGORY_MAPPING = {
    category_key(alias): canonical
    for canonical, aliases in CATEGORY_ALIASES.items()
    for alias in [canonical, *aliases]
}


def canonical_category(value: object) -> str:
    """Only map reviewed categories; never infer a category from product names."""
    return CATEGORY_MAPPING.get(category_key(str(value)), "Chưa phân loại")


# Specific product names only: broad ingredient words such as "cá" or "dừa"
# also appear in names of sauces, sweets and cosmetics.
PRODUCT_TERMS = {
    "Gia vị và chế biến": ("nước mắm", "mắm tôm", "mắm tép", "muối tôm", "muối ớt",
                             "tương ớt", "tương cà", "nước tương", "dầu ăn", "hạt nêm"),
    "Đồ uống": ("trà", "chè uống", "cà phê", "nước ép", "nước khoáng", "sữa hạt"),
    "Rượu, bia và nước lên men": ("rượu", "bia"),
    "Đồ ăn vặt": ("bánh", "kẹo", "mứt", "ô mai", "socola", "chocolate"),
    "Thủy hải sản": ("cá khô", "tôm khô", "mực khô", "cá đông lạnh", "tôm đông lạnh"),
    "Thực phẩm": ("gạo", "bún", "phở", "miến", "mì", "yến sào"),
    "Chăm sóc cơ thể": ("dầu gội", "dầu xả", "sữa tắm", "xà phòng", "kem dưỡng"),
    "Hương thơm và đồ thờ cúng": ("nhang", "hương trầm", "nến thơm"),
}
PRODUCT_PATTERNS = {
    category: re.compile(r"(?<!\w)(?:" + "|".join(re.escape(term) for term in terms) + r")(?!\w)")
    for category, terms in PRODUCT_TERMS.items()
}


def infer_product_category(name: object, description: object = "") -> str:
    """Infer only from unambiguous product names or explicit descriptions."""
    def matches(text: str) -> set[str]:
        normalized = category_key(text)
        return {category for category, pattern in PRODUCT_PATTERNS.items() if pattern.search(normalized)}

    found = matches(name if isinstance(name, str) else "")
    if found:
        return next(iter(found)) if len(found) == 1 else "Chưa phân loại"

    # Avoid treating ingredients, usage instructions or recommendations as the
    # product itself. Only use a description that explicitly identifies it.
    text = description if isinstance(description, str) else ""
    identification = re.search(r"(?:^|[.!?]\s*)\s*(?:sản phẩm (?:này )?là|đây là)\s+([^.!?\n]+)",
                               text, re.IGNORECASE)
    found = matches(identification.group(1)) if identification else set()
    return next(iter(found)) if len(found) == 1 else "Chưa phân loại"


def product_category(category: object, name: object, description: object = "", source: object = "") -> str:
    """Keep reviewed source categories authoritative; infer only for Bưu điện."""
    canonical = canonical_category(category)
    if canonical != "Chưa phân loại" or str(source).strip().upper() != "BUUDIEN":
        return canonical
    return infer_product_category(name, description)
