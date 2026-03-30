# Phase 3 実装計画書：定期抽出バッチ（draft自動生成）

> **最終更新**: 2026-03-22
> **ステータス**: 要件定義完了、実装待ち

---

## 1. 概要

### 目的

GitHubプライベートリポジトリに保存された日記（Markdown）から、**知識（references）**、**アイデア（ideas）**、**中長期目標（goals）** を自動抽出し、S3の `draft/` に保存する。

### 完了条件

- 毎日 2:00 JST にEventBridgeが自動実行される
- 未抽出の日記（過去30日以内）が自動的に抽出される
- 抽出結果がS3の `draft/YYYY-MM-DD/` に保存される
- CloudWatch Logsで実行ログを確認できる

### Phase 2との違い

| 項目             | Phase 2                           | Phase 3                        |
| ---------------- | --------------------------------- | ------------------------------ |
| **目的**         | 抽出済みデータの参照              | 日記からの自動抽出             |
| **トリガー**     | ユーザーのチャット                | EventBridge（定期実行）        |
| **データ保存先** | `references/`, `ideas/`, `goals/` | `draft/YYYY-MM-DD/`            |
| **実装内容**     | Gatewayツール3本                  | 抽出バッチLambda + EventBridge |

---

## 2. 要件詳細

### 2-1. 実行タイミング

- **実行時刻**: 毎日 2:00 JST（UTC 17:00）
- **実行頻度**: 1日1回
- **EventBridge Scheduler**: `cron(0 17 * * ? *)` ← UTC 17:00 = JST 2:00

### 2-2. 抽出対象（どの日記を抽出するか？）

**ルール**: 未抽出の日記すべて（draft/に存在しない日付）

**処理フロー**:
```
1. GitHub APIで日記ディレクトリ一覧取得（daily/YYYY/MM/*.md）
2. S3の draft/ ディレクトリ一覧取得
3. 差分を計算（日記は存在するが、draftがない日付）
4. 過去7日以内の差分のみ抽出処理
```

**制約**:
- 過去7日より古い日記は対象外（設定: `LOOKBACK_DAYS=7`）
- 日記が存在しない日はスキップ（エラーにしない）

**冪等性**:
- draft/に既に存在する日付は再抽出しない
- バッチが複数回実行されても同じ結果になる

### 2-3. LLM抽出ロジック

**方式**: 1回のLLM呼び出しで3ジャンルを一括抽出（Structured Output）

**モデル**: `jp.anthropic.claude-haiku-4-5-20251001-v1:0`

**プロンプト設計**:
```
以下の日記から3つのカテゴリに情報を抽出してください：

1. **References（客観的知識・学んだこと）**
   - 技術的な学習内容
   - 読んだ記事・本の要約
   - 仕事で得た知見

2. **Ideas（アイデア・TODO）**
   - 思いついたアイデア
   - やりたいこと
   - TODO

3. **Goals（中長期目標）**
   - キャリア目標
   - スキル習得目標
   - プロジェクト目標

日記：
{diary_content}

各カテゴリについて、該当する情報がない場合は空のリストを返してください。
```

**Structured Output形式**:
```json
{
  "references": [
    {
      "topic": "AWS AgentCore Gateway",
      "content": "AgentCore GatewayはMCPプロトコルをサポート..."
    }
  ],
  "ideas": [
    {
      "content": "ブログ記事を書く：AWS AgentCoreでMCPツールを作る"
    }
  ],
  "goals": [
    {
      "content": "2026年Q2までにAWS Solutions Architect Professionalを取得"
    }
  ]
}
```

**Phase 2の要件変更**:
- ~~3つのLLMを並列実行~~ → **1つのLLMで一括抽出**（コスト・速度優先）

### 2-4. データ保存形式（S3 draft/）

```
s3://diary-insight-agent-insights/
└── draft/
    └── YYYY-MM-DD/                  # 日付ごとにディレクトリ
        ├── metadata.json            # 抽出メタデータ
        ├── original.md              # 元の日記（Phase 4のレビュー用）
        ├── references.md            # 抽出結果
        ├── ideas.md
        └── goals.md
```

