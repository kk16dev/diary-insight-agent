# Phase 2 実装計画書：Gatewayツール＋システムプロンプト【S3版】

> **最終更新**: 2026-03-22
> **ステータス**: 設計完了、実装待ち

---

## 1. Context（背景・要件）

### 目的

チャットUIから日記のinsight（知識・アイデア・目標）を参照できるようにする。

### 完了条件

チャットで以下のような質問に回答できること:
- 「AWS AgentCoreについて教えて」 → 知識から検索して回答
- 「今月のアイデアをまとめて」 → 期間を推定してアイデアを取得
- 「最近の目標を教えて」 → 目標を取得して回答

### 必須要件（ユーザー確認済み）

- ✅ 日記はGit管理（Obsidian連携のため）
- ✅ 抽出結果（知識・アイデア・目標）のGit管理は**不要**
- ✅ Obsidian参照は「あると便利」だが**必須ではない**
- ✅ 抽出結果は別途目視参照できればOK（AWS Console、AWS CLI等）

### 設計変更の経緯

1. **当初案**: GitHub API経由で抽出結果を参照
   - 理由: すべてGit管理、Obsidianから見える
   - 課題: 複雑、GitHub API認証、レート制限

2. **変更後**: S3保存方式
   - 理由: 抽出結果のGit管理は不要（ユーザー要件確認）
   - メリット: シンプル、高速、低コスト、IAM Roleで完結

---

## 2. 設計方針

### 2-1. データ保存先：S3バケット

```
s3://{stack-name}-insights/
├── references/YYYY-MM-DD-{topic}.md    # 知識（ファイル名に主題含む）
├── ideas/YYYY-MM-DD-ideas.md           # アイデア
└── goals/YYYY-MM-DD-goals.md           # 中長期目標
```

**Phase 3での対応**:
- バッチがGitHub APIで日記を取得
- LLMで抽出
- S3に保存（references/ のファイル名に主題を含める）

**目視参照方法**:
```bash
# AWS Console（ブラウザ）から直接閲覧、または
aws s3 sync s3://diary-insight-agent-insights/ ~/diary-insights/
```

### 2-2. 知識検索：ファイル名ベース（LLM 2段階選択）

**問題**: 知識は日付ではなく内容で検索したい

**解決策**: ファイル名にトピックを含め、LLMでファイル選択

```
処理フロー:
1. S3でファイル名一覧取得
   → references/2026-02-10-aws-agentcore-gateway.md
   → references/2026-02-15-python-async-programming.md

2. ファイル名リストをLLMに見せて関連性判断
   ユーザー: 「AWS AgentCoreについて教えて」
   → Bedrock Haiku: "2026-02-10-aws-agentcore-gateway.md が関連"

3. 選択されたファイル（1〜3個）のみS3から取得
```

**将来の拡張（バックログ）**:
- Option 2: インデックスファイル方式（index.jsonで要約管理）

### 2-3. アーキテクチャ比較

| 項目             | 旧案（GitHub API）            | 新案（S3）           |
| ---------------- | ----------------------------- | -------------------- |
| **保存先**       | GitHub リポジトリ             | S3バケット           |
| **認証**         | Secrets Manager（GitHub PAT） | IAM Role             |
| **Lambda実装**   | urllib + GitHub API処理       | boto3.s3のみ         |
| **速度**         | API経由（遅い）               | 直接アクセス（高速） |
| **複雑度**       | 高                            | 低                   |
| **コスト**       | API制限                       | 安い                 |
| **Git管理**      | ○                             | ×                    |
| **Obsidian参照** | ○                             | ×                    |

---

## 3. ツール仕様

### 3-1. ツール一覧

| ツール             | 必須パラメータ | 任意パラメータ         | 処理内容                         |
| ------------------ | -------------- | ---------------------- | -------------------------------- |
| **get_references** | `query`        | `date_from`, `date_to` | ファイル名ベース検索 → LLMで選択 |
| **get_ideas**      | なし           | `date_from`, `date_to` | 日付フィルタ → 全取得            |
| **get_goals**      | なし           | `date_from`, `date_to` | 日付フィルタ → 全取得            |

### 3-2. tool_spec.json（2ファイルに分割）

#### `gateway/tools/references/tool_spec.json`

