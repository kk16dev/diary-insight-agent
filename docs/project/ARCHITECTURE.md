# Diary Insight Agent - アーキテクチャドキュメント

## 概要

このドキュメントは、Diary Insight Agentのシステムアーキテクチャを図解します。
本システムは、GitHubリポジトリから日記を自動抽出し、Amazon Bedrockで分析してS3に保存するフルスタックAWSアプリケーションです。

---

## 1. システム全体構成図

```mermaid
graph TB
    subgraph "ユーザー"
        User[ユーザー<br/>ブラウザ]
        GitCommit[GitHub Commit<br/>日記の更新]
    end

    subgraph "AWS CloudFront + Amplify"
        Amplify[Amplify Hosting<br/>React Frontend]
    end

    subgraph "認証"
        Cognito[Cognito User Pool<br/>ユーザー認証]
        MachineClient[Machine Client<br/>M2M OAuth2]
    end

    subgraph "Backend Stack"
        subgraph "AgentCore"
            Gateway[AgentCore Gateway<br/>ツール統合]
            Runtime[AgentCore Runtime<br/>Agent実行環境]
        end

        FeedbackAPI[API Gateway<br/>Feedback API]
        FeedbackLambda[Lambda<br/>Feedback処理]
        DynamoDB[(DynamoDB<br/>アプリケーションDB)]
    end

    subgraph "Extraction Stack"
        WebhookAPI[API Gateway<br/>Webhook Endpoint]
        ExtractionLambda[Lambda<br/>日記抽出処理]
        Bedrock[Amazon Bedrock<br/>Claude Haiku 4.5]
        S3[(S3 Bucket<br/>Insights Storage)]
        Secrets[Secrets Manager<br/>GitHub Token/Secret]
    end

    subgraph "外部サービス"
        GitHub[GitHub API<br/>プライベートリポジトリ]
    end

    %% ユーザーフロー
    User -->|HTTPS| Amplify
    Amplify -->|認証| Cognito
    Amplify -->|API呼び出し| Gateway
    Amplify -->|フィードバック送信| FeedbackAPI

    %% フィードバック処理
    FeedbackAPI --> FeedbackLambda
    FeedbackLambda --> DynamoDB

    %% AgentCore
    Gateway -->|M2M Auth| MachineClient
    Gateway --> Runtime
    Runtime -->|Bedrock呼び出し| Bedrock

    %% 日記抽出フロー
    GitCommit -->|Webhook| WebhookAPI
    WebhookAPI --> ExtractionLambda
    ExtractionLambda -->|シークレット取得| Secrets
    ExtractionLambda -->|日記取得| GitHub
    ExtractionLambda -->|LLM抽出| Bedrock
    ExtractionLambda -->|保存| S3

    style Amplify fill:#FF9900
    style Cognito fill:#DD344C
    style Gateway fill:#FF9900
    style Runtime fill:#FF9900
    style Bedrock fill:#01A88D
    style S3 fill:#569A31
    style WebhookAPI fill:#FF4F8B
    style ExtractionLambda fill:#FF9900
```

---

## 2. CDKスタック構成と依存関係

```mermaid
graph LR
    subgraph "Main Stack"
        Main[FastMainStack<br/>オーケストレーター]
    end

    subgraph "Nested Stacks"
        Cognito[CognitoStack<br/>認証基盤]
        Backend[BackendStack<br/>AgentCore + API]
        Amplify[AmplifyHostingStack<br/>フロントエンド]
        Extraction[ExtractionStack<br/>日記抽出]
    end

    Main --> Cognito
    Main --> Backend
    Main --> Amplify
    Main --> Extraction

    Cognito -->|User Pool ID<br/>Client ID| Backend
    Backend -->|Insights Bucket| Extraction
    Backend -->|Runtime ARN<br/>API Endpoint| Amplify

    style Main fill:#232F3E
    style Cognito fill:#DD344C
    style Backend fill:#FF9900
    style Amplify fill:#FF9900
    style Extraction fill:#527FFF
```

**デプロイ順序**:
1. `CognitoStack` - User Pool、OAuth2設定
2. `BackendStack` - AgentCore Gateway/Runtime、DynamoDB、Feedback API
3. `AmplifyHostingStack` - Reactフロントエンドホスティング
4. `ExtractionStack` - GitHub Webhook受信、日記抽出Lambda

---

## 3. 日記抽出フロー（詳細）

