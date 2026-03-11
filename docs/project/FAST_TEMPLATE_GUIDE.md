# FAST テンプレート構成ガイド

Fullstack AgentCore Solution Template (FAST) の構成を理解するためのドキュメント。

## 1. 主要コンポーネントと各役割

### ディレクトリ構成

```
diary-insight-agent/
├── frontend/          # React チャット UI
├── patterns/          # エージェント本体（ビジネスロジック）
├── gateway/           # ツール連携層（MCP プロトコル経由、Lambda 実行）
├── tools/             # エージェント内蔵ツール（同一プロセスで実行）
├── infra-cdk/         # AWS インフラ定義（CDK）
├── scripts/           # デプロイスクリプト
└── config.yaml        # 全体設定
```

### CDK ネストスタック構成

| スタック | 役割 |
|----------|------|
| **FastMainStack** | オーケストレーター（子スタックを束ねる） |
| **CognitoStack** | 認証基盤（OAuth2 Authorization Code + Client Credentials） |
| **AmplifyHostingStack** | フロントエンドホスティング |
| **BackendStack** | AgentCore Runtime + Gateway + Feedback API + DynamoDB |

---

## 2. 処理の流れ（入口から出口まで）

```
ユーザー
  │
  ▼
[フロントエンド] React Chat UI
  │  frontend/src/components/chat/ChatInterface.tsx
  │  Cognito でログイン → access_token 取得
  │
  ▼  POST（SSE ストリーミング）
[AgentCore Runtime] ── JWT 検証 → user_id 抽出
  │
  ▼
[Agent] patterns/strands-single-agent/basic_agent.py
  │  Bedrock LLM を呼び出し
  │  会話履歴は Memory 統合で自動管理
  │
  ├─→ [Gateway] (MCP プロトコル、M2M認証)
  │      │
  │      ▼
  │   [Tool Lambda] gateway/tools/sample_tool/
  │      結果を Agent に返す
  │
  ├─→ [ローカルツール] tools/code_interpreter/
  │      Agent と同一プロセスで実行
  │
  ▼  SSE イベントストリーム
[フロントエンド] リアルタイムでチャット表示
```

---

## 3. 自分が触るべき場所と触らない方がいい場所

### 触るべき場所（カスタマイズ対象）

| ファイル | 理由 |
|----------|------|
| `patterns/strands-single-agent/basic_agent.py` | エージェントのプロンプト・ツール構成・ビジネスロジック |
| `gateway/tools/` | 新しいリモートツールの追加（1ツール = 1 Lambda） |
| `gateway/tools/*/tool_spec.json` | ツールの入出力スキーマ定義 |
| `infra-cdk/config.yaml` | スタック名・パターン・デプロイタイプ |
| `infra-cdk/lib/backend-stack.ts` | Gateway Target や新 Lambda の追加 |
| `frontend/src/components/chat/ChatInterface.tsx` | チャット UI のカスタマイズ |
| `patterns/strands-single-agent/requirements.txt` | Python 依存関係 |

### 触らない方がいい場所（フレームワーク基盤）

| ファイル/ディレクトリ | 理由 |
|----------|------|
| `frontend/src/lib/agentcore-client/` | SSE パーサー・AgentCore 通信プロトコル |
| `infra-cdk/lib/cognito-stack.ts` | 認証基盤（壊すとログイン不能に） |
| `infra-cdk/lib/amplify-hosting-stack.ts` | ホスティング基盤 |
| `frontend/src/components/auth/AuthProvider.tsx` | 認証フロー制御 |
| `patterns/utils/auth.py` | JWT 検証・トークン取得（セキュリティ核心部） |
| `infra-cdk/lib/utils/config-manager.ts` | 設定バリデーション |
| `infra-cdk/lib/utils/agentcore-role.ts` | IAM ロール定義 |

---

## 4. フレームワーク特有の重要な規約

### ツール追加パターン: 「1ツール = 1 Lambda」

```
gateway/tools/my_tool/
├── my_tool_lambda.py   # handler(event, context)
└── tool_spec.json      # MCP 形式のスキーマ
```

- Lambda は HTTP ラッパーではなく、引数を直接受け取る
- 戻り値は `{"content": [{"type": "text", "text": ...}]}` 形式

### リソース命名規約

```
SSM:      /{stack_name_base}/{parameter-name}
Secrets:  /{stack_name_base}/{secret-name}
Lambda:   {stack_name_base}-{function-name}
```

### セキュリティの鉄則

- user_id は必ず**検証済み JWT の `sub` クレーム**から取得する
  - `patterns/utils/auth.py` の `extract_user_id_from_context()`
- ユーザー入力からの user_id は絶対に信用しない（プロンプトインジェクション対策）

### デプロイタイプ

- `docker`（デフォルト）: リポジトリルートがビルドコンテキスト、ARM64
- `zip`: Lambda パッケージング、開発イテレーション向け

### フロントエンド設定注入

- デプロイ時に `aws-exports.json` が自動生成される（Runtime ARN, Cognito 設定等）
- フロントエンドはこのファイルから接続先を読み取る

### Agent のストリーミング

- `@app.entrypoint` デコレータで SSE エントリポイントを定義
- `agent.stream_async()` で非同期ストリーミング
- フロントエンドは `frontend/src/lib/agentcore-client/utils/sse.ts` + パターン別パーサーで受信