**metadata.json 例**:
```json
{
  "diary_date": "2026-03-22",
  "extracted_at": "2026-03-23T02:00:00Z",
  "diary_path": "daily/2026/03/2026-03-22.md",
  "model_id": "jp.anthropic.claude-haiku-4-5-20251001-v1:0",
  "extraction_status": "success"
}
```

**references.md 例**:
```markdown
# 2026-03-22 参考情報

## AWS AgentCore Gateway
AgentCore GatewayはMCPプロトコルをサポート...

## Lambdaのタイムアウト設定
Lambdaのデフォルトタイムアウトは3秒...
```

### 2-5. エラーハンドリング

| エラー種類                   | 対応                                      |
| ---------------------------- | ----------------------------------------- |
| **日記ファイルが存在しない** | スキップ（ログに記録、エラーにしない）    |
| **GitHub APIレート制限**     | Exponential backoff + リトライ（最大3回） |
| **LLM呼び出しエラー**        | CloudWatch Logs に記録、翌日リトライ      |
| **S3書き込みエラー**         | CloudWatch Logs に記録、翌日リトライ      |

**リカバリー戦略**:
- 基本的に翌日の定期実行でリカバリー可能
- draft/のディレクトリを見て「どの日記まで抽出したか」を判断
- 状態管理用のテーブルは不要（S3のディレクトリ構造が状態）

**ログ出力**:
```python
# 成功時
logger.info(f"Extracted diary: {date}, references={len(refs)}, ideas={len(ideas)}, goals={len(goals)}")

# スキップ時
logger.info(f"Diary not found, skipped: {date}")

# エラー時
logger.error(f"Failed to extract diary: {date}, error={e}")
```

---

## 3. アーキテクチャ

### 3-1. システム構成図

```
EventBridge Scheduler（毎日 2:00 JST）
  |
  v
Lambda（抽出バッチ）
  |
  ├──> GitHub API（日記取得）
  |     └── daily/YYYY/MM/YYYY-MM-DD.md
  |
  ├──> Bedrock（LLM抽出）
  |     └── Claude Haiku 4.5 + Structured Output
  |
  └──> S3（draft保存）
        └── draft/YYYY-MM-DD/
              ├── metadata.json
              ├── original.md
              ├── references.md
              ├── ideas.md
              └── goals.md
```

### 3-2. データフロー

```
1. EventBridge起動
   ↓
2. Lambda: GitHub APIで日記一覧取得
   - GET /repos/{owner}/{repo}/contents/daily/{YYYY}/{MM}
   - 過去30日分のファイル一覧を取得
   ↓
3. Lambda: S3でdraft一覧取得
   - ListObjectsV2: prefix="draft/"
   - 既に抽出済みの日付を取得
   ↓
4. Lambda: 差分計算（未抽出の日記）
   - 日記は存在するが、draftがない日付を抽出
   ↓
5. 各日記について（並列処理）:
   a. GitHub APIで日記内容取得
   b. Bedrock（Claude）で3ジャンル抽出
   c. S3の draft/YYYY-MM-DD/ に保存
   ↓
6. CloudWatch Logs: 実行結果を記録
```

### 3-3. GitHub API詳細

**認証**: GitHub Personal Access Token (PAT)
- 権限: `repo`（プライベートリポジトリの読み取り）
- 保存先: AWS Secrets Manager（暗号化）

**API エンドポイント**:
1. ディレクトリ一覧取得
   ```
   GET /repos/{owner}/{repo}/contents/daily/{YYYY}/{MM}
   ```
2. ファイル内容取得
   ```
   GET /repos/{owner}/{repo}/contents/daily/{YYYY}/{MM}/{YYYY-MM-DD}.md
   ```

**レート制限**:
- 認証付き: 5000 requests/hour
- 1日1回の実行で過去30日分を処理: 最大30リクエスト/日 → 問題なし

---

## 4. 実装内容

### 4-1. Lambda実装（抽出バッチ）

**ディレクトリ構成**:
```
batch/
└── extract_diary/
    ├── lambda_function.py          # メインハンドラー
    ├── github_client.py            # GitHub API クライアント
    ├── llm_extractor.py            # LLM抽出ロジック
    ├── s3_handler.py               # S3保存ロジック
    ├── requirements.txt            # boto3, requests
    └── README.md
```

