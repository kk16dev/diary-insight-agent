# Diary Insight Agent

GitHubにプッシュされた日記を自動抽出し、Amazon Bedrockで分析するフルスタックAWSアプリケーション。

## 概要

日記をGitHubリポジトリで管理している方向けの自動分析システムです。日記をプッシュすると、GitHub WebhookでLambdaが起動し、Amazon Bedrock (Claude Haiku 4.5) が以下を自動抽出します：

- 📚 **参考情報（References）**: 後で調べたい技術情報やリンク
- 💡 **アイデア（Ideas）**: ひらめきやTODO
- 🎯 **中長期目標（Goals）**: 将来の目標や計画

抽出結果はS3に保存され、Reactフロントエンドで日付ごとに閲覧できます。また、AgentCore統合により、チャットボット経由での検索・質問も可能です。

## 主要機能

### 1. 日記自動抽出（Phase 3）
- GitHub Webhookでリアルタイム抽出
- Claude Haiku 4.5による高精度な内容分析
- S3に構造化されたMarkdown形式で保存

### 2. Webフロントエンド（Phase 4）
- Cognito認証による安全なアクセス
- 日付ごとの抽出結果閲覧
- shadcn/uiによるモダンなUI

### 3. AgentCore統合（Phase 2）
- チャットボット経由で日記を検索
- LLMによる意味的な検索
- Gateway経由でツール実行

## システム構成

```
GitHub Push
    ↓
API Gateway (Webhook)
    ↓
Lambda (日記抽出)
    ↓
Bedrock (Claude Haiku 4.5)
    ↓
S3 (draft/{date}/)
    ↓
Frontend (React + Amplify)
```

詳細は [docs/project/ARCHITECTURE.md](docs/project/ARCHITECTURE.md) を参照。

## 前提条件

- **AWS アカウント**: CDKデプロイ権限
- **GitHub アカウント**: 日記リポジトリ（プライベートリポジトリ推奨）
- **ローカル環境**:
  - Node.js 18以上
  - Python 3.13
  - AWS CLI（認証情報設定済み）
  - Docker（Docker deploymentの場合のみ）

## セットアップ手順

### 1. リポジトリをクローン

```bash
git clone https://github.com/kk16dev/diary-insight-agent.git
cd diary-insight-agent
```

### 2. Secrets Managerにシークレットを作成

⚠️ **重要**: デプロイ前に以下のシークレットを手動作成してください。

```bash
# GitHub Personal Access Token (repo権限必要)
aws secretsmanager create-secret \
  --name diary-insight-agent/github-token \
  --secret-string '{"token":"ghp_YOUR_TOKEN_HERE"}'

# GitHub Webhook Secret (任意の文字列)
aws secretsmanager create-secret \
  --name diary-insight-agent/github-webhook-secret \
  --secret-string '{"webhook_secret":"YOUR_RANDOM_SECRET"}'
```

詳細は [docs/project/SECRETS_MANAGER_SETUP.md](docs/project/SECRETS_MANAGER_SETUP.md) を参照。

### 3. config.yamlを編集

```bash
cd infra-cdk
vi config.yaml
```

以下を自分の環境に合わせて編集：

```yaml
admin_user_email: your-email@example.com  # Cognitoユーザー用

github:
  owner: your-github-username  # 日記リポジトリのオーナー
  repo: your-diary-repo        # 日記リポジトリ名
```

### 4. CDKをブートストラップ（初回のみ）

```bash
cd infra-cdk
npm install
npx cdk bootstrap
```

### 5. デプロイ

```bash
npm run build
npx cdk deploy --all
```

デプロイには10〜15分かかります。完了後、以下の出力を確認：

- `WebhookUrl`: GitHub Webhookに設定するURL
- `FrontendUrl`: Reactアプリのアクセス先

### 6. GitHub Webhookを設定

1. GitHubリポジトリ → Settings → Webhooks → Add webhook
2. **Payload URL**: デプロイ出力の`WebhookUrl`を入力
3. **Content type**: `application/json`
4. **Secret**: Secrets Managerに保存した`webhook_secret`を入力
5. **Which events**: `Just the push event`を選択
6. **Active**: チェックを入れる

### 7. Cognitoユーザーを作成（admin_user_emailを設定していない場合）

```bash
aws cognito-idp admin-create-user \
  --user-pool-id <UserPoolId> \
  --username your-username \
  --user-attributes Name=email,Value=your-email@example.com \
  --temporary-password TempPassword123!
```

## 使い方

### 1. 日記をGitHubにプッシュ

日記は以下の形式で保存してください：

