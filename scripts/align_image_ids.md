# ファイル名の数字へ画像IDを合わせる（既存DBの一度限りの移行）

対象は `food_detection`。削除済みを含む画像を対象とし、他データセットも含めIDが衝突する場合は処理を中止する。
アノテーションの `image_id`、タスクの `image_id`、画像採番カウンタも更新する。
ファイル名・画像ファイル・ボックス座標・カテゴリ・ユーザー権限は変更しない。
今後の新規画像登録時にファイル名とIDが一致することを保証する変更ではない。

## Ubuntuでの手順

事前に `align_image_ids.js` をサーバの `/srv/coco-annotator/scripts/` へ配置する。
全利用者に作業を終了してもらい、以下を実行する。以前開いた画像編集タブは再利用せず閉じる。

```bash
cd /srv/coco-annotator
docker compose stop backend workers
mkdir -p backups
docker compose exec -T database mongodump --db flask --gzip --archive=/tmp/before-id-alignment.archive.gz
docker compose cp database:/tmp/before-id-alignment.archive.gz backups/before-id-alignment.archive.gz
docker compose cp scripts/align_image_ids.js database:/tmp/align_image_ids.js
docker compose exec -T database mongo --quiet flask --eval 'var APPLY_IMAGE_IDS=false; load("/tmp/align_image_ids.js")'
```

バックアップコマンドの成功と検査結果を確認してから適用する。

```bash
docker compose exec -T database mongo --quiet flask --eval 'var APPLY_IMAGE_IDS=true; load("/tmp/align_image_ids.js")'
docker compose exec -T database mongo --quiet flask --eval 'var APPLY_IMAGE_IDS=false; load("/tmp/align_image_ids.js")'
```

`SUCCESS`、再検査の `mismatched: 0` を確認してから起動する。

```bash
docker compose start backend workers
```

ブラウザの古い画像編集タブを閉じ、データセット一覧から開き直す。移行前の画像URL・ブックマークは画像の対応が変わる。
画像IDはファイル番号に合わせるため欠番があってよい。表示順番号と画像IDも別の値である。
`Scan` や `Import COCO`、ローカルDB全体の上書き転送は不要。
サーバ自身のDB上で実行することで、サーバで作成したユーザー・権限を保持する。

## 退避と失敗時の扱い

全コレクションのコピー先で件数・全ドキュメント・インデックス作成を確認してから切り替える。
元データは `元コレクション名_ids_日時_backup` に残る。処理中はアプリ停止が必須。
MongoDB 4.0では複数コレクションの切替全体は一括処理ではないため、途中失敗時は起動せず切替状態を確認する。
退避コレクションを自動削除しない。バックアップも繰り返し実行時は別名で保存する。
復旧にはアプリ停止のまま保存したアーカイブを `mongorestore --gzip --archive=... --nsInclude='flask.*' --drop` で復元する。
参照先がない既存アノテーション・タスクや重複ファイル番号がある場合は、適用前に中止して原因を調査する。