**lambda_function.py（メインハンドラー）**:
```python
import os
import boto3
from datetime import datetime, timedelta
from github_client import GitHubClient
from llm_extractor import LLMExtractor
from s3_handler import S3Handler

def handler(event, context):
    """
    EventBridgeから起動される抽出バッチ
    """
    # 環境変数
    github_token_secret = os.environ['GITHUB_TOKEN_SECRET_NAME']
    github_owner = os.environ['GITHUB_OWNER']
    github_repo = os.environ['GITHUB_REPO']
    s3_bucket = os.environ['S3_BUCKET_NAME']
    lookback_days = int(os.environ.get('LOOKBACK_DAYS', '30'))

    # クライアント初期化
    github_client = GitHubClient(github_token_secret, github_owner, github_repo)
    llm_extractor = LLMExtractor()
    s3_handler = S3Handler(s3_bucket)

    # 1. 未抽出の日記を検出
    unextracted_dates = get_unextracted_dates(
        github_client, s3_handler, lookback_days
    )

    logger.info(f"Found {len(unextracted_dates)} unextracted diaries")

    # 2. 各日記を抽出
    for date in unextracted_dates:
        try:
            # 日記取得
            diary_content = github_client.get_diary(date)
            if not diary_content:
                logger.info(f"Diary not found, skipped: {date}")
                continue

            # LLM抽出
            extracted = llm_extractor.extract(diary_content)

            # S3保存
            s3_handler.save_draft(date, diary_content, extracted)

            logger.info(f"Extracted: {date}, refs={len(extracted['references'])}, ideas={len(extracted['ideas'])}, goals={len(extracted['goals'])}")

        except Exception as e:
            logger.error(f"Failed to extract: {date}, error={e}")
            continue

    return {
        "statusCode": 200,
        "body": f"Processed {len(unextracted_dates)} diaries"
    }
```

**github_client.py（GitHub API クライアント）**:
```python
import boto3
import requests
from datetime import datetime, timedelta

class GitHubClient:
    def __init__(self, token_secret_name, owner, repo):
        # Secrets Managerからトークン取得
        secrets = boto3.client('secretsmanager')
        self.token = secrets.get_secret_value(SecretId=token_secret_name)['SecretString']
        self.owner = owner
        self.repo = repo
        self.base_url = f"https://api.github.com/repos/{owner}/{repo}"

    def get_diary_list(self, lookback_days):
        """過去N日分の日記一覧を取得"""
        dates = []
        today = datetime.now().date()

        for i in range(lookback_days):
            date = today - timedelta(days=i)
            dates.append(date)

        return dates

    def get_diary(self, date):
        """日記内容を取得"""
        year, month = date.strftime("%Y"), date.strftime("%m")
        filename = date.strftime("%Y-%m-%d.md")
        url = f"{self.base_url}/contents/daily/{year}/{month}/{filename}"

        response = requests.get(url, headers={
            "Authorization": f"Bearer {self.token}",
            "Accept": "application/vnd.github.v3.raw"
        })

        if response.status_code == 404:
            return None  # 日記が存在しない

        response.raise_for_status()
        return response.text
```

