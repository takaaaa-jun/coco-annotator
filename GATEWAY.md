# gateway経由での利用

公開URLは `http://localhost/coco-annotator/`。設定の基準は
`../gateway/README.md`。`deploy/coco-annotator.conf`を
gatewayの`conf.d/coco-annotator.conf`へ配置してください。

`check_annotator`と同じく、標準の`compose.yaml`が共通設定
`docker-compose.base.yaml`と本番設定`docker-compose.prod.yaml`を読み込みます。
Docker Compose 2.20.0以降を使用してください。

| ファイル | 役割 |
| --- | --- |
| `compose.yaml` | 通常の起動入口 |
| `docker-compose.base.yaml` | アプリ・DB・非同期処理の共通設定 |
| `docker-compose.prod.yaml` | 本番ビルドとgatewayへの接続 |
| `client/Dockerfile` | 画面のdevelopment／productionビルド |
| `backend/webserver/Dockerfile` | APIのdevelopment／productionとworkersビルド |

画面は内部80番、APIは内部8000番で待ち受けます。ホストへのポート公開は
gatewayだけが行い、`shared-gateway-net`で接続します。
Socket.IOは画面用Nginxからバックエンドへ中継します。
gatewayの`/coco-annotator/api/`には`client_max_body_size 64m;`を設定します。
COCO JSONの取り込み時に適用される上限です。

ログインCookieは専用名`coco_annotator_session`を使用し、
Composeで`/coco-annotator/`配下に限定します。同一ホストの別アプリとの競合を防ぐためです。
Cookie設定の更新後は再ログインしてください。`SECRET_KEY`は再起動ごとに変更せず保持します。

## 起動

Dockerが利用できる環境で、既存ネットワークがなければ作成します。

```sh
docker network create shared-gateway-net
```

`.env`がない場合は`.env.example`をコピーし、`SECRET_KEY`を設定します。
この作業環境にはランダムなキーを設定した`.env`を用意しています。
サーバーに配備する際はサーバー側でも作成してください。

アプリのルートで実行します。

```sh
docker compose config --quiet
docker compose up -d --build
docker compose logs --tail 100 backend frontend
```

gatewayディレクトリで、起動済みなら設定検証後に再読み込みします。

```sh
docker compose exec gateway nginx -t
docker compose exec gateway nginx -s reload
```

未起動の場合はgatewayで `docker compose up -d` を実行します。
ブラウザで公開URLを開き、ログイン、画像表示、保存、出力を確認します。

## データと既存構成

画像は`datasets/`、学習モデルは`models/`をマウントします。
DBは名前付きボリューム`coco-annotator_mongodb_data`に保存します。
Ubuntuからコピーした`db/`は移行元の保管用です。運用中のDBには直接マウントしません。
Windows共有フォルダへのMongoDBファイルの直接保存は、WiredTigerの異常終了を起こす場合があります。

Ubuntuからの再移行では、元DBへの書き込みを停止して`mongodump`でバックアップし、
同じMongoDBバージョンの名前付きボリュームへ`mongorestore`で復元します。
全コレクションの実件数を照合してからアプリを接続してください。
起動中のDBフォルダをそのままscpする方法では整合性を保証できません。

今回の移行バックアップと件数記録は`backups/ubuntu-transfer-*/`にあります。
tar内の`coco-migration.archive.gz`は`mongorestore --gzip --archive=...`で復元できます。
バックアップはGit管理とDockerビルドの対象外です。
`docker compose down -v`はDBボリュームを削除するため、通常の停止には使用しません。

通常のフロントエンド開発では配信パスの既定値は`/`です。
productionビルドで`VUE_APP_BASE_PATH=/coco-annotator/`を指定します。
通常の起動入口は`compose.yaml`に統一しています。
