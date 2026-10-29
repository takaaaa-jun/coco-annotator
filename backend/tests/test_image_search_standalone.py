"""Run directly with unittest; no Flask app or database is required."""
import importlib.util
import re
from pathlib import Path
import unittest


path = Path(__file__).resolve().parents[1] / 'webserver' / 'util' / 'image_search.py'
spec = importlib.util.spec_from_file_location('image_search', str(path))
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class ImageSearchTest(unittest.TestCase):
    def test_inclusive_zero_padded_range(self):
        self.assertEqual(module.image_search_query('00001-01000'),
                         {'__raw__': {'file_name': {'$gte': '00001.', '$lt': '01000/',
                          '$regex': r'^[0-9]{5}\.[^.]+$'}}})

    def test_single_id_range_and_spaces(self):
        self.assertEqual(module.image_search_query(' 00052 - 00052 '),
                         {'__raw__': {'file_name': {'$gte': '00052.', '$lt': '00052/',
                          '$regex': r'^[0-9]{5}\.[^.]+$'}}})

    def test_unpadded_input(self):
        self.assertEqual(module.image_search_query('1-1000'),
                         module.image_search_query('00001-01000'))

    def test_upper_boundary(self):
        self.assertEqual(module.image_search_query('99999-99999')['__raw__']['file_name']['$lt'],
                         '99999/')

    def test_filename_boundaries_and_extensions(self):
        query = module.image_search_query('00001-01000')['__raw__']['file_name']
        filenames = ['00000.jpg', '00001.JPG', '01000.jpg', '01000.png',
                     '01001.jpg', '000010.jpg', '01000-copy.jpg']
        selected = [name for name in filenames
                    if query['$gte'] <= name < query['$lt']
                    and re.search(query['$regex'], name)]
        self.assertEqual(selected, ['00001.JPG', '01000.jpg', '01000.png'])

    def test_filename_search_is_preserved(self):
        for text in ('00001', '00001.jpg', 'food-001.jpg'):
            self.assertEqual(module.image_search_query(text),
                             {'file_name__icontains': text})

    def test_empty_search(self):
        self.assertEqual(module.image_search_query(''), {})

    def test_invalid_ranges(self):
        for text in ('01000-00001', '00000-01000', '1-100000'):
            with self.assertRaises(ValueError):
                module.image_search_query(text)


if __name__ == '__main__':
    unittest.main()
