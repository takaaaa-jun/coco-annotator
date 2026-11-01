# ログインと接続先の確認

localhostと133.35.129.9は別のアプリ・DB・Cookieの接続先である。サーバーに登録したユーザーを使う場合は、COCOを http://133.35.129.9/coco-annotator/ 、check_annotatorを http://133.35.129.9/check_annotator/login で開く。片方だけlocalhostにしない。

check_annotatorとCOCOも認証は別であり、それぞれにログインする。アカウントやパスワードを複製する処理、DBの初期化、秘密鍵の変更は行わない。登録済みのサーバーアカウントをlocalhostで利用できないことを、パスワード不一致やアカウント未登録と混同しない。

修正では、認証を待たずにデータセットへ移動するwatcherを削除し、認証完了前の保護画面の描画を止める。失敗時はログイン画面に留まり、日本語でエラーを表示してローダーを閉じる。成功時は元の画像ID・データセットID・検索条件へ戻る。戻り先はアプリ内パスだけを許可する。接続先ホストをログイン画面に表示する。

## サーバーへの反映（利用者が実行する）

COCOリポジトリの作業ディレクトリでgit status --shortを確認し、ローカルの変更があれば先に整理する。以下は既存の本番Composeと.envを維持する。frontendのみの更新なのでバックエンドやDBの再作成は不要。

```sh
git fetch origin
git switch codex/58-auth-session
git pull --ff-only origin codex/58-auth-session
docker compose config --quiet
docker compose build frontend
docker compose up -d --no-deps frontend
```

ブラウザでCOCOのサーバーURLを強制再読み込みし、サーバーに登録済みのユーザーでログインする。間違ったパスワードのときはログイン画面に留まること、正しい入力では元の画像や検索結果へ戻ることを確認する。

## テスト

認証APIはモックし、実アカウントへログインせず、パスワードも変更しない。Jestでログイン失敗・ログイン待ち・成功後の検索条件復元・初期セッション確認・外部URLの拒否を検証する。
