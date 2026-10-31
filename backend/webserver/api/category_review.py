"""Same-origin, session-authenticated category review; no mock data reaches MongoDB."""
import datetime
import json
import os
from urllib.parse import urlsplit

from flask import request
from flask_login import current_user, login_required
from flask_restplus import Namespace, Resource

from database import AnnotationModel, CategoryModel, ImageModel
from ..util.category_review import (
    fingerprint, is_box, positive_id, replacement_metadata, serialize_box, validate_catalog,
)
from ..util.review_lock import image_write_lock

api = Namespace('category-review', description='Box-by-box category review')


class ReviewError(Exception):
    def __init__(self, message, status):
        self.message, self.status = message, status


def failure(error):
    return {'message': str(error.message if isinstance(error, ReviewError) else error)}, error.status if isinstance(error, ReviewError) else 400


def load_catalog():
    path = os.environ.get('CATEGORY_REVIEW_CATALOG')
    if not path:
        raise ReviewError('カテゴリ対応表が未設定です。管理者がCATEGORY_REVIEW_CATALOGを設定してください。', 503)
    try:
        if os.path.getsize(path) > 2000000:
            raise ValueError('対応表は2MB以下にしてください。')
        with open(path, encoding='utf-8') as handle:
            catalog = validate_catalog(json.load(handle))
    except (OSError, ValueError, TypeError) as error:
        raise ReviewError('カテゴリ対応表を読み込めません: {}'.format(error), 503)
    dataset = current_user.datasets.filter(id=catalog['datasetId'], deleted=False).first()
    if dataset is None:
        raise ReviewError('対象データセットへのアクセス権がありません。', 403)
    # Both sides of the mapping must be real, enabled database categories.
    all_ids = {row['id'] for row in catalog['sourceCategories'] + catalog['targetCategories']}
    actual = {category.id: category for category in CategoryModel.objects(id__in=list(all_ids), deleted=False)}
    if not all_ids.issubset(set(dataset.categories)) or set(actual) != all_ids:
        raise ReviewError('対応表のカテゴリがDBに存在しないか、データセットで有効ではありません。', 409)
    for row in catalog['sourceCategories'] + catalog['targetCategories']:
        if actual[row['id']].name != row['name']:
            raise ReviewError('対応表とDBのカテゴリ名が一致しません（ID {}）。'.format(row['id']), 409)
    return catalog, dataset


def permitted_image(image_id, dataset):
    image = ImageModel.objects(id=image_id, dataset_id=dataset.id, deleted=False).first()
    if image is None:
        raise ReviewError('対象データセットに画像がありません。', 404)
    return image


@api.route('/catalog')
class Catalog(Resource):
    @login_required
    def get(self):
        try:
            catalog, _ = load_catalog()
            return catalog
        except (ReviewError, ValueError) as error:
            return failure(error)


@api.route('/images/<int:image_id>')
class ImageReview(Resource):
    @login_required
    def get(self, image_id):
        try:
            _, dataset = load_catalog()
            image = permitted_image(image_id, dataset)
            documents = AnnotationModel._get_collection().find({'image_id': image.id, 'deleted': False})
            return {'datasetId': dataset.id, 'imageId': image.id, 'fileName': image.file_name,
                    'width': image.width, 'height': image.height,
                    'boxes': [serialize_box(doc) for doc in documents if is_box(doc)]}
        except (ReviewError, ValueError) as error:
            return failure(error)


@api.route('/annotations/<int:annotation_id>/category')
class ReplaceCategory(Resource):
    @login_required
    @image_write_lock(review=True)
    def put(self, annotation_id):
        try:
            # Require a custom header and same-origin request. Do not allow a cross-origin form write.
            origin = request.headers.get('Origin')
            if request.headers.get('X-Category-Review') != '1' or (origin and urlsplit(origin).netloc != request.host):
                raise ReviewError('同じホストのカテゴリ確認画面から実行してください。', 403)
            data = request.get_json(silent=True)
            if not isinstance(data, dict):
                raise ValueError('JSONオブジェクトが必要です。')
            for key in ('datasetId', 'imageId', 'annotationId', 'expectedCategoryId', 'targetCategoryId'):
                positive_id(data.get(key))
            if annotation_id != data['annotationId']:
                raise ValueError('URLとボックスIDが一致しません。')
            catalog, dataset = load_catalog()
            if not current_user.can_edit(dataset):
                raise ReviewError('データセットの編集権限がありません。', 403)
            if data['datasetId'] != dataset.id or data.get('catalogVersion') != catalog['version']:
                raise ReviewError('対応表が変更されています。再読み込みしてください。', 409)
            image = permitted_image(data['imageId'], dataset)
            if image.annotating:
                raise ReviewError('画像編集中のユーザーがいます。編集内容を保存して画像を閉じてから再実行してください。', 409)
            collection = AnnotationModel._get_collection()
            document = collection.find_one({'_id': annotation_id, 'image_id': image.id, 'deleted': False})
            if document is None:
                raise ReviewError('対象ボックスがありません。', 404)
            if data.get('expectedRevision') != fingerprint(document) or data['expectedCategoryId'] != document['category_id']:
                raise ReviewError('ボックスが更新されています。再読み込みして確認してください。', 409)
            metadata = replacement_metadata(document, catalog, data['targetCategoryId'], current_user.username, datetime.datetime.utcnow().isoformat() + 'Z')
            # Atomic compare-and-set on the exact persisted snapshot. Geometry is never written here.
            image.update(inc__category_review_revision=1)
            changed = collection.update_one(document, {'$set': {'category_id': data['targetCategoryId'], 'metadata': metadata}})
            if changed.modified_count != 1:
                raise ReviewError('別の操作でボックスが更新されました。再読み込みしてください。', 409)
            # Invalidate older editor save payloads, including payloads loaded before this feature.
            image.update(set__regenerate_thumbnail=True)
            categories = AnnotationModel.objects(image_id=image.id, deleted=False).distinct('category_id')
            image.update(set__category_ids=categories)
            updated = dict(document, category_id=data['targetCategoryId'], metadata=metadata)
            return serialize_box(updated)
        except (ReviewError, ValueError) as error:
            return failure(error)