```json
[
  {
    "name": "get_references",
    "description": "日記から抽出された知識・参考情報を検索する。queryで内容検索、date_from/date_toで期間絞り込み。",
    "inputSchema": {
      "type": "object",
      "properties": {
        "query": {
          "type": "string",
          "description": "検索したい内容（例: AWS AgentCore、Python非同期処理）"
        },
        "date_from": {
          "type": "string",
          "description": "取得開始日（YYYY-MM-DD形式、省略時は全期間）"
        },
        "date_to": {
          "type": "string",
          "description": "取得終了日（YYYY-MM-DD形式、省略時は全期間）"
        }
      },
      "required": ["query"]
    }
  }
]
```

#### `gateway/tools/insights/tool_spec.json`

```json
[
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

### 3-3. Lambda構成（2つに分離）

**設計方針**: 責務の分離とコード共通化のバランスを取る

| Lambda         | 担当ツール               | 特徴                           |
| -------------- | ------------------------ | ------------------------------ |
| **references** | `get_references`         | LLM検索、Bedrock呼び出し       |
| **insights**   | `get_ideas`, `get_goals` | シンプルな日付フィルタ、共通化 |

#### Lambda 1: `references_lambda.py`

```python
def handler(event, context):
    """get_references専用: ファイル名ベース検索 + LLM選択"""

    query = event['query']
    date_from = event.get('date_from')
    date_to = event.get('date_to')

    # 1. S3でファイル一覧取得
    s3 = boto3.client('s3')
    files = s3.list_objects_v2(Bucket=bucket, Prefix="references/")

    # 2. 日付フィルタ
    filtered_files = filter_by_date(files, date_from, date_to)

    # 3. ★ LLMでファイル選択（Bedrock Haiku）
    selected_files = select_files_with_llm(filtered_files, query)

    # 4. ファイル内容取得
    contents = []
    for file_key in selected_files:
        obj = s3.get_object(Bucket=bucket, Key=file_key)
        contents.append(obj['Body'].read().decode('utf-8'))

    return {"content": [{"type": "text", "text": "\n\n".join(contents)}]}
```

#### Lambda 2: `insights_lambda.py`（ideas/goals共通）

```python
def handler(event, context):
    """get_ideas/get_goals共通: 日付フィルタ + 全取得"""

    # 1. ツール名からprefixを決定
    tool_name = extract_tool_name(context)  # get_ideas or get_goals
    prefix = "ideas/" if tool_name == "get_ideas" else "goals/"

    date_from = event.get('date_from')
    date_to = event.get('date_to')

    # 2. S3でファイル一覧取得
    s3 = boto3.client('s3')
    files = s3.list_objects_v2(Bucket=bucket, Prefix=prefix)

    # 3. 日付フィルタ
    filtered_files = filter_by_date(files, date_from, date_to)

    # 4. ファイル内容取得（全ファイル）
    contents = []
    for file_key in filtered_files:
        obj = s3.get_object(Bucket=bucket, Key=file_key)
        contents.append(obj['Body'].read().decode('utf-8'))

    return {"content": [{"type": "text", "text": "\n\n".join(contents)}]}
```

**分離の理由**:
- ✅ 責務の分離: references（検索機能）vs. insights（取得機能）
- ✅ DRY原則: ideas/goalsで同じコードを重複させない
- ✅ 運用性: referencesのみ変更時、他に影響しない
- ✅ 個別設定: referencesはタイムアウト長め（Bedrock呼び出しあり）

---

## 4. システムプロンプト

```python
system_prompt = """あなたは日記インサイトエージェントです。ユーザーの日記から抽出された知識（references）、アイデア（ideas）、中長期目標（goals）を参照し、ユーザーの振り返りや意思決定を支援します。

## 利用可能なツール

### Gateway ツール（日記インサイト参照）
- **get_references**: 日記から抽出された知識・参考情報を検索します。queryパラメータで内容検索、date_from/date_toで期間絞り込み。
- **get_ideas**: 日記から抽出されたアイデア・TODOを取得します。
- **get_goals**: 日記から抽出された中長期目標を取得します。

## 回答方針
1. ユーザーの質問に応じて、適切なツールを選択して情報を取得してください。
2. get_referencesは必ずqueryパラメータを指定してください（例: query="AWS AgentCore"）。
3. 「今月のアイデア」のように期間が示唆される場合は、適切な日付範囲を推定してdate_from/date_toを指定してください。
4. 取得した情報をわかりやすく整理・要約して回答してください。
5. 複数の情報源を組み合わせた分析を求められた場合は、複数のツールを呼び出してください。
6. 日本語で回答してください。"""
```

**配置場所**: `patterns/strands-single-agent/basic_agent.py` の 66-67行目

---

## 5. 実装対象ファイル

### 5-1. ディレクトリ構成

```
gateway/tools/
├── references/              # Lambda 1: get_references専用
│   ├── tool_spec.json       # get_referencesのスキーマのみ
│   └── references_lambda.py # LLM検索実装
└── insights/                # Lambda 2: get_ideas/get_goals共通
    ├── tool_spec.json       # get_ideas + get_goalsの2つのスキーマ
    └── insights_lambda.py   # 日付フィルタ実装