---

## 5. gateway/ と tools/ の違い

この2つは**ツールの実行場所**が根本的に異なる。

### gateway/ — リモートツール（Lambda で別プロセス実行）

```
gateway/tools/sample_tool/
├── sample_tool_lambda.py   # Lambda 関数として独立デプロイ
└── tool_spec.json          # MCP スキーマ定義
```

- MCP プロトコル経由で HTTP 越しに呼び出される
- Agent とは別の Lambda として独立してスケール
- Gateway が認証・ルーティングを担当
- 用途: 外部 API 連携、重い処理、独立スケールが必要なツール

### tools/ — ローカルツール（Agent と同一プロセスで実行）

```
tools/code_interpreter/
└── code_interpreter_tools.py   # Python クラス（直接 import）
```

- Agent のランタイムコンテナ内で直接実行される
- MCP も HTTP も不要、普通の関数呼び出し
- Agent と一緒にスケール
- 用途: 組み込み機能、AWS サービスラッパー

### 比較表

| 観点 | gateway/ (リモート) | tools/ (ローカル) |
|------|---------------------|-------------------|
| 実行場所 | Lambda（別プロセス） | Agent ランタイム（同一プロセス） |
| 通信プロトコル | MCP over HTTP | 直接関数呼び出し |
| スケーリング | Lambda 独立スケール | Agent と一緒 |
| 認証 | M2M JWT 必要 | 不要（Agent 内部） |
| デプロイ | Lambda として個別デプロイ | Agent コンテナにバンドル |

### Agent での統合

```python
# basic_agent.py
agent = Agent(
    tools=[
        gateway_client,                        # ← gateway/ のツール群（MCP 経由）
        code_tools.execute_python_securely,    # ← tools/ のツール（直接呼び出し）
    ],
)
```

Agent から見ると両方とも「ツール」として透過的に使えるが、裏側の仕組みが異なる。

---

## 6. M2M 認証の仕組み

### なぜ必要か

Agent が Gateway のツール（Lambda）を呼ぶとき、Gateway は「このリクエストは信頼できるか？」を検証する必要がある。しかし Agent はバックエンドプロセスなので、人間のログインフローは使えない。そこで **OAuth2 Client Credentials（M2M）** フローを使う。

### 2種類の Cognito クライアント

```
Cognito User Pool
  ├── User Client（フロントエンド用、人間がログイン）
  │     OAuth Flow: Authorization Code
  │     シークレット: なし（公開クライアント）
  │     スコープ: openid, email, profile
  │
  └── Machine Client（Agent用、サービス間認証）
        OAuth Flow: Client Credentials
        シークレット: あり（Secrets Manager に保管）
        スコープ: {stack}-gateway/read, {stack}-gateway/write
```

### 認証フロー

```
Agent 起動時
  │
  ▼ ① SSM / Secrets Manager から認証情報を取得
  │   - machine_client_id      (SSM)
  │   - machine_client_secret  (Secrets Manager)
  │   - cognito_domain         (SSM)
  │
  ▼ ② Cognito トークンエンドポイントに POST
  │   POST https://{cognito_domain}/oauth2/token
  │   Authorization: Basic base64(client_id:client_secret)
  │   Body: grant_type=client_credentials
  │         scope={stack}-gateway/read {stack}-gateway/write
  │
  ▼ ③ access_token（JWT）を取得
  │
  ▼ ④ MCP クライアントを作成
  │   MCPClient(url=gateway_url, headers={"Authorization": "Bearer {token}"})
  │
  ▼ ⑤ Gateway がリクエスト受信時に JWT を検証
      - Cognito の公開鍵でトークンを検証
      - 許可された machine_client_id か確認
      - スコープ (read/write) を確認
      → OK なら Lambda ツールを実行
```

### ユーザー認証との関係

```
[ユーザー] ──user JWT──→ [AgentCore Runtime] ──M2M JWT──→ [Gateway] → [Lambda Tool]
           ユーザー認証                          M2M認証
           「誰がリクエスト？」                   「Agentは信頼できる？」
```

- ユーザー JWT と M2M JWT は**完全に別物**
- ユーザー JWT は「誰が使っているか」を特定する
- M2M JWT は「Agent が Gateway にアクセスする権限があるか」を証明する
- 同一の Cognito User Pool を使うが、クライアントもスコープも異なる

### ユーザー別のツール認可について

現在の FAST テンプレートでは**ユーザー単位のツール制限はできない**。

```
ユーザーA ─user JWT─→ [Runtime] ──┐
                                   ├── 同一の M2M JWT ──→ [Gateway] → 全ツール
ユーザーB ─user JWT─→ [Runtime] ──┘
```

- M2M トークンは Agent が1つだけ持つ共有の認証情報
- Client Credentials フローにはユーザーの概念がない
- Gateway は「このリクエストは Agent からか？」しか検証しない

ユーザー別の認可が必要な場合のアプローチ:

| 方法 | 仕組み | 変更箇所 |
|------|--------|----------|
| Agent 層で制御 | `basic_agent.py` で user_id に応じてツールを切り替え | Agent のみ |
| Gateway に Custom Authorizer | ユーザー JWT を Gateway まで転送し認可 | Gateway + CDK |
| Cognito グループ + スコープ | グループごとに異なる Machine Client/スコープを用意 | Cognito + CDK + Agent |