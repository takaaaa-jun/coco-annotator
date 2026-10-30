/* MongoDB 4.0 mongo shell. Default: read-only audit.
 * Set APPLY_IMAGE_IDS=true only while backend and workers are stopped.
 * Usage: mongo flask --eval 'var APPLY_IMAGE_IDS=false; load("/tmp/align_image_ids.js")'
 */
(function () {
    var datasetName = typeof DATASET_NAME === 'undefined' ? 'food_detection' : DATASET_NAME;
    var apply = typeof APPLY_IMAGE_IDS !== 'undefined' && APPLY_IMAGE_IDS === true;
    function check(ok, message) { if (!ok) throw new Error(message); }
    var datasets = db.dataset_model.find({name: datasetName, deleted: false}).toArray();
    check(datasets.length === 1, 'Expected exactly one active dataset');
    var dataset = datasets[0], mapping = {}, targets = {}, changed = 0, total = 0;
    db.image_model.find().forEach(function (image) {
        var target = image._id;
        if (image.dataset_id === dataset._id) {
            var match = /^([0-9]{5})\.[^.]+$/.exec(image.file_name || '');
            check(match !== null && Number(match[1]) > 0, 'Invalid filename: ' + image.file_name);
            target = Number(match[1]);
            total++;
            if (target !== image._id) changed++;
        }
        check(!Object.prototype.hasOwnProperty.call(targets, target), 'ID collision at ' + target + '; includes other datasets/deleted images');
        targets[target] = true;
        mapping[image._id] = target;
    });
    ['annotation_model', 'task_model'].forEach(function (name) {
        db.getCollection(name).find({image_id: {$exists: true, $ne: null}}).forEach(function (doc) {
            check(Object.prototype.hasOwnProperty.call(mapping, doc.image_id), name + ': dangling image reference ' + doc._id);
        });
    });
    printjson({dataset: datasetName, images: total, mismatched: changed, apply: apply});
    if (!apply || !changed) return;
    var suffix = '_ids_' + new Date().toISOString().replace(/[^0-9]/g, '');
    var names = ['image_model', 'annotation_model', 'task_model', 'mongoengine.counters'];
    var maxId = Math.max.apply(null, Object.keys(targets).map(Number));
    function transform(name, doc) {
        if (name === 'image_model') {
            doc._id = mapping[doc._id];
            // Cached thumbnails may contain the old image ID in their filename.
            doc.regenerate_thumbnail = true;
            doc.annotating = [];
        } else if ((name === 'annotation_model' || name === 'task_model') && doc.image_id != null) {
            doc.image_id = mapping[doc.image_id];
        } else if (name === 'mongoengine.counters' && doc._id === 'image_model.id') {
            doc.next = Math.max(doc.next, maxId);
        }
        return doc;
    }
    names.forEach(function (name) {
        var source = db.getCollection(name), stageName = name + suffix + '_stage';
        check(db.getCollectionNames().indexOf(stageName) < 0, 'Stage already exists');
        check(db.getCollectionNames().indexOf(name + suffix + '_backup') < 0, 'Backup already exists');
        var stage = db.getCollection(stageName), batch = [];
        source.find().forEach(function (doc) {
            batch.push(transform(name, doc));
            if (batch.length === 500) { stage.insertMany(batch); batch = []; }
        });
        if (batch.length) stage.insertMany(batch);
        if (!source.count()) db.createCollection(stageName);
        source.getIndexes().forEach(function (idx) {
            if (idx.name === '_id_') return;
            var options = {};
            ['name', 'unique', 'sparse', 'expireAfterSeconds', 'partialFilterExpression', 'collation'].forEach(function (key) {
                if (idx[key] !== undefined) options[key] = idx[key];
            });
            stage.createIndex(idx.key, options);
        });
        check(source.count() === stage.count(), 'Count mismatch: ' + name);
        source.find().forEach(function (doc) {
            var expected = transform(name, doc), actual = stage.findOne({_id: expected._id});
            check(actual && tojson(expected) === tojson(actual), 'Content mismatch: ' + name + '/' + expected._id);
        });
        print('Validated ' + name + ': ' + source.count());
    });
    // No original collection is replaced until ALL staged collections pass validation.
    print('Backup suffix: ' + suffix + '_backup');
    names.forEach(function (name) {
        db.getCollection(name).renameCollection(name + suffix + '_backup');
        db.getCollection(name + suffix + '_stage').renameCollection(name);
    });
    print('SUCCESS: images and references aligned. Keep backup collections until deployment is verified.');
})();