```

### 5-2. ファイル一覧

| ファイル                                        | 操作 | 目的                                     |
| ----------------------------------------------- | ---- | ---------------------------------------- |
| `gateway/tools/references/tool_spec.json`       | 新規 | get_referencesスキーマ                   |
| `gateway/tools/references/references_lambda.py` | 新規 | S3 + LLMファイル選択                     |
| `gateway/tools/insights/tool_spec.json`         | 新規 | get_ideas + get_goalsスキーマ（2ツール） |
| `gateway/tools/insights/insights_lambda.py`     | 新規 | S3 + 日付フィルタ（共通処理）            |
| `infra-cdk/lib/backend-stack.ts`                | 変更 | S3 + 2Lambda + 3GatewayTarget            |
| `patterns/strands-single-agent/basic_agent.py`  | 変更 | システムプロンプト変更                   |

---

## 6. CDK追加リソース（backend-stack.ts）

### 6-1. S3バケット

```typescript
const insightsBucket = new s3.Bucket(this, "DiaryInsightsBucket", {
  bucketName: `${config.stack_name_base}-insights`,
  removalPolicy: cdk.RemovalPolicy.DESTROY,
  autoDeleteObjects: true,
  blockPublicAccess: s3.BlockPublicAccess.BLOCK_ALL,
});
```

### 6-2. Lambda関数（2つ）

```typescript
// Lambda 1: References（LLM検索）
const referencesLambda = new lambda.Function(this, "ReferencesToolLambda", {
  runtime: lambda.Runtime.PYTHON_3_13,
  handler: "references_lambda.handler",
  code: lambda.Code.fromAsset(path.join(__dirname, "../../gateway/tools/references")),
  timeout: cdk.Duration.seconds(60),  // Bedrock呼び出しがあるため長め
  environment: {
    S3_BUCKET_NAME: insightsBucket.bucketName,
  },
  // LogGroup省略
});

// Lambda 2: Insights（Ideas/Goals共通）
const insightsLambda = new lambda.Function(this, "InsightsToolLambda", {
  runtime: lambda.Runtime.PYTHON_3_13,
  handler: "insights_lambda.handler",
  code: lambda.Code.fromAsset(path.join(__dirname, "../../gateway/tools/insights")),
  timeout: cdk.Duration.seconds(30),  // シンプルな処理なので短め
  environment: {
    S3_BUCKET_NAME: insightsBucket.bucketName,
  },
  // LogGroup省略
});
```

### 6-3. IAM権限

```typescript
// S3読み取り（両方のLambdaに付与）
insightsBucket.grantRead(referencesLambda);
insightsBucket.grantRead(insightsLambda);

// Bedrock（referencesのみ: LLMファイル選択用）
referencesLambda.addToRolePolicy(
  new iam.PolicyStatement({
    effect: iam.Effect.ALLOW,
    actions: ["bedrock:InvokeModel"],
    resources: [
      `arn:aws:bedrock:${this.region}::foundation-model/anthropic.claude-3-haiku-20240307-v1:0`
    ],
  })
);

// Gateway → Lambda invoke（両方）
referencesLambda.grantInvoke(gatewayRole);
insightsLambda.grantInvoke(gatewayRole);
```

### 6-4. Gateway Target（3つ）

```typescript
// Target 1: get_references
const referencesToolSpecPath = path.join(__dirname, "../../gateway/tools/references/tool_spec.json");
const referencesApiSpec = JSON.parse(fs.readFileSync(referencesToolSpecPath, "utf8"));

const referencesGatewayTarget = new bedrockagentcore.CfnGatewayTarget(this, "ReferencesGatewayTarget", {
  gatewayIdentifier: gateway.attrGatewayIdentifier,
  name: "get-references-target",
  targetConfiguration: {
    mcp: {
      lambda: {
        lambdaArn: referencesLambda.functionArn,
        toolSchema: { inlinePayload: referencesApiSpec },
      },
    },
  },
  credentialProviderConfigurations: [{ credentialProviderType: "GATEWAY_IAM_ROLE" }],
});
referencesGatewayTarget.addDependency(gateway);
gateway.node.addDependency(referencesLambda);

