# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## プロジェクト概要

GitHubから日記を自動抽出しBedrockで分析するフルスタックAWSアプリ（Python 3.13 + TypeScript + AWS CDK + React）。Fullstack AgentCore Solution Template (FAST) v0.3.1ベース。

## コマンド

### 開発・テスト
```bash
make all                    # lint + format + test
pytest tests/unit/          # unit test
pytest tests/integration/   # integration test
```

### フロントエンド
```bash
cd frontend
npm run dev                 # 開発サーバー起動（localhost:3000）
npm run build              # 本番ビルド
npm run lint               # ESLint
npx shadcn@latest add [component-name]  # shadcn/uiコンポーネント追加
```

### CDKデプロイ
```bash
cd infra-cdk
npm run build && npx cdk deploy --all   # ビルド＆デプロイ
npx cdk diff                            # 差分確認
npx cdk destroy --all                   # 削除
```

## 開発ワークフロー

1. GitHub issueを確認/作成（既存issueがない場合）
2. featureブランチを作成: `git checkout -b feature/issue-name`
3. 開発・コミット
4. PRを作成してマージ
5. マージ後、ローカルを更新

## アーキテクチャ

### システム構成
CDKスタック: Cognito（認証）→ Backend（AgentCore + API）→ Amplify（フロントエンド）+ Extraction（日記抽出Lambda）

日記抽出フロー: GitHub Webhook → Lambda → Bedrock (Claude Haiku 4.5) → S3

詳細は`docs/project/ARCHITECTURE.md`を参照。

### 主要ディレクトリ
```
infra-cdk/      # AWS CDK（4スタック: Cognito, Backend, Amplify, Extraction）
  └── config.yaml    # デプロイ設定（github owner/repo, tags）
batch/extract_diary/  # 日記抽出Lambda（GitHub → Bedrock → S3）
frontend/       # React + Vite + shadcn/ui + Cognito認証
gateway/        # AgentCore Gateway utilities
patterns/       # Agent実装（strands-single-agent使用中）
docs/           # ドキュメント（ARCHITECTURE.md参照）
tests/          # pytest（unit/, integration/）
```

## コードスタイル

**プロジェクト固有のルール**:
1. フェイルファスト原則（デフォルト値フォールバック禁止）
2. 名前付きパラメータを優先
3. 複雑な変更は事前計画＆承認後に実装
4. 新しいセクションで作業前に該当ディレクトリのREADME必読
5. `docs/`の内容を最優先（例: AgentCore Gateway → `docs/GATEWAY.md`参照）
6. grepでは常に`node_modules`と`cdk.out`を除外

## デプロイ設定

### 必須の事前準備
1. Secrets Manager作成: `github-token`, `github-webhook-secret`
2. `infra-cdk/config.yaml`編集: github owner/repo設定
3. 初回のみ: `cd infra-cdk && npx cdk bootstrap`

詳細は`docs/DEPLOYMENT.md`参照。

## 注意事項（プロジェクト固有のゴッチャ）

1. **Bedrock Geographic CRIS設定必須**: 東京・大阪リージョンのみ（`jp.anthropic.claude-haiku-4-5-*`使用）
2. **Secrets Manager事前作成必須**: `github-token`と`github-webhook-secret`がないとデプロイ失敗
3. **GitHub Webhook手動設定**: CDKデプロイ後、API Gateway URLをGitHubリポジトリ設定に手動追加が必要
4. **S3は`RemovalPolicy.DESTROY`**: テスト環境のためスタック削除時にデータも削除される
5. **フロントエンド認証テスト**: ローカル開発時は`src/App.tsx`から`<AuthProvider>`削除で認証スキップ可能
6. **Agent実装は`strands-single-agent`**: `patterns/langgraph-single-agent`もあるが現在未使用