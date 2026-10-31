# カテゴリ確認とCOCO Annotatorとの連携

対象Issue: [画面 #54](https://github.com/takaaaa-jun/check_annotator/issues/54)、[API #55](https://github.com/takaaaa-jun/check_annotator/issues/55)、[カテゴリ選択 #56](https://github.com/takaaaa-jun/check_annotator/issues/56)。COCO側でIssueが無効のため、Issueはcheck_annotatorに集約する。

## 仮データで確認する

ヘッダーの「カテゴリ確認」または `/check_annotator/categories` を開く。初期状態は必ずテストモードで、実DBへの書き込みは行わない。

1. 元カテゴリAを持つボックス #90001 と #90002、および対応未設定のボックス #90003 が表示される。
2. 一覧のボックス番号を押すと、その位置が青で強調される。
3. #90001 の「置き換えを確認」を押す。画像ID・ボックスID・現在のカテゴリ・対応先・座標を確認する。
4. キャンセルすると何も変更しない。「この1件を置き換える」を押すと #90001 だけテスト1に変わる。元カテゴリ、座標、#90002 は保持する。
5. 対応未設定のカテゴリは置換できない。右側のカテゴリ検索は名前・別名・IDを使い、全角・半角を正規化して検索する。
6. テストモードのカテゴリ選択では実COCOへ仮IDを送らない。再読み込みで仮の置換結果をリセットできる。

`frontend/public/category-review.example.json` を「対応表JSONを試す」から読み込むと、準備中の対応表を確認できる。カテゴリIDはリスト内で一意な正の整数、対応は一つの元カテゴリにつき最大一つ。対応先は複数の元カテゴリから共有できる。曖昧・未登録ID・空の一覧・2MBを超えるファイルは拒否する。元カテゴリと置換先が同じIDの場合は置換不要として扱う。

## 実カテゴリデータの接続

1. COCO Annotator側で元カテゴリ・新カテゴリを用意し、対象データセットで有効にする。初期対象はfood_detection（データセットID 2）。仮カテゴリを自動作成する処理はない。
2. サンプルJSONを複製し、`sourceCategories` と `targetCategories` の **idとnameをCOCOの実DBと完全に一致**させる。表示順やファイル番号をカテゴリIDとして使わない。`aliases` は検索用の別名。
3. `mappings` に元カテゴリIDと新カテゴリIDの対応を入れる。対応のない元カテゴリは置換できないが、新規付与用のカテゴリ検索は利用できる。
4. COCO側の既存datasetsボリューム内に、例として `datasets/.category-review/catalog.json` を保存する。COCO側の `.env` に `CATEGORY_REVIEW_CATALOG=/datasets/.category-review/catalog.json` を設定し、backendを再作成する。対応表ファイルを公開ディレクトリに配置する必要はない。
5. 両アプリの変更を反映し、COCO側でログインする。カテゴリ確認画面のデータ元を「COCO Annotator（実データ）」へ切り替えて、実際の画像IDを読み込む。
6. 対応表の内容を変更したら `version` も更新する。サーバーは内容のハッシュも併用し、version更新漏れでも古い確認内容からの書き込みを拒否する。

実データの読み込みに失敗した場合、テストモードへの自動移行は行わない。未設定は503、未ログインは401、権限不足は403、不一致・競合は409として扱う。

## 実データでの置換

APIはCOCOの同一ホスト・既存ログインセッションを使用する。check_annotatorのサーバーはCOCOの認証情報を保持・代理送信しない。

| 操作 | COCO側API |
| --- | --- |
| 検証済み対応表 | `GET /coco-annotator/api/category-review/catalog` |
| 画像と矩形一覧 | `GET /coco-annotator/api/category-review/images/{imageId}` |
| 一つの矩形のカテゴリ置換 | `PUT /coco-annotator/api/category-review/annotations/{annotationId}/category` |

更新要求には `datasetId`、`imageId`、`annotationId`、`expectedCategoryId`、`expectedRevision`、`targetCategoryId`、`catalogVersion` が必要。画面から `X-Category-Review: 1` を付けて送信する。

サーバーは対応表の所属・名称・有効状態、データセット編集権限、対象画像・ボックス・置換先、表示時点のボックス全体のハッシュを検証する。MongoDBの単一ドキュメントの条件付き更新でカテゴリと来歴だけを変更し、矩形・セグメンテーション・他ボックスを変更しない。元カテゴリID・元名称・置換前後・対応表バージョン・実行者・日時は `annotation.metadata.category_review` に保持する。元カテゴリとは、この連携による最初の置換直前のカテゴリであり、それ以前の変更履歴は復元できない。

COCO側で画像編集中のユーザーがいる場合、置換を拒否する。編集内容を保存して画像を閉じてから行う。画像ごとの短時間ロックにより、この連携の置換と編集画面の保存を直列化する。置換後は画像のリビジョンを上げ、古い編集画面の保存を拒否する。保存エラーを画面表示し、無言で上書きしない。途中でプロセスが終了した場合に備え、ロックの有効期限は10分。

対応表にはない手動の再分類や、既に変更済みのボックスの再置換はこのAPIの対象外。既存のCOCO編集機能は残す。

## 新しい矩形を作る

実データモードでカテゴリを検索し「このカテゴリで矩形を描く」を押す。COCOの画像編集URLへ `dataset_id`、`category_id`、`tool=bbox` を付けて遷移する。COCOは読み込み完了後にデータセットとカテゴリを検証し、カテゴリを選択済みにする。

未保存の編集を自動保存・破棄しないよう、この新規付与の導線は別タブを使う。既存の画像編集ボタンのタブ再利用とは別の動作。カテゴリ引き継ぎ自体ではアノテーションを作らない。COCO画面の「このカテゴリで新しい矩形を開始」を押した時点で空のアノテーションを作成し、矩形ツールを選ぶ。その後、画像上で矩形を描画し、COCOで保存する。開始後に描画を取り消す場合は、空のアノテーションをCOCO上で削除する。

## 検証

フロント: `npm test`、`npm run lint`、`npx next typegen && npm run typecheck`、`npm run build`。

COCO: `python backend/tests/test_category_review_standalone.py`。通常はDB不要の検証のみ実行する。APIテストは `CATEGORY_REVIEW_TEST_DB=mongodb://category-review-test-db/category_review_tests` を明示した隔離環境でのみ実行でき、他のホスト名を拒否する。実データに対するテスト更新は行わない。

条件付き更新の根拠: [MongoDB公式の単一ドキュメント更新の原子性](https://www.mongodb.com/docs/manual/core/write-operations-atomicity/)。カテゴリ画面の描画完了待ちは [Vue 2公式のnextTick](https://v2.vuejs.org/v2/api/#Vue-nextTick) に従う。
