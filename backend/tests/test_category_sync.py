"""Pure tests plus opt-in real-MongoDB API tests using production models.

COCO_CATEGORY_TEST_DB=mongodb://127.0.0.1:27028/category_sync_tests
Never points at the application DB. Optional full exported taxonomy:
COCO_CATEGORY_TEST_BLUEPRINT=/path/to/coco-blueprint.json
"""
import collections
import collections.abc
import copy
import importlib.util
import json
import os
from pathlib import Path
import sys
import subprocess
import tempfile
import types
import unittest

# Legacy Flask/RESTPlus on modern Python: aliases removed from collections only.
for name in ('Mapping', 'MutableMapping', 'Sequence', 'Hashable', 'Iterable'):
    if not hasattr(collections, name):
        setattr(collections, name, getattr(collections.abc, name))

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def load(name, relative):
    spec = importlib.util.spec_from_file_location(name, str(ROOT / relative))
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


helper = load('sync_pure', 'webserver/util/category_sync.py')


def blueprint():
    data = {'schemaVersion': 1, 'taxonomy': 'check-annotator', 'datasetId': 2, 'datasetName': 'food_detection',
            'source': {'code': 'original-food-256-v1', 'version': '1'},
            'sourceCategories': [{'externalId': 1, 'name': 'rice'}, {'externalId': 20, 'name': 'udon noodle'},
                                 {'externalId': 21, 'name': 'tempura udon'}, {'externalId': 38, 'name': 'sausage'}],
            'targetCategories': [{'key': '5:rice', 'name': 'ご飯', 'description': '米を炊いた料理', 'parentKey': None},
                                 {'key': '5:udon', 'name': 'うどん', 'description': '', 'parentKey': None},
                                 {'key': '6:tempura-udon', 'name': '天ぷらうどん', 'description': '', 'parentKey': '5:udon'}],
            'mappings': [{'sourceExternalId': 1, 'targetKey': '5:rice'}, {'sourceExternalId': 20, 'targetKey': '5:udon'},
                         {'sourceExternalId': 21, 'targetKey': '6:tempura-udon'}]}
    return sign(data)


def sign(data):
    data.pop('version', None)
    data['version'] = helper.fingerprint(data)
    return data


class ValidationTests(unittest.TestCase):
    def test_valid_blueprint(self):
        sources, targets = helper.validate_blueprint(blueprint())
        self.assertEqual(set(sources), {1, 20, 21, 38})
        self.assertEqual(len(targets), 3)

    def test_checksum_and_duplicate_mapping(self):
        data = blueprint()
        data['mappings'].append(data['mappings'][0])
        with self.assertRaises(ValueError):
            helper.validate_blueprint(data)
        with self.assertRaises(ValueError):
            helper.validate_blueprint(sign(data))

    def test_missing_parent_and_unknown_target(self):
        for change in ('parent', 'target', 'source'):
            data = blueprint()
            if change == 'parent':
                data['targetCategories'][2]['parentKey'] = '5:missing'
            elif change == 'target':
                data['mappings'][0]['targetKey'] = '5:missing'
            else:
                data['mappings'][0]['sourceExternalId'] = 999
            with self.assertRaises(ValueError):
                helper.validate_blueprint(sign(data))


