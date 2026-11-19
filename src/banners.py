"""Read optional homepage banners from files included in the project."""
import base64
from io import BytesIO
from pathlib import Path

import streamlit as st
from PIL import Image, UnidentifiedImageError


BANNER_DIR = Path(__file__).resolve().parents[1] / 'data' / 'banners'
BANNERS = (
    ('banner_footer1_549f9.jpg', 'Người làm nghề bên các sản phẩm mây tre đan'),
    ('banner_footer2_01611.jpg', 'Người dân phơi cá khô'),
    ('banner_footer3_42c65.jpg', 'Người dân chăm sóc hoa trong vườn'),
)


def _load_banner(item):
    name, alt = item
    try:
        content = (BANNER_DIR / name).read_bytes()
        with Image.open(BytesIO(content)) as image:
            image.verify()
            if image.format != 'JPEG':
                return None
        return base64.b64encode(content).decode('ascii'), alt
    except (OSError, ValueError, UnidentifiedImageError):
        return None


@st.cache_data(show_spinner=False)
def load_banners():
    return [banner for item in BANNERS if (banner := _load_banner(item))]
