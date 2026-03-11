# Phase 2 実装計画書：Gatewayツール＋システムプロンプト

## 1. 目的

チャットUIから日記のinsight（知識・アイデア・目標）を参照できるようにする。

具体的には、GitHubリポジトリに保存されたMarkdownファイルを3つのGatewayツールで取得し、エージェントが質問に応じて回答できる状態にする。

### 完了条件

チャットで「今月のアイデアをまとめて」と聞くと、サンプルデータを参照して答えてくれる状態。

> この時点では抽出バッチは未実装（Phase 3）。デモリポジトリに手動でサンプルMarkdownを置いて動作確認する。

---

## 2. 設計方針

### 2-1. 1つの共有Lambdaで3ツールを処理

3つのツール（`get_references`, `get_ideas`, `get_goals`）は、対象ディレクトリ名が異なるだけでロジックは同一。GATEWAY.md の「Multiple Tools Per Lambda」パターンに従い、**1つのLambda関数**で3ツールすべてを処理する。

```
ツール名            → 対象ディレクトリ
────────────────────────────────────
get_references      → references/
get_ideas           → ideas/
get_goals           → goals/
```

### 2-2. GitHub情報はSecrets Managerで一元管理

リポジトリにGitHub関連情報を一切残さない。Secrets Managerに以下のJSON形式で格納する。

- **シークレット名**: `/{stack_name}/github_config`
- **内容**:
  ```json
  {
    "token": "ghp_xxxxx",
    "owner": "github-username",
    "repo": "diary-demo-repo"
  }
  ```

Lambdaは実行時にSecrets Managerから取得する。CDKやconfig.yamlにGitHub情報は不要。

### 2-3. Privateリポジトリ対応

GitHub PATに `repo` スコープがあれば、APIリクエストの `Authorization: Bearer {token}` ヘッダーによりPrivateリポジトリでも動作する。

### 2-4. 日付フィルタリング

各ツールに `date_from` / `date_to` パラメータ（任意）を設け、ファイル名の日付（`YYYY-MM-DD`）で期間を絞り込める。

---

## 3. 全体のデータフロー

```
ユーザー: 「今月のアイデアをまとめて」
  │
  ▼
チャットUI (React) → Cognito認証 → API Gateway
  │
  ▼
AgentCore Runtime (Strands Agent)
  │  システムプロンプトが「日記インサイトエージェント」として指示
  │  → 「今月」を解釈して date_from/date_to を設定
  │  → get_ideas ツールを呼び出す
  │
  ▼
AgentCore Gateway (MCP) → OAuth2認証
  │
  ▼
diary_insights_lambda (Lambda)
  │  1. ツール名から対象ディレクトリを決定 (get_ideas → ideas/)
  │  2. Secrets Manager から GitHub設定を取得
  │  3. GitHub API でファイル一覧取得 → 日付フィルタ
  │  4. 各ファイルの内容を取得・結合
  │
  ▼
GitHub API → diary-demo-repo/ideas/*.md
  │
  ▼（Markdown内容を返却）
  │
Agent が内容を要約して回答
  │
  ▼
ユーザーにストリーミングで返答
```

---

## 4. 変更対象ファイル

| ファイル | 操作 | 概要 |
|----------|------|------|
| `gateway/tools/diary_insights/tool_spec.json` | 新規 | 3ツールのスキーマ定義 |
| `gateway/tools/diary_insights/diary_insights_lambda.py` | 新規 | 共有Lambdaハンドラ |
| `infra-cdk/lib/backend-stack.ts` | 変更 | Lambda/Gateway Target/IAM追加 |
| `patterns/strands-single-agent/basic_agent.py` | 変更 | システムプロンプト変更 |

**変更不要:** `config-manager.ts`, `config.yaml`

---

## 5. 各ファイルの実装詳細

### 5-1. `gateway/tools/diary_insights/tool_spec.json`（新規）

3ツールのJSON Schemaを1ファイルに定義。Gateway Targetの `inlinePayload` として CDK から読み込まれる。