**llm_extractor.py（LLM抽出ロジック）**:
```python
import boto3
import json

class LLMExtractor:
    def __init__(self):
        self.bedrock = boto3.client('bedrock-runtime')
        self.model_id = "anthropic.claude-3-5-sonnet-20241022-v2:0"

    def extract(self, diary_content):
        """日記から3ジャンルを抽出"""
        prompt = self._build_prompt(diary_content)

        response = self.bedrock.converse(
            modelId=self.model_id,
            messages=[{"role": "user", "content": [{"text": prompt}]}],
            toolConfig={
                "tools": [{
                    "toolSpec": {
                        "name": "extract_insights",
                        "description": "日記から知識・アイデア・目標を抽出",
                        "inputSchema": {
                            "json": {
                                "type": "object",
                                "properties": {
                                    "references": {
                                        "type": "array",
                                        "items": {
                                            "type": "object",
                                            "properties": {
                                                "topic": {"type": "string"},
                                                "content": {"type": "string"}
                                            },
                                            "required": ["topic", "content"]
                                        }
                                    },
                                    "ideas": {
                                        "type": "array",
                                        "items": {
                                            "type": "object",
                                            "properties": {
                                                "content": {"type": "string"}
                                            },
                                            "required": ["content"]
                                        }
                                    },
                                    "goals": {
                                        "type": "array",
                                        "items": {
                                            "type": "object",
                                            "properties": {
                                                "content": {"type": "string"}
                                            },
                                            "required": ["content"]
                                        }
                                    }
                                },
                                "required": ["references", "ideas", "goals"]
                            }
                        }
                    }
                }],
                "toolChoice": {"tool": {"name": "extract_insights"}}
            }
        )

        # Tool Useレスポンスをパース
        tool_use = response['output']['message']['content'][0]['toolUse']
        return tool_use['input']

    def _build_prompt(self, diary_content):
        return f"""以下の日記から3つのカテゴリに情報を抽出してください：

1. **References（客観的知識・学んだこと）**
   - 技術的な学習内容
   - 読んだ記事・本の要約
   - 仕事で得た知見

2. **Ideas（アイデア・TODO）**
   - 思いついたアイデア
   - やりたいこと
   - TODO

3. **Goals（中長期目標）**
   - キャリア目標
   - スキル習得目標
   - プロジェクト目標

日記：
{diary_content}

各カテゴリについて、該当する情報がない場合は空のリストを返してください。
"""
```

**s3_handler.py（S3保存ロジック）**:
```python
import boto3
import json
from datetime import datetime

class S3Handler:
    def __init__(self, bucket_name):
        self.s3 = boto3.client('s3')
        self.bucket = bucket_name

    def get_draft_list(self):
        """draft/の一覧を取得"""
        response = self.s3.list_objects_v2(
            Bucket=self.bucket,
            Prefix="draft/",
            Delimiter="/"
        )

        if 'CommonPrefixes' not in response:
            return []

        # draft/YYYY-MM-DD/ のディレクトリ一覧
        dates = []
        for prefix in response['CommonPrefixes']:
            date_str = prefix['Prefix'].replace('draft/', '').replace('/', '')
            dates.append(date_str)

        return dates

    def save_draft(self, date, diary_content, extracted):
        """draftに保存"""
        prefix = f"draft/{date}/"

        # metadata.json
        metadata = {
            "diary_date": date,
            "extracted_at": datetime.utcnow().isoformat() + "Z",
            "diary_path": f"daily/{date[:4]}/{date[5:7]}/{date}.md",
            "model_id": "anthropic.claude-3-5-sonnet-20241022-v2:0",
            "extraction_status": "success"
        }
        self._put_object(prefix + "metadata.json", json.dumps(metadata, indent=2))

        # original.md
        self._put_object(prefix + "original.md", diary_content)

        # references.md
        refs_md = self._format_references(date, extracted['references'])
        self._put_object(prefix + "references.md", refs_md)

        # ideas.md
        ideas_md = self._format_ideas(date, extracted['ideas'])
        self._put_object(prefix + "ideas.md", ideas_md)

        # goals.md
        goals_md = self._format_goals(date, extracted['goals'])
        self._put_object(prefix + "goals.md", goals_md)

    def _put_object(self, key, body):
        self.s3.put_object(Bucket=self.bucket, Key=key, Body=body)

    def _format_references(self, date, references):
        if not references:
            return ""

        lines = [f"# {date} 参考情報\n"]
        for ref in references:
            lines.append(f"## {ref['topic']}\n{ref['content']}\n")

        return "\n".join(lines)

    def _format_ideas(self, date, ideas):
        if not ideas:
            return ""

        lines = [f"# {date} アイデア\n"]
        for idea in ideas:
            lines.append(f"- {idea['content']}\n")

        return "\n".join(lines)

    def _format_goals(self, date, goals):
        if not goals:
            return ""

        lines = [f"# {date} 中長期目標\n"]
        for goal in goals:
            lines.append(f"- {goal['content']}\n")

        return "\n".join(lines)
```

### 4-2. EventBridge設定（CDK）

