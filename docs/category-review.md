# カテゴリ確認とCOCO Annotatorとの連携

対象Issue: [画面 #54](https://github.com/takaaaa-jun/check_annotator/issues/54)、[API #55](https://github.com/takaaaa-jun/check_annotator/issues/55)、[カテゴリ選択 #56](https://github.com/takaaaa-jun/check_annotator/issues/56)。COCO側でIssueが無効のため、Issueはcheck_annotatorに集約する。

## 仮データで確認する

ヘッダーの「カテゴリ確認」または `/check_annotator/categories` を開く。初期状態は必ずテストモードで、実DBへの書き込みは行わない。

1. 元カテゴリAを持つボックス #90001 と #90002、および対応未設定のボックス #90003 が表示される。
2. 一覧のボックス番号を押すと、その位置が青で強調される。
3. #90001 の「置き換えを確認」を押す。画像ID・ボックスID・現在のカテゴリ・対応先・座標を確認する。
4. キャンセルすると何も変更しない。「この1件を置き換える」を押すと #90001 だけテスト1に変わる。元カテゴリ、座標、#90002 は保持する。「元カテゴリAからテスト1に変更しました」と変更通知を表示する。
5. 対応未設定のカテゴリは置換できない。右側にはCOCOで付与済みのカテゴリと件数のみ表示する。カテゴリ検索・新規付与・描画開始の操作はこの画面に置かない。
6. 仮カテゴリを実COCOへ送信する操作はない。ページ全体の再読み込みで仮データを初期化できる。画面内の「再読み込み」では現在の状態を再取得する。

`frontend/public/category-review.example.json` を「対応表JSONを試す」から読み込むと、準備中の対応表を確認できる。カテゴリIDはリスト内で一意な正の整数、対応は一つの元カテゴリにつき最大一つ。対応先は複数の元カテゴリから共有できる。曖昧・未登録ID・空の一覧・2MBを超えるファイルは拒否する。元カテゴリと置換先が同じIDの場合は置換不要として扱う。

## 実カテゴリデータの接続

1. COCO Annotator側で元カテゴリ・新カテゴリを用意し、対象データセットで有効にする。初期対象はfood_detection（データセットID 2）。仮カテゴリを自動作成する処理はない。
2. サンプルJSONを複製し、`sourceCategories` と `targetCategories` の **idとnameをCOCOの実DBと完全に一致**させる。表示順やファイル番号をカテゴリIDとして使わない。`aliases` は検索用の別名。
3. `mappings` に元カテゴリIDと新カテゴリIDの対応を入れる。対応のない元カテゴリは置換できない。COCOで付与したカテゴリの参照は対応表なしでも利用できる。
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

## 参照画面の責務と変更通知

この画面は、COCO Annotatorに保存されたカテゴリ・ボックスを参照する。例外として、確認ダイアログを経由する一件単位のカテゴリ置換だけを残す。新しいカテゴリの付与・手動の再分類・矩形描画はCOCO Annotator側で行う。以前のカテゴリ検索・カテゴリを選んで描画開始する導線は、この画面から削除した。

実データの参照APIは置換対応表を必要とせず、既存のCOCOセッションと対象画像の権限で読み込む。ポリゴン等も有効なbboxを持つ保存済みアノテーションであれば参照対象に含めるが、矩形以外の置換はできない。描画前の空のアノテーションは参照対象に含めず、追加通知を出さない。

実データモードでは、画面表示中に5秒ごと、ブラウザのフォーカス復帰時、非表示からの復帰時、または「再読み込み」で保存済みデータを再取得する。画像ID・データセットIDが同じ前回の表示とアノテーションIDで照合し、カテゴリIDが変われば「○○から××に変更しました」、新しいアノテーションIDなら「○○を追加しました」と表示する。同じカテゴリのボックスを増やした場合も追加として扱う。

通知はこの画面で確認中の変更の最新20件を表示する。初回表示・別画像への切り替えを追加通知と誤認しない。座標だけの変更、カテゴリ名の表記変更、削除はカテゴリ変更・追加として通知しない。置換直後に比較基準を更新するため、自動再取得で同じ変更を重複通知しない。画面を閉じていた間の完全な履歴や、取得間隔内に複数回変更された中間状態の監査ログではない。

確認ダイアログ表示中の自動更新は停止し、確認対象を途中で差し替えない。置換成功時には変更前後の名称とボックスIDを即時表示する。実DBを使わない仮データのモードは引き続き利用できる。
## 検証

フロント: `npm test`、`npm run lint`、`npx next typegen && npm run typecheck`、`npm run build`。

COCO: `python backend/tests/test_category_review_standalone.py`。通常はDB不要の検証のみ実行する。APIテストは `CATEGORY_REVIEW_TEST_DB=mongodb://category-review-test-db/category_review_tests` を明示した隔離環境でのみ実行でき、他のホスト名を拒否する。実データに対するテスト更新は行わない。

条件付き更新の根拠: [MongoDB公式の単一ドキュメント更新の原子性](https://www.mongodb.com/docs/manual/core/write-operations-atomicity/)。カテゴリ画面の描画完了待ちは [Vue 2公式のnextTick](https://v2.vuejs.org/v2/api/#Vue-nextTick) に従う。
