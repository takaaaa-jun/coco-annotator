"""Serialize editor saves and category-review writes for a single image."""
import datetime
import functools
import uuid
from urllib.parse import urlsplit

from flask import request
from flask_login import current_user
from database import ImageModel


def image_write_lock(review=False):
    def decorate(function):
        @functools.wraps(function)
        def wrapped(*args, **kwargs):
            # Old editor bundles sent JSON text with form Content-Type. Support that
            # same-origin save format without relaxing the category-review API.
            origin = request.headers.get('Origin')
            if origin and urlsplit(origin).netloc != request.host:
                return {'message': '同じホストの編集画面から保存してください。'}, 403
            data = request.get_json(force=not review, silent=True)
            if not isinstance(data, dict):
                return {'message': 'JSONオブジェクトが必要です。'}, 400
            image_data = data.get('image', {})
            image_id = data.get('imageId') if review else image_data.get('id') if isinstance(image_data, dict) else None
            if isinstance(image_id, bool) or not isinstance(image_id, int):
                return {'message': '画像IDが必要です。'}, 400
            image = current_user.images.filter(id=image_id, deleted=False).first()
            if image is None:
                return {'message': '画像へのアクセス権がありません。'}, 403
            collection = ImageModel._get_collection()
            now = datetime.datetime.utcnow()
            token = uuid.uuid4().hex
            acquired = collection.update_one(
                {'_id': image_id, '$or': [{'category_review_lock': {'$exists': False}}, {'category_review_lock.expires': {'$lt': now}}]},
                {'$set': {'category_review_lock': {'token': token, 'expires': now + datetime.timedelta(minutes=10)}}})
            if acquired.modified_count != 1:
                return {'message': '別の保存処理が実行中です。完了後に再実行してください。'}, 409
            try:
                current = collection.find_one({'_id': image_id})
                if not review and image_data.get('category_review_revision', 0) != current.get('category_review_revision', 0):
                    return {'message': '他の操作で画像が更新されています。編集内容を確認し、画像を再読み込みしてください。'}, 409
                # Reserve a new revision before any editor writes, so even a partial
                # failure cannot be overwritten by another editor's old snapshot.
                if not review:
                    collection.update_one({'_id': image_id}, {'$inc': {'category_review_revision': 1}})
                result = function(*args, **kwargs)
                if not review and isinstance(result, dict) and result.get('success', result.get('saved', False)):
                    result['category_review_revision'] = current.get('category_review_revision', 0) + 1
                return result
            finally:
                collection.update_one({'_id': image_id, 'category_review_lock.token': token}, {'$unset': {'category_review_lock': ''}})
        return wrapped
    return decorate
