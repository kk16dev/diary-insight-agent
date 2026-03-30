# 日記抽出バッチLambda

GitHubプライベートリポジトリから日記を取得し、LLMで3ジャンル（references, ideas, goals）に抽出してS3の `draft/` に保存する定期バッチLambda。

## 概要

- **トリガー**: EventBridge（毎日 2:00 JST）
- **処理内容**: 過去7日以内の未抽出日記を検出 → GitHub APIで取得 → LLM抽出 → S3保存
- **LLM**: Claude Haiku 4.5（Bedrock Converse API）
- **保存先**: S3 `draft/YYYY-MM-DD/`

## ファイル構成

```
batch/extract_diary/
├── lambda_function.py    # メインハンドラー
├── github_client.py      # GitHub API クライアント
├── llm_extractor.py      # LLM抽出ロジック
├── s3_handler.py         # S3保存ロジック
├── requirements.txt      # 依存関係
└── README.md             # このファイル
```

## 環境変数

| 変数名 | 説明 | 例 |
|--------|------|-----|
| `GITHUB_TOKEN_SECRET_NAME` | Secrets ManagerのGitHub PAT シークレット名 | `diary-insight-agent/github-token` |
| `GITHUB_OWNER` | GitHubリポジトリオーナー | `kk16dev` |
| `GITHUB_REPO` | GitHubリポジトリ名 | `personal-knowledge-base` |
| `S3_BUCKET_NAME` | S3バケット名 | `diary-insight-agent-insights` |
| `LOOKBACK_DAYS` | 遡る日数（デフォルト: 7） | `7` |

## 処理フロー

```
1. EventBridge起動（毎日 2:00 JST）
   ↓
2. 過去7日分の日記日付リストを生成
   ↓
3. S3の draft/ 一覧を取得
   ↓
4. 差分を計算（日記は存在するが、draftがない日付）
   ↓
5. 各未抽出日記について:
   a. GitHub APIで日記内容を取得
   b. LLM（Claude Haiku 4.5）で3ジャンル抽出
   c. S3の draft/YYYY-MM-DD/ に保存
   ↓
6. CloudWatch Logs に実行結果を記録
```

## S3保存形式

```
s3://diary-insight-agent-insights/
└── draft/
    └── YYYY-MM-DD/
        ├── metadata.json      # 抽出メタデータ
        ├── original.md        # 元の日記
        ├── references.md      # 抽出結果
        ├── ideas.md
        └── goals.md
```

## エラーハンドリング

| エラー種類 | 対応 |
|-----------|------|
| 日記が存在しない | スキップ（ログに記録、エラーにしない） |
| GitHub APIレート制限 | 例外を発生（翌日リトライ） |
| LLM呼び出しエラー | 例外を発生（翌日リトライ） |
| S3書き込みエラー | 例外を発生（翌日リトライ） |

## デプロイ

CDKで自動デプロイ（`infra-cdk/lib/extraction-stack.ts`）

## ローカルテスト

```bash
# 環境変数を設定
export GITHUB_TOKEN_SECRET_NAME=diary-insight-agent/github-token
export GITHUB_OWNER=kk16dev
export GITHUB_REPO=personal-knowledge-base
export S3_BUCKET_NAME=diary-insight-agent-insights
export LOOKBACK_DAYS=7

# 実行
python3 lambda_function.py
```

## ログ

CloudWatch Logs Group: `/aws/lambda/DiaryExtractionLambda`

**成功時**:
```
抽出完了: 2026-03-22, references=2, ideas=1, goals=0
```

**スキップ時**:
```
日記が存在しないためスキップ: 2026-03-21
```

**エラー時**:
```
抽出失敗: 2026-03-20, error=...
```