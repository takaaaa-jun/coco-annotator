"""Serialize editor saves and category-review writes for a single image."""
import datetime
import functools
import uuid

from flask import request
from flask_login import current_user
from database import ImageModel


def image_write_lock(review=False):
    def decorate(function):
        @functools.wraps(function)
        def wrapped(*args, **kwargs):
            data = request.get_json(silent=True)
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
                    return {'message': 'カテゴリ確認画面で画像が変更されました。保存せず画像を再読み込みしてください。'}, 409
                return function(*args, **kwargs)
            finally:
                collection.update_one({'_id': image_id, 'category_review_lock.token': token}, {'$unset': {'category_review_lock': ''}})
        return wrapped
    return decorate
