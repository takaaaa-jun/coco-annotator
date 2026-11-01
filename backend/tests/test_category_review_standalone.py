"""Run directly. Optional DB tests require a dedicated throwaway MongoDB host."""
import copy
import importlib.util
import json
import os
from pathlib import Path
import sys
import tempfile
import types
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def load(name, relative):
    spec = importlib.util.spec_from_file_location(name, str(ROOT / relative))
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


helper = load('category_review_pure', 'webserver/util/category_review.py')
CATALOG = {
    'version': 'test-1', 'datasetId': 2,
    'sourceCategories': [{'id': 1, 'name': 'Original A'}, {'id': 3, 'name': 'Original C'}],
    'targetCategories': [{'id': 101, 'name': 'Test 1'}, {'id': 102, 'name': 'Test 2'}],
    'mappings': [{'sourceCategoryId': 1, 'targetCategoryId': 101}],
}
BOX = {'_id': 90001, 'image_id': 4001, 'dataset_id': 2, 'category_id': 1,
       'bbox': [10, 20, 100, 80], 'isbbox': True, 'deleted': False,
       'metadata': {'custom': 'keep'}, 'segmentation': [[10, 20, 110, 20, 110, 100, 10, 100]],
       'paper_object': [], 'keypoints': [], 'creator': 'reviewer'}


class PureTests(unittest.TestCase):
    def test_mapping_references_and_ambiguity(self):
        for change in ({'datasetId': True}, {'datasetId': 0}, {'version': ''},
                       {'mappings': [{'sourceCategoryId': 1, 'targetCategoryId': 999}]},
                       {'mappings': CATALOG['mappings'] * 2},
                       {'sourceCategories': CATALOG['sourceCategories'] * 2}):
            with self.assertRaises(ValueError):
                helper.validate_catalog(dict(CATALOG, **change))

    def test_content_changes_revision_even_if_version_is_unchanged(self):
        before = helper.validate_catalog(CATALOG)['version']
        changed = copy.deepcopy(CATALOG)
        changed['targetCategories'][0]['aliases'] = ['bread']
        self.assertNotEqual(before, helper.validate_catalog(changed)['version'])

    def test_provenance_and_geometry_are_preserved(self):
        before = copy.deepcopy(BOX)
        metadata = helper.replacement_metadata(BOX, CATALOG, 101, 'reviewer', 'now')
        self.assertEqual(BOX, before)
        self.assertEqual(metadata['custom'], 'keep')
        self.assertEqual(metadata['category_review']['original_category_id'], 1)
        self.assertEqual(helper.original_category(dict(BOX, category_id=101, metadata=metadata)), 1)

    def test_non_box_and_unmapped_replacements_are_rejected(self):
        for box, target in ((dict(BOX, isbbox=False), 101), (BOX, 102), (dict(BOX, category_id=3), 101)):
            with self.assertRaises(ValueError):
                helper.replacement_metadata(box, CATALOG, target, 'reviewer', 'now')

    def test_invalid_geometry_and_revisions(self):
        self.assertFalse(helper.is_box(dict(BOX, bbox=[0, 0, 0, 20])))
        self.assertFalse(helper.is_box(dict(BOX, bbox=[0, 0, float('nan'), 20])))
        self.assertNotEqual(helper.fingerprint(BOX), helper.fingerprint(dict(BOX, bbox=[0, 0, 1, 2])))


