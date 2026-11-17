import re
import unittest

from src.styles import APP_STYLES, COLOR_TOKENS
from src.product_cards import product_card_html


def contrast(first, second):
    def luminance(color):
        color = color.lstrip('#')
        if len(color) == 3:
            color = ''.join(c * 2 for c in color)
        rgb = [int(color[i:i + 2], 16) / 255 for i in (0, 2, 4)]
        rgb = [c / 12.92 if c <= .04045 else ((c + .055) / 1.055) ** 2.4 for c in rgb]
        return sum(c * weight for c, weight in zip(rgb, (.2126, .7152, .0722)))
    light, dark = sorted((luminance(first), luminance(second)), reverse=True)
    return (light + .05) / (dark + .05)


class StylesTests(unittest.TestCase):
    def test_text_sizes_and_explicit_color_pairs(self):
        tokens = dict(re.findall(r'(--[\w-]+):([^;]+);', COLOR_TOKENS))
        css = re.sub(r'var\((--[\w-]+)\)', lambda m: tokens.get(m[1], m[0]), APP_STYLES)
        for selector, body in re.findall(r'([^{}]+)\{([^{}]*)\}', css):
            with self.subTest(selector=selector.strip()):
                sizes = re.findall(r'font-size:\s*(\d+)px', body)
                minimum = 12 if any(chip in selector for chip in ('.star-chip', '.source-chip', '.account-role')) else 13
                self.assertTrue(all(int(size) >= minimum for size in sizes))
                foreground = re.search(r'(?:^|;)\s*color:\s*(#[\da-fA-F]{3,6})(?:;|!|\s|$)', body)
                background = re.search(r'(?:^|;)\s*background(?:-color)?:\s*(#[\da-fA-F]{3,6})(?:;|!|\s|$)', body)
                if foreground and background:
                    self.assertGreaterEqual(contrast(foreground[1], background[1]), 4.5)
        # Inherited text colors on the darkest shared and chat surfaces.
        for foreground in ('#183d2b', '#53675b', '#276e48', '#59665e', '#c62828'):
            self.assertGreaterEqual(contrast(foreground, '#eef6e9'), 4.5)
        self.assertGreaterEqual(contrast('#637185', '#f5f6f8'), 4.5)

    def test_missing_product_image_has_accessible_name(self):
        card = product_card_html({'product_name': 'Trà', 'image_url': ''})
        self.assertIn('role="img" aria-label="Chưa có ảnh sản phẩm"', card)
