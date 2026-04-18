# Claude Code環境整備 - 作業コンテキスト

## 📍 現在の状況

**ブランチ**: `feature/claudecode-setup`
**作業開始日**: 2026-04-18

### ✅ 完了した作業

1. **feature/claudecode-setupブランチを作成** - Claude Code環境整備用の作業ブランチ
2. **docs/ARCHITECTURE.mdを作成** - システムアーキテクチャドキュメント（Mermaid図付き）
   - システム全体構成図（AWS構成図）
   - CDKスタック構成と依存関係
   - 日記抽出フロー（シーケンス図）
   - データフロー図
   - AgentCore Gateway構成図
   - セキュリティ構成
   - Bedrock権限設定（Geographic CRIS）
   - デプロイメントフロー
   - コスト最適化
   - モニタリング・ログ

---

## 🎯 次にやるべきこと

### Phase 1: Claude Codeチュートリアル確認（推奨）

Claude Codeの公式ドキュメントを確認して、CLAUDE.mdとskillsのベストプラクティスを学ぶ。

**参考リンク**:
- Claude Code公式ドキュメント: https://docs.anthropic.com/claude-code
- CLAUDE.mdガイド: https://docs.anthropic.com/claude-code/guides/claude-md
- Skillsガイド: https://docs.anthropic.com/claude-code/guides/skills

### Phase 2: CLAUDE.mdを作成

プロジェクト全体の概要をClaude Code向けにまとめる。

**含めるべき内容**:
- プロジェクト概要（Diary Insight Agentの説明）
- アーキテクチャの説明（スタック構成）
- 主要な機能
- **AIアシスタント向けルール**（vibe-context/から統合）
  - `vibe-context/coding-conventions.md`
  - `vibe-context/development-best-practices.md`
  - `vibe-context/AGENTS.md`
- ディレクトリ構造
- 開発ワークフロー
- デプロイメント手順
- トラブルシューティング

**重要な既存ファイル**:
- `vibe-context/coding-conventions.md` - コーディング規約
- `vibe-context/development-best-practices.md` - 開発ベストプラクティス
- `infra-cdk/README.md` - CDKデプロイメントガイド
- `docs/ARCHITECTURE.md` - アーキテクチャドキュメント（今回作成）
- `batch/extract_diary/README.md` - 日記抽出バッチの説明

**言語**: **日本語**で作成すること（ユーザーからの要望）

### Phase 3: .claude/skills/を作成

プロジェクト固有のスキルを定義する。

**推奨スキル**:
1. **cdk-deploy** - CDKデプロイメント管理
   - `cdk deploy --all`の実行
   - スタック差分確認
   - デプロイ前チェック

2. **diary-extraction** - 日記抽出機能の管理
   - Lambdaログ確認
   - S3バケット確認
   - Webhook設定確認

3. **architecture-docs** - アーキテクチャドキュメント更新
   - Mermaid図の更新
   - ARCHITECTURE.mdの更新

### Phase 4: コミット＆マージ

```bash
git add CLAUDE.md .claude/
git commit -m "feat: Claude Code環境整備（CLAUDE.md + skills）"
git checkout master
git merge feature/claudecode-setup
git branch -d feature/claudecode-setup
```

---

## 📂 プロジェクト構造（参考）

```
.
├── CLAUDE.md                 # 📝 作成予定（Phase 2）
├── CONTEXT.md                # 📝 このファイル
├── .claude/                  # 📝 作成予定（Phase 3）
│   └── skills/
│       ├── cdk-deploy.md
│       ├── diary-extraction.md
│       └── architecture-docs.md
├── batch/
│   └── extract_diary/        # 日記抽出Lambda
├── docs/
│   ├── ARCHITECTURE.md       # ✅ 作成完了（Phase 1）
│   ├── GATEWAY.md
│   ├── DEPLOYMENT.md
│   └── ...
├── frontend/                 # React Frontend
├── gateway/                  # AgentCore Gateway utilities
├── infra-cdk/               # AWS CDK
│   ├── lib/
│   │   ├── backend-stack.ts
│   │   ├── cognito-stack.ts
│   │   ├── extraction-stack.ts
│   │   └── fast-main-stack.ts
│   └── config.yaml
├── patterns/                # AgentCore agent patterns
├── vibe-context/            # 既存のAI向けガイドライン
│   ├── AGENTS.md
│   ├── coding-conventions.md
│   └── development-best-practices.md
└── pyproject.toml
```

---

## 🔑 重要な設定情報

### プロジェクト基本情報
- **プロジェクト名**: Diary Insight Agent
- **ベーステンプレート**: Fullstack AgentCore Solution Template (FAST) v0.3.1
- **メインブランチ**: `master`
- **現在のブランチ**: `feature/claudecode-setup`

### 技術スタック
- **言語**: Python 3.13, TypeScript
- **インフラ**: AWS CDK
- **LLM**: Amazon Bedrock (Claude Haiku 4.5)
- **フロントエンド**: React (Amplify Hosting)
- **認証**: Cognito User Pool + OAuth2

### CDKスタック構成
1. `CognitoStack` - 認証基盤
2. `BackendStack` - AgentCore Gateway/Runtime + DynamoDB + Feedback API
3. `AmplifyHostingStack` - Reactフロントエンド
4. `ExtractionStack` - GitHub Webhook + 日記抽出Lambda

---

## 💡 次回セッションでの作業開始コマンド

次回、Claude Codeを起動したら、以下のように指示してください：

```
次の作業を進めてください
```

このコマンドだけで、このCONTEXT.mdを読み込んで作業を再開します。

---

## 📚 参考ドキュメント

### プロジェクト内ドキュメント
- `docs/ARCHITECTURE.md` - システムアーキテクチャ（今回作成）
- `docs/GATEWAY.md` - AgentCore Gateway説明
- `docs/DEPLOYMENT.md` - デプロイメント手順
- `docs/LOCAL_DEVELOPMENT.md` - ローカル開発
- `infra-cdk/README.md` - CDKインフラ説明
- `batch/extract_diary/README.md` - 日記抽出バッチ説明

### 外部ドキュメント
- Claude Code: https://docs.anthropic.com/claude-code
- AWS CDK: https://docs.aws.amazon.com/cdk/
- Amazon Bedrock: https://docs.aws.amazon.com/bedrock/

---

## ⚠️ 注意事項

1. **CLAUDE.mdは日本語で作成すること** - ユーザーからの要望
2. **チュートリアル確認を推奨** - CLAUDE.mdとskillsのベストプラクティスを学んでから作成
3. **既存のvibe-contextを統合** - coding-conventions.md、development-best-practices.md、AGENTS.mdの内容をCLAUDE.mdに統合
4. **Makefileを活用** - `make all`でlinting + unit tests実行
5. **Git履歴を綺麗に** - 作業完了後にmasterへマージしてブランチ削除

---

**最終更新**: 2026-04-18
**作成者**: Claude Sonnet 4.5
