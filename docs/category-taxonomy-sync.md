# check_annotatorの登録済みカテゴリを使う

MySQLから`export_coco_categories.py`で出力した同期用JSONを使用する。
元表の外部IDはCOCOの実ID候補として扱い、名称が完全一致した場合のみ採用する。
新カテゴリは`metadata.check_annotator`の階層別管理codeで識別する。

今回の分類では新カテゴリ45件・置換対応41件。
旧カテゴリ・既存アノテーションは削除せず、新規付与の選択肢を新カテゴリへ切り替える。
COCO編集画面には旧カテゴリの付与済みボックスも残るが、新規作成・再分類先には使えない。

全編集画面を閉じ、書き込み元のbackend/frontend/workersを停止してから同期する。
先に両リポジトリの変更を反映し、COCOのイメージをビルドする。
JSONはdatasets/.category-review/taxonomy.jsonへ保存する。

```bash
docker compose run --rm --no-deps -v "$PWD/backend:/source:ro" \
  backend python /source/scripts/sync_categories.py \
  --data /datasets/.category-review/taxonomy.json
```

このコマンドは参照のみ。確認後に`--apply`を追加する。
IDと元名称が一致しなければ中止する。実IDを確認した場合のみ
`--source-bindings /datasets/.category-review/source-bindings.json`を指定する。
例：`{"20":320}`。名称一致・元IDの一意性は省略しない。
同名の旧カテゴリが複数ある場合も、名前だけでまとめたり対応を推測したりしない。

`.env`を次のように設定してbackend/frontend/workersを再作成する。

```dotenv
CATEGORY_REVIEW_DATASET_ID=2
CATEGORY_REVIEW_CATALOG=
```

新しい対応表は対象データセットのMongoDBドキュメントに保存する。
新カテゴリと対応表は全件検証してから単一更新で有効化する。
途中失敗で新カテゴリだけが残っても、再実行時に管理codeで再利用する。
同期済みデータセットで古いファイル対応表へ自動的に戻ることはない。
同期時はアノテーションを変更せず、確認画面からの1件単位の置換だけを行う。
未対応215件の置換、描画以外のアノテーションの置換は行わない。

詳しいサーバーコマンドはcheck_annotatorの`docs/COCO新カテゴリ同期.md`を参照。

## テスト

専用の隔離MongoDBだけを指定する。アプリ用DBは指定できない。

```bash
COCO_CATEGORY_TEST_DB=mongodb://category-review-test-db/category_sync_tests \
  python backend/tests/test_category_sync.py
CATEGORY_REVIEW_TEST_DB=mongodb://category-review-test-db/category_review_tests \
  python backend/tests/test_category_review_standalone.py
```

全256件・41対応の通し検証には、MySQLから出力したJSONのパスを
`COCO_CATEGORY_TEST_BLUEPRINT`へ設定する。
ローカル実行では127.0.0.1:27028の同名専用DBも許可している。
テストは指定されたテストDBのコレクションを作り直す。
