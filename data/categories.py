"""Shared Vietnamese display taxonomy; source categories stay intact in storage."""
import unicodedata


def category_key(value: str) -> str:
    return " ".join(unicodedata.normalize("NFC", value).casefold().split())


CATEGORY_ALIASES = {
    "Gia vị và chế biến": [
        "Food & Beverages > Staples & Cooking Essentials > Cooking Pastes & Seasoning Kits",
        "Food & Beverages > Staples & Cooking Essentials > Cooking Sauces",
    ],
    "Thực phẩm đóng hộp và khô": [],
    "Đồ ăn vặt": ["Food & Beverages > Snacks > Dried Snacks"],
    "Đồ uống": [],
    "Rượu, bia và nước lên men": [],
    "Bột và nguyên liệu làm bánh": ["Food & Beverages > Baking > Baking Flours"],
    "Chăm sóc cơ thể": ["Beauty & Personal Care > Bath & Body Care > Body & Massage Oil"],
    "Sản phẩm hỗ trợ sức khỏe": [
        "Health > Nutrition & Wellness > Vitamins, Minerals & Wellness Supplements",
    ],
    "Hương thơm và đồ thờ cúng": [
        "Đồ thờ cúng", "Home Supplies > Home Care Supplies > Home Fragrances",
    ],
    "Đồ dùng cho bé": [],
    "Sản phẩm thiên nhiên và khác": ["Sản phẩm thiên nhiên & Khác"],
    "Thực phẩm": [],
    "Thủy hải sản": [],
    "Trái cây": [],
    "Thảo dược": [],
    "Thủ công mỹ nghệ": [],
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