```typescript
// infra-cdk/lib/backend-stack.ts

// EventBridge Scheduler（毎日 2:00 JST = UTC 17:00）
const extractionSchedule = new events.Rule(this, "DiaryExtractionSchedule", {
  schedule: events.Schedule.cron({
    minute: "0",
    hour: "17",  // UTC 17:00 = JST 2:00
    day: "*",
    month: "*",
    year: "*",
  }),
  description: "Daily diary extraction batch (2:00 JST)",
});

// Lambda（抽出バッチ）
const extractionLambda = new lambda.Function(this, "DiaryExtractionLambda", {
  runtime: lambda.Runtime.PYTHON_3_13,
  handler: "lambda_function.handler",
  code: lambda.Code.fromAsset(path.join(__dirname, "../../batch/extract_diary")),
  timeout: cdk.Duration.minutes(15),  // 最大15分
  memorySize: 512,
  environment: {
    GITHUB_TOKEN_SECRET_NAME: `${config.stack_name_base}/github-token`,
    GITHUB_OWNER: githubOwner,  // config.yamlから取得
    GITHUB_REPO: githubRepo,    // config.yamlから取得
    S3_BUCKET_NAME: insightsBucket.bucketName,
    LOOKBACK_DAYS: "7",
  },
  logGroup: new logs.LogGroup(this, "DiaryExtractionLambdaLogGroup", {
    retention: logs.RetentionDays.ONE_WEEK,
  }),
});

// EventBridge → Lambda
extractionSchedule.addTarget(new targets.LambdaFunction(extractionLambda));

// IAM権限
// 1. S3（draft/への書き込み）
insightsBucket.grantWrite(extractionLambda, "draft/*");
insightsBucket.grantRead(extractionLambda, "draft/*");

// 2. Secrets Manager（GitHub Token読み取り）
extractionLambda.addToRolePolicy(
  new iam.PolicyStatement({
    effect: iam.Effect.ALLOW,
    actions: ["secretsmanager:GetSecretValue"],
    resources: [
      `arn:aws:secretsmanager:${this.region}:${this.account}:secret:diary-insight-agent/github-token-*`
    ],
  })
);

// 3. Bedrock（LLM呼び出し）
extractionLambda.addToRolePolicy(
  new iam.PolicyStatement({
    effect: iam.Effect.ALLOW,
    actions: ["bedrock:InvokeModel"],
    resources: [
      `arn:aws:bedrock:${this.region}::foundation-model/anthropic.claude-3-5-sonnet-20241022-v2:0`
    ],
  })
);
```

### 4-3. Secrets Manager設定

**手動設定（初回のみ）**:
```bash
# GitHub Personal Access Token (PAT) を保存
aws secretsmanager create-secret \
  --name diary-insight-agent/github-token \
  --secret-string "ghp_xxxxxxxxxxxxxxxxxxxx" \
  --description "GitHub PAT for diary repository access"
```

**権限**: `repo`（プライベートリポジトリの読み取り）

### 4-4. config.yaml 追加設定

```yaml
# infra-cdk/config.yaml

github:
  owner: kk16dev
  repo: diary  # プライベートリポジトリ名
```

---

## 5. タスク分解

### 実装タスク一覧

- [ ] **1. batch/extract_diary/ 実装**
  - [ ] lambda_function.py（メインハンドラー）
  - [ ] github_client.py（GitHub API クライアント）
  - [ ] llm_extractor.py（LLM抽出ロジック）
  - [ ] s3_handler.py（S3保存ロジック）
  - [ ] requirements.txt
  - [ ] README.md

- [ ] **2. CDK変更（infra-cdk/lib/backend-stack.ts）**
  - [ ] EventBridge Scheduler追加
  - [ ] Lambda（抽出バッチ）追加
  - [ ] IAM権限設定（S3, Secrets Manager, Bedrock）

- [ ] **3. config.yaml 拡張**
  - [ ] github.owner, github.repo 追加

- [ ] **4. Secrets Manager設定**
  - [ ] GitHub PAT作成（権限: repo）
  - [ ] Secrets Managerに保存

- [ ] **5. デプロイ＆動作確認**
  - [ ] CDKデプロイ: `cd infra-cdk && cdk deploy`
  - [ ] Lambda手動実行テスト
  - [ ] EventBridge動作確認（翌日2:00）
  - [ ] CloudWatch Logs確認

