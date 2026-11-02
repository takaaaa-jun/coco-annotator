# 「JSONオブジェクトが必要です」の修正

旧編集画面はAxiosへJSON.stringify済みの文字列を渡しており、Axios 0.18は
application/x-www-form-urlencodedとして送信していた。
image_write_lockのJSON検証がこの保存形式を拒否していた。

新画面はオブジェクトを渡してapplication/jsonで送信する。
旧画面が開いたままでも、通常の編集保存に限りJSON本文を解析する。
Originが異なるリクエストは解析前に拒否する。
カテゴリ置換APIは従来どおりapplication/jsonと専用ヘッダーを必須とし、緩和しない。

反映はbackendとfrontendの両方が必要。

```bash
cd /srv/coco-annotator
git switch main
git pull --ff-only origin main
docker compose build backend frontend
docker compose up -d --no-deps backend frontend
```

更新後に編集画面を再読み込みする前に、保存待ちの編集内容があるかを確認する。
この修正では既存のカテゴリ・画像・アノテーションを移行・削除しない。

旧カテゴリのゼロ件行まで引き続き出る場合、対象データセットの同期状態も別途確認する。
画面キャッシュの問題と断定せず、画像のdataset_id、CATEGORY_REVIEW_DATASET_ID、
dataset.category_review_catalog、dataset.categoriesを照合する。
旧カテゴリの付与済みボックスを残すこと自体は正常だが、新規付与候補は新カテゴリに切り替わる。

検証：実MongoDBで同期・編集保存API24件、既存置換API15件が成功。
Vue 2と実Axios 0.18の関連3スイート18件も成功。
画面テストは既存ローカルBabel依存不足のため隔離した変換設定を使用した。
