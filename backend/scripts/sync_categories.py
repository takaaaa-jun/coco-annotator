"""Sync an exported check_annotator taxonomy. Default is read-only preview."""
import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data', type=Path, required=True)
    parser.add_argument('--source-bindings', type=Path)
    parser.add_argument('--apply', action='store_true')
    args = parser.parse_args()
    data = json.loads(args.data.read_text(encoding='utf-8'))
    bindings = json.loads(args.source_bindings.read_text(encoding='utf-8')) if args.source_bindings else None
    from database import CategoryModel, connect_mongo
    from mongoengine.connection import get_db
    # Import only pure helpers; importing webserver starts the application.
    import importlib.util
    spec = importlib.util.spec_from_file_location('category_sync', str(ROOT / 'webserver/util/category_sync.py'))
    helper = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(helper)
    helper.validate_blueprint(data)
    connect_mongo('flask')
    def create(name, marker):
        # Imported legacy IDs may be larger than MongoEngine's current counter.
        # Advance only the sequence, never reuse or overwrite an existing ID.
        db = get_db()
        highest = db.category_model.find_one(sort=[('_id', -1)])
        field = CategoryModel._fields['id']
        sequence_name = (field.get_sequence_name() if hasattr(field, 'get_sequence_name')
                         else field.sequence_name or CategoryModel._get_collection_name())
        sequence_id = '{}.{}'.format(sequence_name, field.name)
        db[field.collection_name].update_one({'_id': sequence_id},
            {'$max': {'next': highest['_id'] if highest else 0}}, upsert=True)
        model = CategoryModel(name=name, supercategory=marker.get('parentName', ''), metadata={'check_annotator': marker})
        model.save(force_insert=True)
        return model.id
    result = helper.synchronize(get_db(), data, create, bindings, args.apply)
    if args.apply:
        print(json.dumps({'datasetId': result['datasetId'], 'targetCategories': len(result['targetCategories']),
                          'mappings': len(result['mappings']), 'applied': True}))
    else:
        print(json.dumps(result))
        print('Preview only. Add --apply to activate verified new categories.')


if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        print(str(error) if isinstance(error, ValueError) else type(error).__name__, file=sys.stderr)
        sys.exit(1)
