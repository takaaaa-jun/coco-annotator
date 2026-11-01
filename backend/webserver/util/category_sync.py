"""Validate a MySQL taxonomy export and activate its real COCO categories safely."""
import copy
import datetime
import hashlib
import json
import uuid


def fingerprint(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                    separators=(',', ':')).encode('utf-8')).hexdigest()


def validate_blueprint(data):
    if not isinstance(data, dict) or data.get('schemaVersion') != 1 or data.get('taxonomy') != 'check-annotator':
        raise ValueError('Unsupported category blueprint.')
    unsigned = copy.deepcopy(data)
    version = unsigned.pop('version', None)
    if version != fingerprint(unsigned):
        raise ValueError('Blueprint checksum does not match its content.')
    if type(data.get('datasetId')) is not int or data['datasetId'] <= 0:
        raise ValueError('Invalid dataset ID.')
    if not isinstance(data.get('datasetName'), str) or not data['datasetName'].strip():
        raise ValueError('Dataset name is required.')
    if not isinstance(data.get('source'), dict) or not data['source'].get('code'):
        raise ValueError('Source code is required.')
    sources, targets = {}, {}
    for row in data['sourceCategories']:
        identifier = row['externalId']
        if type(identifier) is not int or identifier <= 0 or identifier in sources or not isinstance(row['name'], str) or not row['name'].strip():
            raise ValueError('Invalid or duplicated source category.')
        sources[identifier] = row
    for row in data['targetCategories']:
        key = row['key']
        if not isinstance(key, str) or not key.startswith(('5:', '6:')) or key in targets or not isinstance(row['name'], str) or not row['name'].strip():
            raise ValueError('Invalid or duplicated target category.')
        if not isinstance(row.get('description'), str):
            raise ValueError('Invalid category description.')
        targets[key] = row
    for row in targets.values():
        parent = row.get('parentKey')
        if row['key'].startswith('6:') and (parent not in targets or not parent.startswith('5:')):
            raise ValueError('Category6 parent is missing.')
        if row['key'].startswith('5:') and parent is not None:
            raise ValueError('Unexpected category5 parent.')
    mapped = set()
    for row in data['mappings']:
        source = row['sourceExternalId']
        if source not in sources or source in mapped or row['targetKey'] not in targets:
            raise ValueError('Invalid or ambiguous replacement mapping.')
        mapped.add(source)
    if not sources or not targets or not mapped:
        raise ValueError('Empty categories or mappings.')
    return sources, targets


def plan_sync(db, data, source_bindings=None):
    sources, targets = validate_blueprint(data)
    dataset = db.dataset_model.find_one({'_id': data['datasetId'], 'deleted': {'$ne': True}})
    if dataset is None or dataset.get('name') != data['datasetName']:
        raise ValueError('Dataset does not exist.')
    if db.image_model.find_one({'dataset_id': dataset['_id'], 'deleted': {'$ne': True}, 'annotating.0': {'$exists': True}}):
        raise ValueError('Close active editors before synchronizing categories.')
    bindings = source_bindings or {}
    if set(bindings) - set(str(key) for key in sources):
        raise ValueError('Source bindings contain unknown external IDs.')
    actual_sources = []
    source_ids = {}
    # ID is only a proposed binding. Exact names are checked even for explicit bindings.
    for external_id, row in sorted(sources.items()):
        actual_id = bindings.get(str(external_id), external_id)
        if type(actual_id) is not int or actual_id <= 0 or actual_id in source_ids.values():
            raise ValueError('Invalid or duplicate actual source binding.')
        actual = db.category_model.find_one({'_id': actual_id, 'deleted': {'$ne': True}})
        if actual is None or actual.get('name') != row['name']:
            raise ValueError('Source ID/name mismatch for external ID {}.'.format(external_id))
        source_ids[external_id] = actual_id
        actual_sources.append({'id': actual_id, 'name': actual['name'], 'aliases': []})
    actual_targets, missing = {}, []
    for key, row in sorted(targets.items()):
        found = list(db.category_model.find({'metadata.check_annotator.taxonomy': data['taxonomy'],
                                             'metadata.check_annotator.key': key}))
        if len(found) > 1:
            raise ValueError('Multiple COCO categories share managed key {}.'.format(key))
        if found:
            actual = found[0]
            identity = actual.get('metadata', {}).get('check_annotator', {})
            if (actual.get('deleted') or actual['name'] != row['name']
                    or identity.get('description', '') != row['description']
                    or identity.get('parentKey') != row.get('parentKey')
                    or actual.get('supercategory', '') != (targets[row['parentKey']]['name'] if row.get('parentKey') else '')
                    or actual['_id'] in source_ids.values()):
                raise ValueError('Existing managed category conflicts with {}.'.format(key))
            actual_targets[key] = actual['_id']
        else:
            # Never adopt or rename a category merely because its display name matches.
            if db.category_model.find_one({'name': row['name'], 'creator': 'system'}):
                raise ValueError('Unmanaged system category already uses name {}.'.format(row['name']))
            missing.append(row)
    unknown = set(dataset.get('categories', [])) - set(source_ids.values()) - set(actual_targets.values())
    if unknown:
        raise ValueError('Dataset contains unrelated category IDs; resolve them before replacing selectable categories.')
    return {'dataset': dataset, 'sources': actual_sources, 'sourceIds': source_ids,
            'targetIds': actual_targets, 'missing': missing, 'targets': targets}