```mermaid
sequenceDiagram
    participant User as ユーザー
    participant GitHub as GitHub
    participant Webhook as API Gateway<br/>(Webhook)
    participant Lambda as 日記抽出Lambda
    participant Secrets as Secrets Manager
    participant Bedrock as Amazon Bedrock<br/>(Claude Haiku 4.5)
    participant S3 as S3 Bucket

    User->>GitHub: git commit & push<br/>(日記を更新)
    GitHub->>Webhook: POST /webhook<br/>(Webhook通知)
    Webhook->>Lambda: イベント転送

    Lambda->>Secrets: GetSecretValue<br/>(GitHub Token/Secret)
    Secrets-->>Lambda: 認証情報

    Lambda->>Lambda: Webhook署名検証

    Lambda->>GitHub: GET /repos/.../commits<br/>(コミット差分取得)
    GitHub-->>Lambda: 日記ファイル差分

    Lambda->>Bedrock: InvokeModel<br/>(日記抽出プロンプト)
    Bedrock-->>Lambda: 抽出結果<br/>(references, ideas, goals)

    Lambda->>S3: PutObject<br/>(draft/YYYY-MM-DD/)
    S3-->>Lambda: 保存完了

    Lambda-->>Webhook: 200 OK
    Webhook-->>GitHub: Webhook応答
```

**処理時間**: 約30秒〜1分（Bedrock呼び出しを含む）

---

## 4. データフロー図

```mermaid
flowchart LR
    subgraph "入力"
        A[GitHub Commit<br/>日記Markdown]
    end

    subgraph "抽出処理"
        B[Lambda Handler]
        C{Webhook署名<br/>検証}
        D[GitHub API<br/>差分取得]
        E[Bedrock LLM<br/>Claude Haiku 4.5]
    end

    subgraph "出力先"
        F[(S3: draft/<br/>YYYY-MM-DD/)]
    end

    subgraph "S3保存形式"
        G[metadata.json<br/>抽出メタデータ]
        H[original.md<br/>元の日記]
        I[references.md<br/>参考文献]
        J[ideas.md<br/>アイデア]
        K[goals.md<br/>目標]
    end

    A --> B
    B --> C
    C -->|OK| D
    C -->|NG| L[403 Forbidden]
    D --> E
    E --> F
    F --> G
    F --> H
    F --> I
    F --> J
    F --> K

    style E fill:#01A88D
    style F fill:#569A31
```

**S3保存パス**:
```
s3://diary-insight-agent-insights/
└── draft/
    └── YYYY-MM-DD/
        ├── metadata.json      # 抽出日時、LLMモデル、統計情報
        ├── original.md        # 元の日記（GitHub取得内容）
        ├── references.md      # 参考文献・リンク
        ├── ideas.md           # アイデア・気づき
        └── goals.md           # 目標・タスク
```

---

## 5. AgentCore Gateway構成図

```mermaid
graph TB
    subgraph "AgentCore Gateway"
        Gateway[Gateway API<br/>ツールルーター]

        subgraph "Lambda Tools"
            Tool1[Tool Lambda 1<br/>example_tool]
            Tool2[Tool Lambda 2<br/>custom_tool]
        end
    end

    subgraph "AgentCore Runtime"
        Runtime[Runtime<br/>Agent実行環境]
        Agent[Agent Container<br/>ZIP or Docker]
    end

    Frontend[Frontend<br/>React App] -->|API呼び出し| Gateway
    Gateway --> Tool1
    Gateway --> Tool2

    Runtime --> Agent
    Agent -->|ツール呼び出し| Gateway

    Gateway -->|M2M Auth| MachineClient[Machine Client<br/>OAuth2]

    style Gateway fill:#FF9900
    style Runtime fill:#527FFF
    style Agent fill:#232F3E
```

**Gatewayの役割**:
- Lambdaベースのツールを動的に登録
- M2M認証（OAuth2 Client Credentials）
- AgentCore Runtimeからのツール呼び出しをルーティング

---

## 6. 主要AWSリソース一覧

| リソース種別 | 用途 | スタック |
|-------------|------|---------|
| **Cognito User Pool** | ユーザー認証、OAuth2 | CognitoStack |
| **Lambda (Extraction)** | 日記抽出処理（Python 3.13） | ExtractionStack |
| **Lambda (Feedback)** | フィードバック処理 | BackendStack |
| **Lambda (Gateway Tools)** | AgentCoreツール実装 | BackendStack |
| **API Gateway (Webhook)** | GitHub Webhook受信 | ExtractionStack |
| **API Gateway (Feedback)** | フィードバックAPI | BackendStack |
| **S3 Bucket (Insights)** | 日記抽出結果保存 | BackendStack |
| **DynamoDB Table** | アプリケーションデータ | BackendStack |
| **Secrets Manager** | GitHub Token/Webhook Secret | 手動作成 |
| **Bedrock (Claude Haiku 4.5)** | 日記抽出LLM | ExtractionStack |
| **AgentCore Gateway** | ツール統合基盤 | BackendStack |
| **AgentCore Runtime** | Agent実行環境 | BackendStack |
| **Amplify Hosting** | Reactフロントエンド | AmplifyHostingStack |

---

## 7. セキュリティ構成

