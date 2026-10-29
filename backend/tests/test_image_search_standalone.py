"""Run directly with unittest; no Flask app or database is required."""
import importlib.util
from pathlib import Path
import unittest


path = Path(__file__).resolve().parents[1] / 'webserver' / 'util' / 'image_search.py'
spec = importlib.util.spec_from_file_location('image_search', str(path))
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class ImageSearchTest(unittest.TestCase):
    def test_inclusive_zero_padded_range(self):
        self.assertEqual(module.image_search_query('00001-01000'),
                         {'id__gte': 1, 'id__lte': 1000})

    def test_single_id_range_and_spaces(self):
        self.assertEqual(module.image_search_query(' 00052 - 00052 '),
                         {'id__gte': 52, 'id__lte': 52})

    def test_filename_search_is_preserved(self):
        for text in ('00001', '00001.jpg', 'food-001.jpg'):
            self.assertEqual(module.image_search_query(text),
                             {'file_name__icontains': text})

    def test_empty_search(self):
        self.assertEqual(module.image_search_query(''), {})

    def test_invalid_ranges(self):
        for text in ('01000-00001', '00000-01000', '1-9223372036854775808'):
            with self.assertRaises(ValueError):
                module.image_search_query(text)


if __name__ == '__main__':
    unittest.main()