@unittest.skipUnless(os.environ.get('COCO_CATEGORY_TEST_DB'), 'Isolated MongoDB not configured')
class SyncApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        host = os.environ['COCO_CATEGORY_TEST_DB']
        if host not in ('mongodb://127.0.0.1:27028/category_sync_tests',
                        'mongodb://category-review-test-db/category_sync_tests'):
            raise RuntimeError('Refusing a non-test MongoDB target')
        from mongoengine import connect
        connect('category_sync_tests', host=host)
        from mongoengine.connection import get_db
        cls.db = get_db()
        # Import the actual production database package without starting the webserver.
        import database
        cls.models = database
        from flask import Flask, request
        from flask_login import LoginManager, UserMixin
        from flask_restplus import Api
        cls.app = Flask(__name__)
        cls.app.secret_key = 'category-sync-test-only'
        manager = LoginManager(cls.app)

        class User(UserMixin):
            username = 'reviewer'
            is_admin = False
            preferences = {}

            @property
            def datasets(self):
                return database.DatasetModel.objects(owner='reviewer')

            @property
            def images(self):
                return database.ImageModel.objects(dataset_id__in=self.datasets.distinct('id'))

            @property
            def annotations(self):
                return database.AnnotationModel.objects(image_id__in=self.images.distinct('id'))

            def can_edit(self, model):
                return request.headers.get('X-Test-Read-Only') != '1'

            def update(self, **kwargs):
                pass

        @manager.request_loader
        def loader(incoming):
            return User() if incoming.headers.get('X-Test-User') == '1' else None

        for package in ('_sync_test', '_sync_test.api', '_sync_test.util'):
            module = types.ModuleType(package)
            module.__path__ = []
            sys.modules[package] = module
        load('_sync_test.util.category_review', 'webserver/util/category_review.py')
        load('_sync_test.util.category_selection', 'webserver/util/category_selection.py')
        load('_sync_test.util.review_lock', 'webserver/util/review_lock.py')
        cls.bridge = load('_sync_test.api.category_review', 'webserver/api/category_review.py')
        # Import actual annotator routes; rendering/thumbnails are outside this test.
        util = sys.modules['_sync_test.util']
        util.profile = lambda f: f
        util.query_util = load('_sync_test.util.query_util', 'webserver/util/query_util.py')
        util.coco_util = types.SimpleNamespace()
        util.thumbnails = types.SimpleNamespace(generate_thumbnail=lambda image: None)
        cls.editor = load('_sync_test.api.annotator', 'webserver/api/annotator.py')
        cls.annotations = load('_sync_test.api.annotations', 'webserver/api/annotations.py')
        api = Api(cls.app, prefix='/api')
        api.add_namespace(cls.bridge.api)
        api.add_namespace(cls.editor.api)
        api.add_namespace(cls.annotations.api)

    def setUp(self):
        for collection in self.db.list_collection_names():
            self.db[collection].drop()
        self.data = blueprint()
        self.seed(self.data)
        self.client = self.app.test_client()
        self.headers = {'X-Test-User': '1', 'X-Category-Review': '1'}
        self.old_env = dict(os.environ)
        os.environ['CATEGORY_REVIEW_DATASET_ID'] = '2'

    def tearDown(self):
        for key in ('CATEGORY_REVIEW_DATASET_ID', 'CATEGORY_REVIEW_CATALOG'):
            if key in self.old_env:
                os.environ[key] = self.old_env[key]
            else:
                os.environ.pop(key, None)

    def seed(self, data):
        self.db.category_model.insert_many([{'_id': row['externalId'], 'name': row['name'], 'creator': 'legacy-{}'.format(row['externalId']),
                                             'deleted': False, 'metadata': {}} for row in data['sourceCategories']])
        self.db.dataset_model.insert_one({'_id': 2, 'name': data['datasetName'], 'owner': 'reviewer', 'users': [],
                                          'categories': [row['externalId'] for row in data['sourceCategories']], 'deleted': False})
        self.db.image_model.insert_one({'_id': 4001, 'dataset_id': 2, 'path': '/test/4001.jpg', 'file_name': '4001.jpg',
                                        'width': 640, 'height': 480, 'deleted': False, 'annotating': [], 'category_ids': [1]})
        for identifier in (90001, 90002):
            self.db.annotation_model.insert_one({'_id': identifier, 'image_id': 4001, 'dataset_id': 2, 'category_id': 1,
                'bbox': [10, 20, 100, 80], 'isbbox': True, 'deleted': False, 'creator': 'reviewer',
                'segmentation': [[10, 20, 110, 20, 110, 100]], 'metadata': {'custom': 'keep'}, 'paper_object': []})

    def create(self, name, marker):
        # Same implementation as the CLI, including imported-ID sequence correction.
        field = self.models.CategoryModel._fields['id']
        highest = self.db.category_model.find_one(sort=[('_id', -1)])
        self.db[field.collection_name].update_one({'_id': '{}.{}'.format(field.get_sequence_name(), field.name)},
            {'$max': {'next': highest['_id'] if highest else 0}}, upsert=True)
        category = self.models.CategoryModel(name=name, supercategory=marker.get('parentName', ''), metadata={'check_annotator': marker})
        category.save(force_insert=True)
        return category.id

    def activate(self):
        return helper.synchronize(self.db, self.data, self.create, apply=True)

    def payload(self):
        catalog = self.client.get('/api/category-review/catalog', headers=self.headers).get_json()
        image = self.client.get('/api/category-review/images/4001', headers=self.headers).get_json()
        box = next(b for b in image['boxes'] if b['id'] == 90001)
        target = next(m['targetCategoryId'] for m in catalog['mappings'] if m['sourceCategoryId'] == box['originalCategoryId'])
        return {'datasetId': 2, 'imageId': 4001, 'annotationId': 90001, 'expectedCategoryId': box['categoryId'],
                'expectedRevision': box['revision'], 'targetCategoryId': target, 'catalogVersion': catalog['version']}

    def put(self, payload):
        return self.client.put('/api/category-review/annotations/90001/category', json=payload, headers=self.headers)

    def test_preview_is_read_only(self):
        before = list(self.db.category_model.find())
        preview = helper.synchronize(self.db, self.data, self.create)
        self.assertEqual(preview['createCategories'], 3)
        self.assertEqual(list(self.db.category_model.find()), before)
        self.assertNotIn('category_review_catalog', self.db.dataset_model.find_one())

    def test_actual_sync_cli_preview_apply_and_repeat(self):
        with tempfile.TemporaryDirectory() as directory:
            data_path = Path(directory) / 'taxonomy.json'
            data_path.write_text(json.dumps(self.data, ensure_ascii=False), encoding='utf-8')
            wrapper = (
                'import collections,collections.abc,runpy; '
                '[setattr(collections,n,getattr(collections.abc,n)) for n in '
                '("Mapping","MutableMapping","Sequence","Hashable","Iterable") if not hasattr(collections,n)]; '
                'runpy.run_path(' + repr(str(ROOT / 'scripts/sync_categories.py')) + ',run_name="__main__")')
            environment = dict(os.environ, MONGODB_HOST=os.environ['COCO_CATEGORY_TEST_DB'], PYTHONIOENCODING='utf-8')
            before = list(self.db.annotation_model.find())
            for options in ([], ['--apply'], ['--apply']):
                result = subprocess.run([sys.executable, '-c', wrapper, '--data', str(data_path)] + options,
                                        env=environment, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                        universal_newlines=True, encoding='utf-8', timeout=60)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertEqual(self.db.category_model.count_documents({}), 7)
            self.assertEqual(list(self.db.annotation_model.find()), before)

    def test_activate_is_repeatable_and_legacy_ids_are_unchanged(self):
        before = list(self.db.annotation_model.find())
        catalog = self.activate()
        self.assertEqual(self.activate(), catalog)
        self.assertEqual(self.db.category_model.count_documents({}), 7)
        self.assertEqual(self.db.category_model.find_one({'_id': 1})['name'], 'rice')
        self.assertEqual(list(self.db.annotation_model.find()), before)
        self.assertTrue(set(self.db.dataset_model.find_one()['categories']).isdisjoint({1, 20, 21, 38}))

    def test_source_mismatch_refuses_before_writes(self):
        self.db.category_model.update_one({'_id': 20}, {'$set': {'name': 'wrong source'}})
        with self.assertRaises(ValueError):
            self.activate()
        self.assertEqual(self.db.category_model.count_documents({}), 4)
        self.assertNotIn('category_review_catalog', self.db.dataset_model.find_one())

    def test_wrong_dataset_and_editor_refuse(self):
        self.db.dataset_model.update_one({'_id': 2}, {'$set': {'name': 'wrong'}})
        with self.assertRaises(ValueError):
            self.activate()
        self.db.dataset_model.update_one({'_id': 2}, {'$set': {'name': 'food_detection'}})
        self.db.image_model.update_one({'_id': 4001}, {'$set': {'annotating': ['reviewer']}})
        with self.assertRaises(ValueError):
            self.activate()

    def test_unknown_dataset_category_is_not_silently_removed(self):
        self.db.dataset_model.update_one({'_id': 2}, {'$push': {'categories': 999}})
        with self.assertRaises(ValueError):
            self.activate()
        self.assertIn(999, self.db.dataset_model.find_one()['categories'])

    def test_explicit_source_binding_checks_names_and_uniqueness(self):
        self.db.category_model.update_one({'_id': 20}, {'$set': {'_temporary': True}})
        original = self.db.category_model.find_one({'_id': 20})
        original['_id'] = 200
        self.db.category_model.insert_one(original)
        self.db.category_model.delete_one({'_id': 20})
        self.db.dataset_model.update_one({'_id': 2}, {'$set': {'categories': [1, 200, 21, 38]}})
        with self.assertRaises(ValueError):
            helper.synchronize(self.db, self.data, self.create, {'20': 1}, apply=True)
        catalog = helper.synchronize(self.db, self.data, self.create, {'20': 200}, apply=True)
        self.assertIn(200, [row['sourceCategoryId'] for row in catalog['mappings']])

    def test_busy_sync_and_corrupt_target_are_rejected(self):
        self.db.dataset_model.update_one({'_id': 2}, {'$set': {'category_sync_lock': 'other'}})
        with self.assertRaises(ValueError):
            self.activate()
        self.db.dataset_model.update_one({'_id': 2}, {'$unset': {'category_sync_lock': ''}})
        catalog = self.activate()
        target = catalog['targetCategories'][0]['id']
        self.db.category_model.update_one({'_id': target}, {'$set': {'deleted': True}})
        self.assertEqual(self.client.get('/api/category-review/catalog', headers=self.headers).status_code, 409)
        response = self.client.post('/api/annotation/', json={'image_id': 4001, 'category_id': target}, headers=self.headers)
        self.assertEqual(response.status_code, 409)

    def test_failure_halfway_never_activates_half_catalog(self):
        calls = []
        def fail(name, marker):
            if calls:
                raise RuntimeError('simulated category creation failure')
            calls.append(name)
            return self.create(name, marker)
        with self.assertRaises(RuntimeError):
            helper.synchronize(self.db, self.data, fail, apply=True)
        dataset = self.db.dataset_model.find_one()
        self.assertNotIn('category_review_catalog', dataset)
        self.assertNotIn('category_sync_lock', dataset)
        self.activate()
        self.assertEqual(self.db.category_model.count_documents({}), 7)

    def test_exactly_one_box_changes_preserving_geometry_and_metadata(self):
        self.activate()
        before = list(self.db.annotation_model.find().sort('_id'))
        payload = self.payload()
        self.assertEqual(self.put(payload).status_code, 200)
        after = list(self.db.annotation_model.find().sort('_id'))
        self.assertEqual(after[1], before[1])
        for key in ('bbox', 'segmentation', 'paper_object'):
            self.assertEqual(after[0][key], before[0][key])
        self.assertEqual(after[0]['metadata']['custom'], 'keep')
        self.assertEqual(after[0]['metadata']['category_review']['original_category_name'], 'rice')
        self.assertEqual(self.put(payload).status_code, 409)

    def test_catalog_uses_new_categories_and_editor_retains_old_boxes(self):
        self.activate()
        response = self.client.get('/api/annotator/data/4001', headers=self.headers)
        self.assertEqual(response.status_code, 200)
        categories = response.get_json()['categories']
        legacy = next(c for c in categories if c['id'] == 1)
        self.assertFalse(legacy['selectable'])
        self.assertEqual(len(legacy['annotations']), 2)
        self.assertEqual({c['name'] for c in categories if c['selectable']}, {'ご飯', 'うどん', '天ぷらうどん'})

    def test_unmapped_and_wrong_target_cannot_be_replaced(self):
        self.activate()
        payload = self.payload()
        payload['targetCategoryId'] = next(c['id'] for c in self.client.get('/api/category-review/catalog', headers=self.headers).get_json()['targetCategories'] if c['name'] == 'うどん')
        self.assertEqual(self.put(payload).status_code, 400)
        self.db.annotation_model.update_one({'_id': 90001}, {'$set': {'category_id': 38}})
        response = self.client.get('/api/category-review/images/4001', headers=self.headers)
        self.assertEqual(response.status_code, 200)
        payload.update(expectedCategoryId=38, expectedRevision=next(b['revision'] for b in response.get_json()['boxes'] if b['id'] == 90001))
        self.assertEqual(self.put(payload).status_code, 400)

    def test_legacy_creation_is_rejected_but_new_category_allowed(self):
        catalog = self.activate()
        for route in ('/api/annotation/', '/api/annotation/90001'):
            method = self.client.post if route.endswith('/') else self.client.put
            response = method(route, json={'image_id': 4001, 'category_id': 1}, headers=self.headers)
            self.assertEqual(response.status_code, 409)
        target_id = catalog['targetCategories'][0]['id']
        response = self.client.post('/api/annotation/', json={'image_id': 4001, 'category_id': target_id}, headers=self.headers)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()['category_id'], target_id)

    def test_stale_editor_catalog_is_rejected(self):
        self.activate()
        response = self.client.post('/api/annotator/data', json={'image': {'id': 4001}, 'dataset': {}}, headers=self.headers)
        self.assertEqual(response.status_code, 409)

    def test_editor_saves_json_and_legacy_string_body(self):
        self.activate()
        loaded = self.client.get('/api/annotator/data/4001', headers=self.headers).get_json()
        payload = {'image': {'id': 4001, 'category_ids': [1], 'metadata': {}},
                   'dataset': loaded['dataset'], 'categories': []}
        before = list(self.db.annotation_model.find())
        for content_type in ('application/json', 'application/x-www-form-urlencoded', 'text/plain'):
            response = self.client.post('/api/annotator/data', data=json.dumps(payload),
                                        content_type=content_type, headers=self.headers)
            self.assertEqual(response.status_code, 200, response.get_json())
        self.assertEqual(list(self.db.annotation_model.find()), before)

    def test_editor_legacy_body_rejects_cross_origin_and_invalid_json(self):
        self.activate()
        before = list(self.db.annotation_model.find())
        response = self.client.post('/api/annotator/data', data='{"image":{"id":4001}}',
                                    content_type='text/plain', headers=dict(self.headers, Origin='https://other.example'))
        self.assertEqual(response.status_code, 403)
        for raw in ('not json', '[]', 'null'):
            response = self.client.post('/api/annotator/data', data=raw, content_type='text/plain', headers=self.headers)
            self.assertEqual(response.status_code, 400)
        self.assertEqual(list(self.db.annotation_model.find()), before)

    def test_review_endpoint_still_requires_json_content_type(self):
        self.activate()
        payload = self.payload()
        response = self.client.put('/api/category-review/annotations/90001/category', data=json.dumps(payload),
                                   content_type='application/x-www-form-urlencoded', headers=self.headers)
        self.assertEqual(response.status_code, 400)

    def test_permissions_origin_and_stale_geometry(self):
        self.activate()
        self.assertEqual(self.client.get('/api/category-review/catalog').status_code, 401)
        payload = self.payload()
        for headers in (dict(self.headers, **{'X-Test-Read-Only': '1'}), dict(self.headers, Origin='https://other.example')):
            self.assertEqual(self.client.put('/api/category-review/annotations/90001/category', json=payload, headers=headers).status_code, 403)
        self.db.annotation_model.update_one({'_id': 90001}, {'$set': {'bbox': [0, 0, 30, 30]}})
        self.assertEqual(self.put(payload).status_code, 409)

    def test_managed_identity_and_enabled_categories_are_verified(self):
        catalog = self.activate()
        target = catalog['targetCategories'][0]['id']
        self.db.category_model.update_one({'_id': target}, {'$set': {'metadata.check_annotator.key': 'wrong'}})
        self.assertEqual(self.client.get('/api/category-review/catalog', headers=self.headers).status_code, 409)

    def test_managed_dataset_never_falls_back_to_old_catalog(self):
        self.activate()
        os.environ.pop('CATEGORY_REVIEW_DATASET_ID')
        os.environ['CATEGORY_REVIEW_CATALOG'] = str(ROOT / 'config/category-review.example.json')
        self.assertNotEqual(self.client.get('/api/category-review/catalog', headers=self.headers).status_code, 200)

    @unittest.skipUnless(os.environ.get('COCO_CATEGORY_TEST_BLUEPRINT'), 'Full MySQL export not provided')
    def test_full_exported_taxonomy_and_each_mapping(self):
        for collection in self.db.list_collection_names():
            self.db[collection].drop()
        self.data = json.loads(Path(os.environ['COCO_CATEGORY_TEST_BLUEPRINT']).read_text(encoding='utf-8'))
        self.seed(self.data)
        self.activate()
        catalog = self.client.get('/api/category-review/catalog', headers=self.headers).get_json()
        self.assertEqual(len(catalog['sourceCategories']), 256)
        self.assertEqual(len(catalog['mappings']), 42)
        for mapping in catalog['mappings']:
            self.db.annotation_model.update_one({'_id': 90001}, {'$set': {'category_id': mapping['sourceCategoryId'], 'metadata': {'custom': 'keep'}}})
            payload = self.payload()
            self.assertEqual(payload['targetCategoryId'], mapping['targetCategoryId'])
            self.assertEqual(self.put(payload).status_code, 200)
        self.assertEqual(self.db.annotation_model.find_one({'_id': 90002})['category_id'], 1)

    @unittest.skipUnless(os.environ.get('COCO_CATEGORY_TEST_BLUEPRINT'), 'Full MySQL export not provided')
    def test_real_255_category_layout_and_omelet_choice(self):
        for collection in self.db.list_collection_names():
            self.db[collection].drop()
        self.data = json.loads(Path(os.environ['COCO_CATEGORY_TEST_BLUEPRINT']).read_text(encoding='utf-8'))
        self.seed(self.data)
        self.db.category_model.drop()
        by_name = {}
        for row in self.data['sourceCategories']:
            actual_name = ' '.join(row['name'].split())
            if actual_name not in by_name:
                by_name[actual_name] = len(by_name) + 1
                self.db.category_model.insert_one({'_id': by_name[actual_name], 'name': actual_name,
                    'creator': 'system', 'deleted': False, 'metadata': {}})
        self.db.dataset_model.update_one({'_id': 2}, {'$set': {'categories': list(by_name.values())}})
        legacy_before = list(self.db.category_model.find().sort('_id'))
        self.assertEqual(len(legacy_before), 255)
        self.assertEqual(self.db.category_model.find_one({'_id': 67})['name'], 'egg sunny-side up')
        self.assertEqual(self.db.category_model.find_one({'_id': 165})['name'],
                         'dish consisting of stir-fried potato, eggplant and green pepper')
        preview = helper.synchronize(self.db, self.data, self.create)
        self.assertEqual(preview['actualSourceCategories'], 255)
        self.assertEqual(preview['replacementChoices'], 42)
        self.assertEqual(preview['mappings'], 41)
        self.assertEqual(preview['ambiguousMappings'], 1)
        self.activate()
        self.assertEqual(list(self.db.category_model.find({'_id': {'$lte': 255}}).sort('_id')), legacy_before)
        response = self.client.get('/api/category-review/catalog', headers=self.headers)
        self.assertEqual(response.status_code, 200)
        catalog = response.get_json()
        source166 = next(row for row in catalog['sourceCategories'] if 166 in row['externalIds'])
        self.assertEqual(source166['id'], 165)
        mapping = next(row for row in catalog['mappings'] if row['sourceCategoryId'] == by_name['omelet'])
        self.assertTrue(mapping['requiresChoice'])
        names = {row['id']: row['name'] for row in catalog['targetCategories']}
        self.assertEqual({names[key] for key in mapping['candidateTargetCategoryIds']}, {'オムレツ', 'だし巻き卵'})
        self.db.annotation_model.update_one({'_id': 90001}, {'$set': {'category_id': by_name['omelet'], 'metadata': {'custom': 'keep'}}})
        payload = self.payload()
        self.assertEqual(self.put(payload).status_code, 400)  # Cached/old clients may not pick the first candidate.
        for target in mapping['candidateTargetCategoryIds']:
            self.db.annotation_model.update_one({'_id': 90001}, {'$set': {'category_id': by_name['omelet'], 'metadata': {'custom': 'keep'}}})
            payload = self.payload()
            payload.update(targetCategoryId=target, choiceConfirmed=True)
            self.assertEqual(self.put(payload).status_code, 200)
            saved = self.db.annotation_model.find_one({'_id': 90001})
            self.assertEqual(saved['metadata']['category_review']['original_external_category_ids'], [40, 67])
            self.assertEqual(saved['bbox'], [10, 20, 100, 80])
        # Exercise every actual COCO source and every choice in the exact deployed layout.
        for resolved in catalog['mappings']:
            for target in resolved['candidateTargetCategoryIds']:
                self.db.annotation_model.update_one({'_id': 90001}, {'$set': {
                    'category_id': resolved['sourceCategoryId'], 'metadata': {'custom': 'keep'}}})
                payload = self.payload()
                payload.update(targetCategoryId=target, choiceConfirmed=resolved['requiresChoice'])
                self.assertEqual(self.put(payload).status_code, 200)
                self.assertEqual(self.db.annotation_model.find_one({'_id': 90001})['bbox'], [10, 20, 100, 80])
        self.assertEqual(self.db.annotation_model.find_one({'_id': 90002})['category_id'], 1)
        self.assertEqual(self.activate()['mappings'], catalog['mappings'])

    def test_ambiguous_duplicate_name_without_matching_id_is_rejected(self):
        self.db.category_model.insert_one({'_id': 300, 'name': 'udon noodle', 'creator': 'other', 'deleted': False})
        self.db.category_model.update_one({'_id': 20}, {'$set': {'_id_unrelated': True}})
        self.db.category_model.update_one({'_id': 20}, {'$set': {'name': 'wrong'}})
        self.db.category_model.insert_one({'_id': 301, 'name': 'udon noodle', 'creator': 'another', 'deleted': False})
        self.db.dataset_model.update_one({'_id': 2}, {'$set': {'categories': [1, 20, 21, 38, 300, 301]}})
        with self.assertRaises(ValueError):
            self.activate()

    def test_whitespace_only_match_must_still_be_unique(self):
        self.db.category_model.update_one({'_id': 20}, {'$set': {'name': 'wrong'}})
        for identifier, name in ((300, 'udon   noodle'), (301, 'udon noodle ')):
            self.db.category_model.insert_one({'_id': identifier, 'name': name, 'creator': 'other', 'deleted': False})
        self.db.dataset_model.update_one({'_id': 2}, {'$set': {'categories': [1, 20, 21, 38, 300, 301]}})
        with self.assertRaises(ValueError):
            self.activate()


if __name__ == '__main__':
    unittest.main(verbosity=2)