```mermaid
graph TB
    subgraph "認証・認可"
        A[Cognito User Pool<br/>ユーザー認証]
        B[Machine Client<br/>M2M OAuth2]
        C[API Gateway<br/>認証統合]
    end

    subgraph "シークレット管理"
        D[Secrets Manager<br/>GitHub Token]
        E[Secrets Manager<br/>Webhook Secret]
    end

    subgraph "IAMロール"
        F[Lambda実行ロール]
        G[Bedrock呼び出し権限]
        H[S3読み書き権限]
    end

    A --> C
    B --> C
    D --> F
    E --> F
    F --> G
    F --> H

    style A fill:#DD344C
    style D fill:#DD344C
    style E fill:#DD344C
```

**セキュリティベストプラクティス**:
- ✅ Secrets ManagerでGitHub認証情報を管理
- ✅ Webhook署名検証（HMAC SHA-256）
- ✅ S3バケットはプライベート（BlockPublicAccess）
- ✅ Lambda実行ロールは最小権限（Bedrock、S3のみ）
- ✅ Geographic CRIS（東京・大阪リージョン限定）

---

## 8. Bedrock権限設定（Geographic CRIS）

```mermaid
graph LR
    subgraph "東京リージョン (ap-northeast-1)"
        A[Inference Profile<br/>Claude Haiku 4.5]
        B[Foundation Model<br/>東京]
    end

    subgraph "大阪リージョン (ap-northeast-3)"
        C[Foundation Model<br/>大阪]
    end

    Lambda[日記抽出Lambda<br/>ap-northeast-1] -->|InvokeModel| A
    A -.->|ルーティング| B
    A -.->|ルーティング| C

    style A fill:#01A88D
    style B fill:#01A88D
    style C fill:#01A88D
```

**Geographic CRIS設定**:
- Inference Profile: `jp.anthropic.claude-haiku-4-5-20251001-v1:0`
- Destination Regions: 東京（ap-northeast-1）、大阪（ap-northeast-3）
- IAMポリシーで両方のリージョンへのアクセスを許可

---

## 9. デプロイメントフロー

```mermaid
flowchart TB
    Start([開発者]) --> Config[config.yaml編集]
    Config --> Secrets[Secrets Manager設定<br/>GitHub Token/Secret]
    Secrets --> CDKBuild[npm run build]
    CDKBuild --> CDKDeploy[cdk deploy --all]

    CDKDeploy --> DeployCognito[CognitoStack<br/>デプロイ]
    DeployCognito --> DeployBackend[BackendStack<br/>デプロイ]
    DeployBackend --> DeployAmplify[AmplifyHostingStack<br/>デプロイ]
    DeployBackend --> DeployExtraction[ExtractionStack<br/>デプロイ]

    DeployExtraction --> ConfigWebhook[GitHub Webhook設定<br/>手動]
    ConfigWebhook --> Test[動作確認]
    Test --> Done([完了])

    style Start fill:#232F3E
    style Secrets fill:#DD344C
    style Done fill:#569A31
```

**手動設定が必要な項目**:
1. Secrets Managerに`github-token`と`github-webhook-secret`を作成
2. GitHub Webhook URLをリポジトリ設定に追加（API Gateway URLを使用）

---

## 10. コスト最適化

| リソース | 月間コスト概算 | 最適化施策 |
|---------|--------------|----------|
| Lambda（日記抽出） | $0.20 | 実行時間15分、月間30回 |
| Bedrock（Claude Haiku 4.5） | $0.50 | Input: 2K tokens, Output: 1K tokens × 30回 |
| S3（Insights Storage） | $0.05 | 標準ストレージ、1GB未満 |
| API Gateway | $0.01 | 月間30リクエスト |
| DynamoDB | $0.00 | オンデマンド、低トラフィック |
| Amplify Hosting | $0.00 | 無料枠内 |
| **合計** | **$0.76/月** | |

**コスト削減のポイント**:
- ✅ API Gatewayキャッシュ無効化（不要な固定費削減）
- ✅ CloudWatch Logs保持期間: 1週間
- ✅ S3バケット: `RemovalPolicy.DESTROY`（テスト環境）
- ✅ CDKリソースタグでコスト追跡

---

## 11. モニタリング・ログ

| ログ種別 | ロググループ | 保持期間 |
|---------|------------|---------|
| 日記抽出Lambda | `/aws/lambda/diary-insight-agent-diary-extraction` | 7日 |
| Feedback Lambda | `/aws/lambda/diary-insight-agent-feedback-*` | 7日 |
| API Gateway（Webhook） | API Gateway自動生成 | 7日 |

**モニタリング指標**:
- Lambda実行時間（目標: <60秒）
- Bedrock呼び出しエラー率（目標: <1%）
- S3保存成功率（目標: 100%）

---

## 参考リンク

- [AWS CDK Documentation](https://docs.aws.amazon.com/cdk/)
- [Amazon Bedrock User Guide](https://docs.aws.amazon.com/bedrock/)
- [AgentCore Gateway Documentation](./GATEWAY.md)
- [Deployment Guide](./DEPLOYMENT.md)
- [Local Development Guide](./LOCAL_DEVELOPMENT.md)

---

**最終更新**: 2026-04-18
**バージョン**: v0.3.1
