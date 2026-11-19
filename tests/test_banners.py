import base64
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from PIL import Image

from src import banners


class BannerTests(unittest.TestCase):
    def test_project_banners_are_valid_local_images_with_alt(self):
        for name, alt in banners.BANNERS:
            with self.subTest(name=name):
                result = banners._load_banner((name, alt))
                self.assertIsNotNone(result)
                self.assertEqual(base64.b64decode(result[0]), (banners.BANNER_DIR / name).read_bytes())
                self.assertTrue(result[1])

    def test_missing_and_corrupt_images_are_skipped(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            (folder / 'broken.jpg').write_bytes(b'not an image')
            with patch.object(banners, 'BANNER_DIR', folder):
                self.assertIsNone(banners._load_banner(('missing.jpg', 'Missing')))
                self.assertIsNone(banners._load_banner(('broken.jpg', 'Broken')))
                Image.new('RGB', (2, 2)).save(folder / 'valid.jpg')
                self.assertIsNotNone(banners._load_banner(('valid.jpg', 'Valid')))