- [ ] **6. 継続監視**
  - [ ] 1週間の自動実行ログを確認
  - [ ] draft/にデータが蓄積されているか確認

---

## 6. バックログ

### 6-1. SNS通知追加

**目的**: エラー発生時にメール/Slack通知

**実装内容**:
- CloudWatch Alarmでエラー検知
- SNSトピック作成
- メール/Slack連携

**優先度**: 低（Phase 5以降）

---

### 6-2. LLMプロバイダー変更（Bedrock → Claude API / Gemini API）

**背景**:
- Bedrockはトークン利用に応じてAWS経由のコストがかかる
- 現在Claude ProやGeminiのプランを契約済み
- 直接APIを使った方がコスト削減できる可能性

**実装内容**:
- Claude API（Anthropic直接）
- Gemini API（Google直接）
- 環境変数で切り替え可能にする

**コスト比較**:
| プロバイダー   | モデル            | コスト（Input）   | コスト（Output）   |
| -------------- | ----------------- | ----------------- | ------------------ |
| **Bedrock**    | Claude 3.5 Sonnet | $3.00 / 1M tokens | $15.00 / 1M tokens |
| **Claude API** | Claude 3.5 Sonnet | $3.00 / 1M tokens | $15.00 / 1M tokens |
| **Gemini API** | Gemini 1.5 Pro    | 無料枠あり        | 無料枠あり         |

**Note**:
- BedrockとClaude APIの価格は同じだが、契約プランによって差が出る可能性
- Gemini APIの無料枠が活用できれば大幅なコスト削減

**優先度**: 中（Phase 5〜6）

**関連タスク**:
- [ ] Claude API / Gemini API の料金体系調査
- [ ] 実際のトークン使用量を測定
- [ ] コスト試算
- [ ] 実装（環境変数 `LLM_PROVIDER=bedrock|claude|gemini`）

---

## 7. 参考情報

### 既存パターン

- **Lambda実装**: `gateway/tools/references/references_lambda.py`
- **CDKパターン**: `infra-cdk/lib/backend-stack.ts` の Lambdaリソース定義
- **Bedrock Converse API**: Phase 2の`references_lambda.py`で使用中

### ドキュメント

- [GitHub REST API - Contents](https://docs.github.com/en/rest/repos/contents)
- [Bedrock Converse API - Tool Use](https://docs.aws.amazon.com/bedrock/latest/userguide/tool-use.html)
- [EventBridge Scheduler - Cron式](https://docs.aws.amazon.com/eventbridge/latest/userguide/eb-cron-expressions.html)

### 関連ファイル

- [docs/project/REQUIREMENTS.md](./REQUIREMENTS.md) — 全体要件定義
- [docs/project/PHASE2_PLAN.md](./PHASE2_PLAN.md) — Phase 2実装計画

---

## 8. 補足

### Phase 4への引き継ぎ事項

Phase 3完了後、Phase 4（承認フロー）で以下を実装予定：

1. **専用UI（レビュー画面）**
   - draft/一覧表示
   - 元日記 vs 抽出結果の並列表示
   - 編集機能
   - 承認ボタン

2. **承認処理**
   - draft/ → references/, ideas/, goals/ への移動
   - ファイル名変更（references はトピック名を含める）

3. **修正処理**
   - AIへの修正依頼（自然言語）
   - draft/の内容を再抽出

**設計方針**:
- フロントエンドはReact（FASTデフォルト）に追加
- バックエンドはGatewayツールまたは新規Lambda
- チャットUIとは別画面（ワークフローで固める）

---

## 9. 完了条件チェックリスト

- [ ] EventBridgeが毎日2:00 JSTに自動実行される
- [ ] 未抽出の日記（過去30日以内）が検出される
- [ ] 抽出結果がS3の `draft/YYYY-MM-DD/` に保存される
- [ ] `metadata.json`, `original.md`, `references.md`, `ideas.md`, `goals.md` が生成される
- [ ] CloudWatch Logsで実行ログを確認できる
- [ ] 日記が存在しない日はスキップされる
- [ ] エラー発生時もバッチが停止せず、翌日リトライされる