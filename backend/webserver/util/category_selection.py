"""Restrict new shapes/reclassification to a managed dataset's new categories."""
from flask_login import current_user
from database import CategoryModel


def validate_selection(image, category_id):
    dataset = current_user.datasets.filter(id=image.dataset_id, deleted=False).first()
    if dataset is None or not current_user.can_edit(dataset):
        raise ValueError('データセットの編集権限がありません。')
    if getattr(dataset, 'category_sync_lock', None):
        raise ValueError('カテゴリ同期中です。再読み込みしてください。')
    if getattr(dataset, 'category_review_catalog', None) and category_id not in dataset.categories:
        raise ValueError('新しく付与できるのは同期済みの新カテゴリだけです。')
    catalog = getattr(dataset, 'category_review_catalog', None)
    if catalog:
        expected = next((row for row in catalog['targetCategories'] if row['id'] == category_id), None)
        actual = CategoryModel.objects(id=category_id, deleted=False).first()
        marker = actual.metadata.get('check_annotator', {}) if actual else {}
        if (expected is None or actual is None or actual.name != expected['name']
                or marker.get('key') != expected.get('managedKey')
                or marker.get('taxonomy') != catalog.get('managedTaxonomy')):
            raise ValueError('新カテゴリの管理コード・名称が同期結果と一致しません。')
