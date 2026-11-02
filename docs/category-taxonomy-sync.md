# check_annotatorの登録済みカテゴリを使う

MySQLから`export_coco_categories.py`で出力した同期用JSONを使用する。
元表の外部IDはCOCOの実ID候補として扱い、名称が一致しなければ対象データセット内の一意な完全一致名から実IDを解決する。
IDは振り直さず、同名候補が複数あって特定できない場合は中止する。
空白数だけの表記差は正規化するが、単語・綴り・大文字小文字の近似照合は行わない。
新カテゴリは`metadata.check_annotator`の階層別管理codeで識別する。

元ID67「だし巻き卵」の追加後は新カテゴリ46件・元の置換候補42件。
実サーバーのCOCOは同名omeletを統合した255カテゴリであり、実IDごとの対応は41件。
omeletには「オムレツ」「だし巻き卵」の2候補が付き、選択と確認を必須にする。
古い画面が先頭候補を送っても、明示選択がなければ拒否する。
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
IDと元名称が一致せず、名称でも一意に特定できなければ中止する。実IDを確認した場合のみ
`--source-bindings /datasets/.category-review/source-bindings.json`を指定する。
例：`{"20":320}`。名称一致は省略しない。
元表の同名2行がCOCOの同じ実IDになる場合は、両方の置換先が設定済みの場合だけ候補を併記する。
同じ名前に複数の実COCO IDがあり、既知IDでも区別できない場合は自動的にまとめない。

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
未対応214件の置換、矩形以外のアノテーションの置換は行わない。

詳しいサーバーコマンドはcheck_annotatorの`docs/COCO同期修復.md`を参照。

## テスト

専用の隔離MongoDBだけを指定する。アプリ用DBは指定できない。

```bash
COCO_CATEGORY_TEST_DB=mongodb://category-review-test-db/category_sync_tests \
  python backend/tests/test_category_sync.py
CATEGORY_REVIEW_TEST_DB=mongodb://category-review-test-db/category_review_tests \
  python backend/tests/test_category_review_standalone.py
```

全256元分類・42候補と実COCOの255分類の通し検証には、MySQLから出力したJSONのパスを
`COCO_CATEGORY_TEST_BLUEPRINT`へ設定する。
ローカル実行では127.0.0.1:27028の同名専用DBも許可している。
テストは指定されたテストDBのコレクションを作り直す。
