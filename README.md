# pii-masking-filter

Microsoft Presidioを利用した、日本語の個人情報（PII）をマスキングするREST APIサーバーです。

`pii_masking/` のマスキング処理は、
[`kouki6951/pii-masking-chat`](https://github.com/kouki6951/pii-masking-chat/tree/main/pii_chat).
の実装を移植しています。マスキング専用であり、チャットUI、外部AI API、
元の個人情報に戻すための対応表は含みません。

## エンドポイント

- `GET /health` — 稼働確認
- `POST /mask` — 送信されたテキスト内の日本語PIIをマスキング

## ローカルでの起動

```bash
uv sync --locked
uv run --no-sync uvicorn app:app --host 127.0.0.1 --port 8000
```

Python 3.10以上と [uv](https://docs.astral.sh/uv/getting-started/installation/) を使用し、
リポジトリのルートで実行してください。仮想環境 `.venv` はuvが作成します。
依存定義は `pyproject.toml`、解決済みのバージョンは `uv.lock` で管理し、
requirements.txt は使用しません。依存を変更した場合は `uv lock` でロックを更新してください。
spaCy日本語モデル `ja_core_news_lg` は必須依存として `uv sync` で事前インストールします。
開発時は起動コマンドに `--reload` を追加できます。
リクエスト処理中にモデルをダウンロードすることはありません。
依存パッケージとモデルのインストールにはインターネット接続が必要です。
インストール後は上記の `uv run --no-sync` で依存の再同期をせず、オフラインで起動できます。

## Dockerでの起動

DockerとDocker Composeを使用し、リポジトリのルートで実行してください。

```bash
touch .env
docker compose up --build --wait
curl http://127.0.0.1:8000/health
```

`POST /mask` も以下の使用例で確認できます。停止する場合は `docker compose down` を実行してください。
ビルド時に依存と日本語モデルをインストールするため、インターネット接続が必要です。
ビルド済みのイメージは実行時にダウンロードせず、非rootユーザーで起動します。
開発用reloadは有効にしていません。Composeはポート8000をローカルホストだけに公開します。
Composeは `env_file` でリポジトリの `.env` をapiコンテナの環境変数として読み込みます。
起動前に `.env` を作成してください（設定不要なら上記のとおり空ファイルで構いません）。
設定例は「設定とフィルタの選択」を参照してください。`.env.example` はありません。
未設定の項目はアプリの既定値を使います。Composeの `environment` に明示した値は
`env_file` より優先されますが、現在は設定を上書きする項目を置いていません。
ホストの環境変数は自動転送されないため、従来の `PII_SCORE_THRESHOLD` の
ホスト側上書きも `.env` または `environment` で指定してください。
`.env` はGitの管理対象外で、イメージにも含めません。

Dockerfileだけで起動する場合:

```bash
docker build -t pii-masking-filter .
docker run --rm -p 127.0.0.1:8000:8000 pii-masking-filter
```

## 使用例

```bash
curl -X POST http://127.0.0.1:8000/mask \
  -H 'Content-Type: application/json' \
  -d '{"text":"電話は090-1234-5678です。メールはtaro@example.comです。"}'
```

```json
{
  "masked_text": "電話は<電話番号_1>です。メールは<メールアドレス_1>です。",
  "has_pii": true,
  "entity_count": 2
}
```

`GET /health` は `{"status":"ok"}`（HTTP 200）を返します。プロセスの稼働確認用であり、
モデルが利用可能かどうかは確認しません。公開するルートはこの2つのみです。
対話型APIドキュメントとOpenAPIエンドポイントは無効にしています。

`POST /mask` は文字列フィールド `text` のみを受け付けます。
長さは1〜1,048,576文字（1M＝1024²）です。バイト数ではなく文字数の上限です。
不明なフィールドや不正な入力・JSONには、HTTP 422と `{"detail":"invalid_request"}` を返します。
モデルの未インストールや不正な設定には、HTTP 503と `{"detail":"masker_unavailable"}` を返します。
処理に失敗した場合は、HTTP 500と `{"detail":"masking_failed"}` を返します。
エラーレスポンスに送信されたテキストを含めることはありません。

置換文字列は日本語ラベルとリクエスト内の連番で構成されます。
同じ種類・値のPIIには同じ置換文字列を使います。
`entity_count` は異なる値の数ではなく、検出された出現箇所の数です。
PIIが検出されなかったテキストは、そのまま返します。

解析はUTF-8で32KiB（32 × 1024バイト）を目安に、行単位でまとめて行います。
行区切りはPythonの `str.splitlines()` に従います（LF/CRLFやUnicode行区切りなど）。
改行、空行、空白、末尾の改行の有無を保持し、結果を元の順序で
区切り文字を追加せず結合します。単一行が32KiBを超える場合は、その行を分割せず
1つの大きなチャンクとして解析します。チャンク境界をまたぐPIIの認識はできません。
置換文字列の連番と同じ値の対応はチャンクをまたいでリクエスト全体で共有します。
途中で解析に失敗した場合も、部分的な結果は返さず上記のHTTP 500を返します。

## 設定とフィルタの選択

リポジトリのルートに置いた `.env` または環境変数で設定します。
両方に同じ設定がある場合は、環境変数を優先します。`.env` はGitの管理対象外です。

- `SPACY_MODEL`: インストール済みの日本語spaCyモデル（既定値: `ja_core_news_lg`）。
- `PII_SCORE_THRESHOLD`: 検出スコアの閾値。0〜1（既定値: `0.4`）。
- `PII_FILTERS`: 適用するPII種別をカンマ区切りで指定します。
  未設定の場合は従来どおり全フィルタを適用します。名前は下表の大文字表記で指定してください。
  空文字、不明な種別、末尾のカンマなどは設定エラーとなります。

例えば、電話番号とメールアドレスだけを対象にする `.env` は次のとおりです。

```dotenv
PII_FILTERS=PHONE_NUMBER,EMAIL_ADDRESS
SPACY_MODEL=ja_core_news_lg
PII_SCORE_THRESHOLD=0.4
```

環境変数で指定する場合:

```bash
PII_FILTERS=PHONE_NUMBER,EMAIL_ADDRESS uv run --no-sync uvicorn app:app --host 127.0.0.1 --port 8000
```

| フィルタ名 | 対象 |
| --- | --- |
| `PERSON` | 氏名（spaCy NER・敬称パターン） |
| `LOCATION` | 地名 |
| `ORGANIZATION` | 組織名 |
| `NRP` | 国籍・宗教・政治的集団 |
| `DATE_TIME` | 日時 |
| `EMAIL_ADDRESS` | メールアドレス |
| `PHONE_NUMBER` | 電話番号 |
| `CREDIT_CARD` | クレジットカード番号 |
| `IP_ADDRESS` | IPアドレス |
| `URL` | URL |
| `JP_MY_NUMBER` | マイナンバー |
| `JP_POSTAL_CODE` | 郵便番号 |
| `JP_ADDRESS` | 住所 |
| `JP_PASSPORT` | パスポート番号 |
| `JP_DRIVERS_LICENSE` | 運転免許証番号 |
| `JP_BANK_ACCOUNT` | 銀行口座番号 |

**選択しなかった種類のPIIはマスキングされず、レスポンスに残ります。**
フィルタの選択はリクエストごとではなく、サーバー全体に適用されます。
設定を変更した場合はサーバーを再起動してください。

モデルと設定は、最初のマスキング時にワーカーごとに1回読み込み、以後再利用します。
初回のリクエストは遅くなる場合があるため、実際のトラフィックを流す前に
架空のテキストで `/mask` を呼び出してください。ワーカーを増やすと、
それぞれにモデル用のメモリが必要です。大きな入力ほど処理時間とメモリ消費が増えます。

## テスト

```bash
uv sync --frozen
uv run --no-sync python -m pytest -q
```

テストでは重いspaCyモデルの読み込みだけを置き換え、APIと実際のPresidio認識器を検証します。
`--frozen` はコミット済みの `uv.lock` をそのまま使用します。
依存同期時には必須の日本語モデルもインストールしますが、通常のテストでは読み込みません。
実際の日本語モデルも確認する場合は、サーバーを起動して上記の使用例を実行してください。

ローカルまたはComposeで起動済みのサーバーを検証する場合は、
電話番号とメールアドレスのフィルタを有効にして次を実行してください。
`PII_TEST_URL` を指定しない通常のテストでは、このスモークテストはスキップされます。

```bash
PII_TEST_URL=http://127.0.0.1:8000 uv run --no-sync python -m pytest -q tests/test_runtime.py
```

## デプロイとプライバシー

アプリケーションはリクエスト本文、元のPII、復元用の対応表をログに記録しません。
入力検証や処理のエラーにもPIIを含めません。Uvicornの標準アクセスログには、
本文ではなくパスとステータスコードが記録されます。
URLやクエリパラメータにはPIIを含めないでください。
リバースプロキシや監視ツールでも、本文を記録しないよう設定してください。

API自体に認証機能はありません。信頼できるネットワーク内、または認証・TLSを備えた
リバースプロキシの背後で使用してください。プロキシ側でリクエスト本文のサイズ制限、
レート制限、タイムアウトを設定してください。文字数の上限はJSON解析後に検証されるため、
本文のサイズ制限の代わりにはなりません。本番では開発用の `--reload` を使用しないでください。

検出はルールやモデルによる推定であり、すべてのPIIを除去できる保証はありません。
匿名化データとして利用する前に、実際の用途に近い日本語テキストで精度を確認してください。
検出されなかったPIIは `masked_text` に残ります。