def synchronize(db, data, create_category, source_bindings=None, apply=False):
    plan = plan_sync(db, data, source_bindings)
    if not apply:
        return {'datasetId': data['datasetId'], 'createCategories': len(plan['missing']),
                'targetCategories': len(plan['targets']), 'mappings': len(data['mappings'])}
    # Registry activation is a single compare-and-set on the dataset. Partial category
    # creation can leave reusable targets but never activates half a catalog.
    token = uuid.uuid4().hex
    acquired = db.dataset_model.update_one(
        {'_id': data['datasetId'], 'category_sync_lock': {'$exists': False}},
        {'$set': {'category_sync_lock': token}})
    if acquired.modified_count != 1:
        raise ValueError('Another category sync is running. Inspect an abandoned lock before retrying.')
    try:
        plan = plan_sync(db, data, source_bindings)
        for target in plan['missing']:
            marker = {'taxonomy': data['taxonomy'], 'key': target['key'],
                      'description': target['description'], 'parentKey': target.get('parentKey'),
                      'parentName': plan['targets'][target['parentKey']]['name'] if target.get('parentKey') else ''}
            plan['targetIds'][target['key']] = create_category(target['name'], marker)
        # Re-resolve every created ID/name before exposing it to annotators.
        plan = plan_sync(db, data, source_bindings)
        if plan['missing']:
            raise ValueError('Created categories failed identity verification.')
        targets = [{'id': plan['targetIds'][key], 'name': row['name'], 'aliases': [],
                    'managedKey': key} for key, row in sorted(plan['targets'].items())]
        catalog = {'version': data['version'], 'datasetId': data['datasetId'],
                   'sourceCategories': plan['sources'], 'targetCategories': targets,
                   'mappings': [{'sourceCategoryId': plan['sourceIds'][row['sourceExternalId']],
                                 'targetCategoryId': plan['targetIds'][row['targetKey']]} for row in data['mappings']],
                   'managedTaxonomy': data['taxonomy']}
        before = plan['dataset']
        if before.get('category_review_catalog') == catalog and set(before.get('categories', [])) == set(plan['targetIds'].values()):
            return catalog
        selector = {'_id': data['datasetId'], 'category_sync_lock': token, 'categories': before.get('categories', []),
                    'category_review_catalog': before.get('category_review_catalog')}
        activated = db.dataset_model.update_one(selector, {'$set': {
            'categories': sorted(plan['targetIds'].values()), 'category_review_catalog': catalog,
            'category_review_taxonomy_revision': fingerprint(catalog),
            'category_review_previous_categories': before.get('category_review_previous_categories', before.get('categories', [])),
        }})
        if activated.modified_count != 1:
            raise ValueError('Dataset changed during sync. No new catalog was activated.')
        return catalog
    finally:
        db.dataset_model.update_one({'_id': data['datasetId'], 'category_sync_lock': token}, {'$unset': {'category_sync_lock': ''}})
