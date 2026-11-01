"""Pure validation and concurrency helpers for category-review (no DB imports)."""
import copy
import hashlib
import json
import math


def positive_id(value):
    if isinstance(value, bool) or not isinstance(value, int) or not 0 < value <= 9007199254740991:
        raise ValueError('IDは正の整数で指定してください。')
    return value


def validate_catalog(data):
    if not isinstance(data, dict) or not isinstance(data.get('version'), str) or not data['version'].strip():
        raise ValueError('対応表のversionが必要です。')
    positive_id(data.get('datasetId'))
    ids = {}
    for key in ('sourceCategories', 'targetCategories'):
        rows = data.get(key)
        if not isinstance(rows, list) or not rows:
            raise ValueError('カテゴリ一覧が空です。')
        ids[key] = set()
        for row in rows:
            if not isinstance(row, dict):
                raise ValueError('カテゴリの形式が不正です。')
            identifier = positive_id(row.get('id'))
            if identifier in ids[key]:
                raise ValueError('カテゴリIDが重複しています。')
            ids[key].add(identifier)
            if not isinstance(row.get('name'), str) or not row['name'].strip():
                raise ValueError('カテゴリ名が空です。')
            aliases = row.get('aliases', [])
            if not isinstance(aliases, list) or any(not isinstance(alias, str) for alias in aliases):
                raise ValueError('別名は文字列の配列で指定してください。')
    if not isinstance(data.get('mappings'), list):
        raise ValueError('mappingsが必要です。')
    mapped = set()
    for row in data['mappings']:
        if not isinstance(row, dict):
            raise ValueError('対応表の形式が不正です。')
        source = positive_id(row.get('sourceCategoryId'))
        target = positive_id(row.get('targetCategoryId'))
        if source not in ids['sourceCategories'] or target not in ids['targetCategories']:
            raise ValueError('対応表に存在しないカテゴリがあります。')
        if source in mapped:
            raise ValueError('一つの元カテゴリに複数の置換先は指定できません。')
        mapped.add(source)
    result = copy.deepcopy(data)
    # Bind the revision to all file contents, even when an operator forgets to bump version.
    result['version'] = data['version'] + ':' + fingerprint(data)[:16]
    return result


def fingerprint(data):
    return hashlib.sha256(json.dumps(data, sort_keys=True, default=str, separators=(',', ':')).encode('utf-8')).hexdigest()


def has_geometry(document):
    bbox = document.get('bbox', [])
    return (isinstance(bbox, list) and len(bbox) == 4
            and all(isinstance(n, (float, int)) and not isinstance(n, bool) and math.isfinite(n) for n in bbox)
            and bbox[2] > 0 and bbox[3] > 0)


def is_box(document):
    return document.get('isbbox') is True and has_geometry(document)


def original_category(document):
    metadata = document.get('metadata', {})
    if not isinstance(metadata, dict):
        raise ValueError('ボックスのメタデータの形式が不正です。')
    provenance = metadata.get('category_review', {})
    if not isinstance(provenance, dict):
        raise ValueError('category_reviewメタデータの形式が不正です。')
    return provenance.get('original_category_id', document['category_id'])


def serialize_box(document):
    return {
        'id': document['_id'], 'imageId': document['image_id'],
        'categoryId': document['category_id'], 'originalCategoryId': original_category(document),
        'bbox': document['bbox'], 'revision': fingerprint(document), 'isBox': is_box(document),
    }


def replacement_metadata(document, catalog, target_id, username, timestamp):
    if not is_box(document):
        raise ValueError('矩形以外のアノテーションは置換できません。')
    source = original_category(document)
    mapping = next((m for m in catalog['mappings'] if m['sourceCategoryId'] == source), None)
    if mapping is None or mapping['targetCategoryId'] != target_id:
        raise ValueError('対応表と置換先が一致しません。')
    if document['category_id'] != source:
        raise ValueError('元カテゴリから変更済みです。再読み込みして確認してください。')
    metadata = copy.deepcopy(document.get('metadata', {}))
    previous = metadata.get('category_review')
    if previous is not None and not isinstance(previous, dict):
        raise ValueError('category_reviewメタデータの形式が不正です。')
    source_row = next(c for c in catalog['sourceCategories'] if c['id'] == source)
    metadata['category_review'] = {
        'original_category_id': source, 'original_category_name': source_row['name'],
        'catalog_version': catalog['version'], 'previous_category_id': document['category_id'],
        'target_category_id': target_id, 'changed_by': username, 'changed_at': timestamp,
    }
    return metadata
