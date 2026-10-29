# COCO Annotator

画像のバウンディングボックス・領域・キーポイントを編集するWebアプリケーションです。
[jsbroks/coco-annotator](https://github.com/jsbroks/coco-annotator)をベースにしています。
ライセンスと原著作者の表記は[LICENSE.md](LICENSE.md)を参照してください。

## 運用方針

- 本番環境はUbuntu。Windowsはローカル開発・確認用です。
- gateway経由で`/coco-annotator/`を公開します。
- ソースコードと配備設定をGitで管理し、画像・DB・秘密情報は別途用意します。
- 起動入口は`compose.yaml`です。共通設定と本番設定を読み込みます。

## Ubuntuでの配備

Docker EngineとDocker Compose 2.20.0以降、gatewayを用意してください。
リポジトリは`.git`を含む形でcloneします。現在のビルドはバージョン情報のため`.git`を参照します。

1. `.env.example`を`.env`へコピーし、`SECRET_KEY`に十分に長いランダム文字列を設定します。
2. `datasets/<データセット名>/`へ画像を配置します。必要なら`models/`にもモデルを配置します。
3. `deploy/coco-annotator.conf`をgatewayの`conf.d/`へ配置します。
4. gatewayとアプリが使う`shared-gateway-net`を用意します。既存なら作成は不要です。
5. アプリのルートで以下を実行します。

```sh
docker compose config --quiet
docker compose up -d --build
docker compose ps
```

gateway側で`nginx -t`による検証後に設定を再読み込みし、
`http://<サーバーのIPまたはホスト名>/coco-annotator/`を開きます。
詳細は[GATEWAY.md](GATEWAY.md)を参照してください。

## データセットの登録

1. 画像フォルダと同じ名前のデータセットを画面で作成します。
2. `Scan`で画像を登録します。
3. 既存ボックスがある場合は`Import COCO`でJSONを取り込みます。
4. `Tasks`で完了・警告・エラーを確認します。
5. 画像を開き、編集・保存・開き直しを確認します。

COCO内の`images[].file_name`は、画像のファイル名と一致させてください。
現在の取り込み処理では、`bbox`だけで`segmentation`も`keypoints`もないデータはスキップされます。
JSONを画像フォルダに置くだけではアノテーションは取り込まれません。

画像一覧の`Contains`は通常ファイル名の部分一致で検索します。
`00001-01000`のように入力してEnterを押すと、DBの画像IDが1以上1000以下の範囲で検索します。
範囲の両端を含み、並べ替え・カテゴリ・アノテーション有無の条件とも併用できます。
カード左側の表示連番ではなく、DBの画像IDが検索対象です。

## 保存先とバックアップ

| 対象 | 保存先 | Git管理 |
| --- | --- | --- |
| 画像・COCO JSON | `datasets/` | 対象外 |
| オプションのモデル | `models/*.h5` | 対象外 |
| ユーザー・カテゴリ・ボックス | Dockerボリューム`coco-annotator_mongodb_data` | 対象外 |
| 秘密鍵 | `.env` | 対象外 |
| ローカルバックアップ | `backups/` | 対象外 |

別サーバーへデータを引き継ぐ場合は、最新DBをバックアップ・復元します。
`db/`は旧データの保管場所であり、現在のDB保存先ではありません。
通常の停止は`docker compose down`を使用します。`down -v`はDBボリュームを削除します。

## ログ

```sh
docker compose logs -f --tail 100 backend workers
docker compose logs --tail 100 database
```

## ディレクトリ

| 場所 | 役割 |
| --- | --- |
| `client/` | Vue製の画面と配信用Nginx設定 |
| `backend/webserver/` | Flask APIとAPI・ワーカー共通Dockerfile |
| `backend/database/` | MongoDBモデル |
| `backend/workers/` | 取り込み・出力・スキャンなどの非同期処理 |
| `backend/tests/` | バックエンドの既存テスト |
| `backend/Dockerfile` | Python依存環境の再構築用定義。通常起動では既成イメージを使用 |
| `deploy/` | gatewayへ配置する設定 |
| `models/` | オプションのモデル取得スクリプト |