// Target 2 & 3: get_ideas, get_goals（同じLambdaを使用）
const insightsToolSpecPath = path.join(__dirname, "../../gateway/tools/insights/tool_spec.json");
const insightsApiSpec = JSON.parse(fs.readFileSync(insightsToolSpecPath, "utf8"));

const ideasGatewayTarget = new bedrockagentcore.CfnGatewayTarget(this, "IdeasGatewayTarget", {
  gatewayIdentifier: gateway.attrGatewayIdentifier,
  name: "get-ideas-target",
  targetConfiguration: {
    mcp: {
      lambda: {
        lambdaArn: insightsLambda.functionArn,
        toolSchema: { inlinePayload: insightsApiSpec },  // get_ideas + get_goals
      },
    },
  },
  credentialProviderConfigurations: [{ credentialProviderType: "GATEWAY_IAM_ROLE" }],
});
ideasGatewayTarget.addDependency(gateway);

const goalsGatewayTarget = new bedrockagentcore.CfnGatewayTarget(this, "GoalsGatewayTarget", {
  gatewayIdentifier: gateway.attrGatewayIdentifier,
  name: "get-goals-target",
  targetConfiguration: {
    mcp: {
      lambda: {
        lambdaArn: insightsLambda.functionArn,
        toolSchema: { inlinePayload: insightsApiSpec },  // get_ideas + get_goals
      },
    },
  },
  credentialProviderConfigurations: [{ credentialProviderType: "GATEWAY_IAM_ROLE" }],
});
goalsGatewayTarget.addDependency(gateway);
gateway.node.addDependency(insightsLambda);
```

**追加位置**: `createAgentCoreGateway` メソッド内、既存の `gatewayTarget`（sample-tool）の直後

**Note**: insights/tool_spec.json には get_ideas と get_goals の2つのツール定義を含める

---

## 7. デプロイ前準備（サンプルデータ）

```bash
# サンプルMarkdownファイル作成
mkdir -p /tmp/diary-samples/{references,ideas,goals}

cat > /tmp/diary-samples/references/2026-02-10-aws-agentcore-gateway.md << 'EOF'
# 2026-02-10 参考情報: AWS AgentCore Gateway

## 学んだこと
- AgentCore GatewayはMCPプロトコルをサポート
- Lambda Targetパターンでツールを独立してスケール可能
EOF

cat > /tmp/diary-samples/ideas/2026-02-10-ideas.md << 'EOF'
# 2026-02-10 アイデア

## ブログ記事のネタ
- AWS AgentCoreのGateway機能について技術ブログを書く
EOF

cat > /tmp/diary-samples/goals/2026-02-10-goals.md << 'EOF'
# 2026-02-10 中長期目標

## キャリア
- 2026年Q2までにAWS Solutions Architect Professionalを取得する
EOF

# デプロイ後にS3アップロード
aws s3 sync /tmp/diary-samples/ s3://diary-insight-agent-insights/
```

---

## 8. 動作確認手順

1. CDKデプロイ: `cd infra-cdk && cdk deploy`
2. S3にサンプルデータ配置（上記スクリプト）
3. Gateway確認: `python3 scripts/test-gateway.py`
4. チャットUIテスト:
   - 「AWS AgentCoreについて教えて」
   - 「今月のアイデアをまとめて」
   - 「最近の目標を教えて」

---

## 9. 参考情報

### 既存パターン

- **Lambda実装**: `gateway/tools/sample_tool/sample_tool_lambda.py`
- **ツールスキーマ**: `gateway/tools/sample_tool/tool_spec.json`
- **CDKパターン**: `infra-cdk/lib/backend-stack.ts` の `createAgentCoreGateway` メソッド

### 今回の実装パターン

- **2Lambda構成**: 責務で分離（references: 検索、insights: 取得）
- **3GatewayTarget**: 各ツールを独立して呼び出し可能
- **コード共通化**: insights_lambda.py が get_ideas/get_goals を処理

### ドキュメント

- [docs/GATEWAY.md](../GATEWAY.md) — Gateway Lambda Target実装ガイド
- [docs/project/REQUIREMENTS.md](./REQUIREMENTS.md) — 全体要件定義

### バックログ

- インデックスファイル方式（references の検索精度向上）
- Bedrock Knowledge Base（大量データ対応）