```
your-diary-repo/
└── daily/
    └── 2026/
        └── 04/
            └── 2026-04-20.md  ← この形式
```

### 2. 自動抽出を確認

プッシュ後、数秒〜数十秒でLambdaが起動し、Bedrockで抽出されます。

CloudWatch Logsで確認：
```bash
aws logs tail /aws/lambda/diary-insight-agent-diary-extraction --follow
```

### 3. フロントエンドで閲覧

1. デプロイ出力の`FrontendUrl`にアクセス
2. Cognitoでログイン
3. "Drafts"ページで日付ごとの抽出結果を閲覧

### 4. チャットボットで検索（オプション）

AgentCore Runtimeを使用して、日記の内容を検索できます。

詳細は [docs/GATEWAY.md](docs/GATEWAY.md) を参照。

## 開発方法

### ローカル開発

#### フロントエンド
```bash
cd frontend
npm install
npm run dev  # localhost:3000で起動
```

認証をスキップする場合は、`src/App.tsx`から`<AuthProvider>`を削除してください。

#### バックエンド（Lambda）
```bash
# 日記抽出Lambdaのテスト
cd batch/extract_diary
pytest tests/

# すべてのテスト実行
make all  # lint + format + test
```

### コードフォーマット・Lint

```bash
# Python
make lint    # ruff check
make format  # ruff format

# TypeScript
cd infra-cdk
npm run lint
```

## 技術スタック

### バックエンド
- **AWS CDK**: インフラストラクチャ定義
- **AWS Lambda**: サーバーレス実行環境（Python 3.13）
- **Amazon Bedrock**: Claude Haiku 4.5でLLM抽出
- **Amazon S3**: 抽出結果の保存
- **API Gateway**: Webhook + REST API

### フロントエンド
- **React 18**: UIフレームワーク
- **Vite**: ビルドツール
- **shadcn/ui**: UIコンポーネント
- **AWS Amplify**: ホスティング
- **Amazon Cognito**: 認証

### その他
- **AgentCore**: LLMエージェント実行基盤
- **GitHub API**: 日記ファイル取得

## ディレクトリ構成

```
diary-insight-agent/
├── infra-cdk/           # AWS CDKインフラ定義
│   ├── lib/             # CDKスタック（4スタック）
│   ├── lambdas/         # API Lambda（drafts, feedback）
│   └── config.yaml      # デプロイ設定
├── batch/               # 日記抽出Lambda
│   └── extract_diary/   # GitHub → Bedrock → S3
├── frontend/            # Reactフロントエンド
│   ├── src/
│   │   ├── components/  # UIコンポーネント
│   │   └── routes/      # ページ
│   └── vite.config.ts
├── gateway/             # AgentCore Gateway utilities
├── patterns/            # Agent実装（strands-single-agent）
├── tests/               # pytestテスト
└── docs/                # ドキュメント
```

## トラブルシューティング

### Webhook が動作しない

1. CloudWatch Logsを確認：
   ```bash
   aws logs tail /aws/lambda/diary-insight-agent-diary-extraction --follow
   ```

2. GitHub Webhookの配信履歴を確認（Settings → Webhooks → Recent Deliveries）

3. Secrets Managerにシークレットが正しく保存されているか確認

### フロントエンドでログインできない

1. Cognitoユーザーが作成されているか確認：
   ```bash
   aws cognito-idp list-users --user-pool-id <UserPoolId>
   ```

2. 初回ログイン時は仮パスワードを変更する必要があります

### Bedrock が使えない

- Geographic CRIS設定が必要です（東京・大阪リージョンのみ）
- AWSコンソール → Bedrock → Model access → Enable models

## 既知の制限事項

- **S3の`draft/`ディレクトリ**: 元々承認機能を想定していたが、現在は確定データを保存（機能的には問題なし）
- **GitHubリポジトリは全ユーザー共通**: マルチテナント対応には大規模な設計変更が必要
- **テスト環境向けの設定**: S3は`RemovalPolicy.DESTROY`のため、スタック削除時にデータも削除されます

## 参考ドキュメント

- [アーキテクチャ詳細](docs/project/ARCHITECTURE.md)
- [デプロイ手順](docs/DEPLOYMENT.md)
- [Secrets Manager設定](docs/project/SECRETS_MANAGER_SETUP.md)
- [AgentCore Gateway](docs/GATEWAY.md)
- [開発ガイド](CLAUDE.md)

## ライセンス

このプロジェクトは [Fullstack AgentCore Solution Template (FAST) v0.3.1](https://github.com/awslabs/fast-agentcore-template) をベースにしています。
