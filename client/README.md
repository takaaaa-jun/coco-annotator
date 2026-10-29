# Webクライアント

Vue 2とPaper.jsを使用した画像アノテーション画面です。
起動・配備方法は[ルートのREADME](../README.md)を参照してください。

- `Dockerfile`の`production`対象でビルドし、Nginxの内部80番で配信します。
- 配信パスは`/coco-annotator/`です。
- `nginx.conf`は静的ファイルとSocket.IOの中継を設定します。
- APIはgatewayからバックエンドへ転送します。
- 依存関係の変更時は`package.json`と`package-lock.json`を揃えてください。
- Vue CLI 3.1.4の配信パス設定名は`baseUrl`です。

画面を変更した後は、リポジトリのルートで再ビルドします。

```sh
docker compose up -d --build frontend
```
