# バックエンド

- `webserver/`: Flask API、認証、Socket.IO、画像配信。
- `database/`: MongoEngineによるMongoDBモデル。
- `workers/`: CeleryによるCOCO取り込み・出力、画像スキャン、サムネイル生成。
- `config/`: 環境変数から読み込む共通設定。
- `tests/`: 既存のAPI・モデルテスト。

通常の起動はリポジトリのルートで`docker compose up -d --build`を使用します。
`webserver/Dockerfile`の`production`対象がAPI、`workers`対象が非同期処理を起動します。
DB接続先は内部ネットワークの`database`、メッセージキューは`messageq`です。

`Dockerfile`は元プロジェクトのPython依存環境を作るための定義です。
通常のComposeでは`jsbroks/coco-annotator:python-env`を利用します。

配備とデータ移行は[ルートのREADME](../README.md)と[GATEWAY.md](../GATEWAY.md)を参照してください。