@unittest.skipUnless(os.environ.get('CATEGORY_REVIEW_TEST_DB'), 'Dedicated MongoDB not configured')
class ApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        host = os.environ['CATEGORY_REVIEW_TEST_DB']
        if not host.startswith('mongodb://category-review-test-db/'):
            raise RuntimeError('Refusing to run against a non-test MongoDB host')
        from mongoengine import connect
        connect('category_review_tests', host=host)
        from database import AnnotationModel, CategoryModel, DatasetModel, ImageModel
        from flask import Flask, request
        from flask_login import LoginManager, UserMixin, login_required
        from flask_restplus import Api, Resource
        cls.models = (AnnotationModel, CategoryModel, DatasetModel, ImageModel)
        for package in ('_review_test', '_review_test.util', '_review_test.api'):
            module = types.ModuleType(package)
            module.__path__ = []
            sys.modules[package] = module
        load('_review_test.util.category_review', 'webserver/util/category_review.py')
        locks = load('_review_test.util.review_lock', 'webserver/util/review_lock.py')
        bridge = load('_review_test.api.category_review', 'webserver/api/category_review.py')
        cls.app = Flask(__name__)
        cls.app.secret_key = 'isolated-category-review-tests'
        manager = LoginManager(cls.app)

        class User(UserMixin):
            username = 'reviewer'
            is_admin = False

            @property
            def datasets(self):
                return DatasetModel.objects(owner='reviewer')

            @property
            def images(self):
                return ImageModel.objects(dataset_id__in=self.datasets.distinct('id'))

            def can_edit(self, dataset):
                return request.headers.get('X-Test-Read-Only') != '1'

        @manager.request_loader
        def user_loader(incoming):
            return User() if incoming.headers.get('X-Test-User') == '1' else None

        api = Api(cls.app, prefix='/api')
        api.add_namespace(bridge.api)

        @api.route('/test-editor-save')
        class EditorSave(Resource):
            @login_required
            @locks.image_write_lock()
            def post(self):
                return {'saved': True}

    def setUp(self):
        Annotation, Category, Dataset, Image = self.models
        for model in self.models:
            model.drop_collection()
        Category._get_collection().insert_many([dict(row, _id=row['id'], deleted=False, creator='reviewer') for row in CATALOG['sourceCategories'] + CATALOG['targetCategories']])
        Dataset._get_collection().insert_one({'_id': 2, 'name': 'test', 'owner': 'reviewer', 'users': [], 'categories': [1, 3, 101, 102], 'deleted': False})
        Image._get_collection().insert_one({'_id': 4001, 'dataset_id': 2, 'file_name': '04001.jpg', 'path': '/test/04001.jpg', 'width': 640, 'height': 480, 'deleted': False, 'annotating': [], 'category_ids': [1]})
        Annotation._get_collection().insert_many([copy.deepcopy(BOX), dict(copy.deepcopy(BOX), _id=90002)])
        self.temp = tempfile.TemporaryDirectory()
        self.path = str(Path(self.temp.name) / 'catalog.json')
        with open(self.path, 'w') as handle:
            json.dump(CATALOG, handle)
        os.environ['CATEGORY_REVIEW_CATALOG'] = self.path
        self.client = self.app.test_client()
        self.headers = {'X-Test-User': '1', 'X-Category-Review': '1'}

    def tearDown(self):
        self.temp.cleanup()

    def payload(self):
        catalog = json.loads(self.client.get('/api/category-review/catalog', headers=self.headers).data)
        image = json.loads(self.client.get('/api/category-review/images/4001', headers=self.headers).data)
        box = image['boxes'][0]
        return {'datasetId': 2, 'imageId': 4001, 'annotationId': box['id'], 'expectedCategoryId': 1,
                'expectedRevision': box['revision'], 'targetCategoryId': 101, 'catalogVersion': catalog['version']}

    def put(self, data, headers=None):
        return self.client.put('/api/category-review/annotations/90001/category', json=data, headers=headers or self.headers)

    def test_authentication_and_unconfigured_catalog(self):
        self.assertEqual(self.client.get('/api/category-review/catalog').status_code, 401)
        del os.environ['CATEGORY_REVIEW_CATALOG']
        self.assertEqual(self.client.get('/api/category-review/catalog', headers=self.headers).status_code, 503)

    def test_only_one_box_changes_and_stale_retry_is_rejected(self):
        data = self.payload()
        self.assertEqual(self.put(data).status_code, 200)
        collection = self.models[0]._get_collection()
        first, second = collection.find_one({'_id': 90001}), collection.find_one({'_id': 90002})
        self.assertEqual(first['category_id'], 101)
        self.assertEqual(first['bbox'], BOX['bbox'])
        self.assertEqual(first['segmentation'], BOX['segmentation'])
        self.assertEqual(first['metadata']['category_review']['original_category_id'], 1)
        self.assertEqual(second, dict(BOX, _id=90002))
        self.assertEqual(self.put(data).status_code, 409)
        image = self.models[3]._get_collection().find_one({'_id': 4001})
        self.assertEqual(set(image['category_ids']), {1, 101})
        self.assertNotIn('category_review_lock', image)

    def test_geometry_conflict(self):
        data = self.payload()
        self.models[0]._get_collection().update_one({'_id': 90001}, {'$set': {'bbox': [0, 0, 30, 30]}})
        self.assertEqual(self.put(data).status_code, 409)

    def test_mapping_change_same_version(self):
        data = self.payload()
        changed = copy.deepcopy(CATALOG)
        changed['mappings'][0]['targetCategoryId'] = 102
        with open(self.path, 'w') as handle:
            json.dump(changed, handle)
        self.assertEqual(self.put(data).status_code, 409)

    def test_permissions_cross_origin_and_wrong_target(self):
        data = self.payload()
        self.assertEqual(self.put(data, dict(self.headers, **{'X-Test-Read-Only': '1'})).status_code, 403)
        self.assertEqual(self.put(data, dict(self.headers, Origin='https://other.example')).status_code, 403)
        self.assertEqual(self.put(dict(data, targetCategoryId=102)).status_code, 400)

    def test_active_editor_and_busy_lock_are_rejected(self):
        data = self.payload()
        image = self.models[3]._get_collection()
        image.update_one({'_id': 4001}, {'$set': {'annotating': ['reviewer']}})
        self.assertEqual(self.put(data).status_code, 409)
        image.update_one({'_id': 4001}, {'$set': {'annotating': [], 'category_review_lock': {'token': 'other'}}})
        self.assertEqual(self.put(data).status_code, 409)

    def test_old_editor_cannot_overwrite_reviewed_data(self):
        self.assertEqual(self.put(self.payload()).status_code, 200)
        response = self.client.post('/api/test-editor-save', json={'image': {'id': 4001}}, headers=self.headers)
        self.assertEqual(response.status_code, 409)
        response = self.client.post('/api/test-editor-save', json={'image': {'id': 4001, 'category_review_revision': 1}}, headers=self.headers)
        self.assertEqual(response.status_code, 200)


if __name__ == '__main__':
    unittest.main(verbosity=2)