```json
[
  {
    "name": "get_references",
    "description": "日記から抽出された知識・参考情報を取得する。date_fromとdate_toで期間を絞り込める。",
    "inputSchema": {
      "type": "object",
      "properties": {
        "date_from": {
          "type": "string",
          "description": "取得開始日（YYYY-MM-DD形式、省略時は全期間）"
        },
        "date_to": {
          "type": "string",
          "description": "取得終了日（YYYY-MM-DD形式、省略時は全期間）"
        }
      },
      "required": []
    }
  },
  {
    "name": "get_ideas",
    "description": "日記から抽出されたアイデア・TODOを取得する。date_fromとdate_toで期間を絞り込める。",
    "inputSchema": {
      "type": "object",
      "properties": {
        "date_from": {
          "type": "string",
          "description": "取得開始日（YYYY-MM-DD形式、省略時は全期間）"
        },
        "date_to": {
          "type": "string",
          "description": "取得終了日（YYYY-MM-DD形式、省略時は全期間）"
        }
      },
      "required": []
    }
  },
  {
    "name": "get_goals",
    "description": "日記から抽出された中長期目標を取得する。date_fromとdate_toで期間を絞り込める。",
    "inputSchema": {
      "type": "object",
      "properties": {
        "date_from": {
          "type": "string",
          "description": "取得開始日（YYYY-MM-DD形式、省略時は全期間）"
        },
        "date_to": {
          "type": "string",
          "description": "取得終了日（YYYY-MM-DD形式、省略時は全期間）"
        }
      },
      "required": []
    }
  }
]
```

### 5-2. `gateway/tools/diary_insights/diary_insights_lambda.py`（新規）

既存の `sample_tool_lambda.py` パターンに準拠した共有Lambdaハンドラ。

**処理フロー:**

1. `context.client_context.custom['bedrockAgentCoreToolName']` からツール名を取得
2. `___` デリミタでターゲット名プレフィックスを除去
3. ツール名→ディレクトリ名マッピング
4. Secrets Manager から `/{STACK_NAME}/github_config` を取得（JSON）
5. GitHub Contents API でディレクトリ内のファイル一覧を取得
6. ファイル名から日付を正規表現（`YYYY-MM-DD`）で抽出し、`date_from`/`date_to` でフィルタ
7. 各ファイルの内容（Base64）をデコードして結合
8. `{"content": [{"type": "text", "text": result}]}` で返却

**技術的なポイント:**

- 外部ライブラリ不要（`urllib.request`, `json`, `base64`, `re`, `boto3` のみ）
- `boto3` はLambdaランタイムに含まれるため依存追加不要
- エラー時は `{"error": "..."}` 形式で返却

### 5-3. `infra-cdk/lib/backend-stack.ts`（変更）

`createAgentCoreGateway` メソッドに以下を追加。既存の sample_tool はそのまま残す。

**追加リソース:**

| リソース | CDK ID | 内容 |
|----------|--------|------|
| Lambda | `DiaryInsightsToolLambda` | Python 3.13, 60秒タイムアウト |
| LogGroup | `DiaryInsightsToolLambdaLogGroup` | CloudWatch Logs |
| IAM Policy | (Lambda inline) | `secretsmanager:GetSecretValue` |
| Gateway Target | `DiaryInsightsGatewayTarget` | 3ツールのスキーマを含む |

**IAM権限:**

- Lambda → Secrets Manager: `secretsmanager:GetSecretValue` (対象: `/{stack_name}/github_config*`)
- Gateway Role → Lambda: `lambda:InvokeFunction`（`grantInvoke`）

**依存関係:**

```
diaryInsightsLambda ← gateway ← diaryGatewayTarget
```

### 5-4. `patterns/strands-single-agent/basic_agent.py`（変更）

システムプロンプト（66-67行目）を日記インサイトエージェント向けの日本語プロンプトに変更。

**変更後のプロンプト概要:**

- ロール定義: 日記インサイトエージェント
- ツール説明: 3つのGatewayツール + Code Interpreter
- 回答方針: 適切なツール選択、日付範囲推定、日本語回答

---

## 6. デプロイ前の手動準備

### 6-1. デモ用GitHubリポジトリ作成

以下の構造でサンプルMarkdownを配置:

```
diary-demo-repo/
├── references/
│   └── 2026-02-10-references.md
├── ideas/
│   └── 2026-02-10-ideas.md
└── goals/
    └── 2026-02-10-goals.md
```

### 6-2. Secrets Manager にGitHub設定を登録

```bash
aws secretsmanager create-secret \
  --name /diary-insight-agent/github_config \
  --secret-string '{"token":"ghp_xxxxx","owner":"your-username","repo":"diary-demo-repo"}' \
  --region us-east-1
```

---

## 7. 動作確認手順

1. `cdk deploy` でデプロイ
2. Gatewayテストスクリプトで3ツールが登録されていることを確認
3. Lambda直接テスト（AWS CLI）
4. チャットUI E2Eテスト:
   - 「今月のアイデアをまとめて」 → `get_ideas` が呼ばれ、サンプルデータを参照した回答
   - 「最近の中長期目標を教えて」 → `get_goals`
   - 「目標に関連するアイデアを整理して」 → `get_goals` + `get_ideas`
