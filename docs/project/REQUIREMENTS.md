# diary-insight-agent 要件定義書

## 1. プロジェクト概要

### 目的

FASTフレームワーク（Fullstack AgentCore Solution Template）をベースに、Markdownで書いた日記から「客観的情報」「アイデア(todo)」「中長期目標」を自動抽出し、チャットUIで参照・活用できるAIエージェントを構築する。

### 前提・制約

| 項目               | 決定内容            | 理由                                         |
| ------------------ | ------------------- | -------------------------------------------- |
| 利用者             | 自分1人（個人利用） | 複数ユーザー対応不要                         |
| 日記フォーマット   | Markdown            | 既存の日記リポジトリに合わせる               |
| 抽出結果の保存形式 | Markdown            | データ量が多くならないためDBやベクトルDB不要 |
| 抽出トリガー       | 1日1回の定期実行    | 夜間バッチ想定                               |
| 認証情報管理       | Secrets Manager     |                                              |

---

## 2. システムアーキテクチャ

### 全体構成

```
【プロアクティブ：定期実行】

EventBridge（1日1回）
  |
Lambda（抽出バッチ）
  ├── GitHub API で日記リポジトリから最新Markdownを取得
  ├── LLMで抽出（客観的情報・アイデア・中長期目標）
  └── GitHub API で抽出結果をリポジトリに書き戻し

【リアクティブ：チャットUI】

ユーザー（自分）
  | ブラウザ
Amplify Hosting（React フロントエンド）  ← FASTデフォルト
  | Cognito認証
API Gateway                               ← FASTデフォルト
  |
AgentCore Runtime（Strandsエージェント） ← FASTデフォルト
  ├── AgentCore Memory（会話履歴）        ← FASTデフォルト
  └── AgentCore Gateway（MCPツール）      ← FASTデフォルト
        ├── Tool: get_references   ─┐
        ├── Tool: get_ideas         │ 今回追加実装
        └── Tool: get_goals        ─┘
            |
        GitHub APIで抽出済みMarkdownを取得して返す
```

### FASTから変更・追加する箇所

| ファイル／リソース                             | 変更内容                                                  |
| ---------------------------------------------- | --------------------------------------------------------- |
| `gateway/tools/`                               | 抽出結果参照ツール3本を新規追加                           |
| `infra-cdk/lib/backend-stack.ts`               | Lambdaツール・EventBridge・抽出バッチLambdaを追加         |
| `patterns/strands-single-agent/basic_agent.py` | システムプロンプトを日記インサイトエージェント向けに更新  |
| `infra-cdk/config.yaml`                        | admin_user_emailをnullに設定（config.yaml.exampleを用意） |

---

## 3. 機能詳細

### 3-1. 定期抽出バッチ（プロアクティブ）

**処理フロー**

```
1. EventBridgeが毎日指定時刻にLambdaを起動
2. GitHub APIで日記リポジトリの当日分Markdownを取得
3. 専用LLMを3つ並列で呼び出し、それぞれ抽出を担当：
   - LLM-1：知識（後から振り返るために学習した知識）
   - LLM-2：アイデア（思いついたこと・仮説）
   - LLM-3：中長期目標（将来に向けた意志・計画）
4. 各LLMはtool_useで「保存すべきか否か」を判断して出力
   - 抽出対象がない場合はスキップ（ファイル書き込みなし）
5. 抽出対象がある場合のみ、GitHub APIで各専用ディレクトリにMarkdownとして書き込み
```

**ディレクトリ構成（日記リポジトリ側）**

```
diary-repo/
├── diary/
│   └── 2026-02-23.md               ← 日記本文
├── references/
│   └── 2026-02-23-references.md    ← 知識の抽出結果
├── ideas/
│   └── 2026-02-23-ideas.md         ← アイデアの抽出結果
└── goals/
    └── 2026-02-23-goals.md         ← 中長期目標の抽出結果
```

### 3-2. チャットUIからの参照（リアクティブ）

**利用イメージ**

```
ユーザー：「今月出てきたアイデアをまとめて」
エージェント：抽出済みMarkdownを参照して回答

ユーザー：「中長期目標の進捗を整理して」
エージェント：目標一覧と関連する客観的情報を紐付けて回答
```

**ツール仕様**

| ツール名         | 概要             | 取得対象ディレクトリ |
| ---------------- | ---------------- | -------------------- |
| `get_references` | 知識を取得       | `references/`        |
| `get_ideas`      | アイデアを取得   | `ideas/`             |
| `get_goals`      | 中長期目標を取得 | `goals/`             |

---

## 4. リポジトリ構成

| リポジトリ                    | 公開範囲 | 内容                                         |
| ----------------------------- | -------- | -------------------------------------------- |
| 日記リポジトリ（既存）        | Private  | 日記Markdown・抽出結果Markdown               |
| `diary-insight-agent`（新規） | Public   | FASTベースのエージェントコード（データなし） |
| デモリポジトリ（新規）        | Public   | デモ用サンプルデータ込みの環境               |

### ディレクトリ構成（diary-insight-agentリポジトリ）

```
diary-insight-agent/
├── frontend/                    ← FASTデフォルト
├── infra-cdk/
│   ├── config.yaml              ← .gitignore対象
│   ├── config.yaml.example      ← コミット対象（プレースホルダー）
│   └── lib/backend-stack.ts     ← ツール・EventBridge追加
├── patterns/
│   └── strands-single-agent/
│       └── basic_agent.py       ← システムプロンプト変更
├── gateway/tools/
│   ├── get_references/
│   ├── get_ideas/
│   └── get_goals/
├── batch/
│   └── extract_diary/           ← 定期抽出バッチLambda
└── README.md
```

---

## 5. 非機能要件

| 項目                   | 内容                                                                              |
| ---------------------- | --------------------------------------------------------------------------------- |
| 認証情報               | GitHub TokenをSecrets Managerで管理。`.gitignore`で`config.yaml`を除外            |
| コスト                 | EventBridge＋Lambda定期実行は月数円以下。FASTのサーバーレス構成で未使用時ほぼ無料 |
| ログ                   | CloudWatch + X-Ray（FASTデフォルト）                                              |
| プロアクティブ実行時刻 | 毎日深夜（例：23:00 JST）を想定                                                   |

---

## 6. 開発フェーズ計画

### フェーズ概要

| フェーズ | 内容                                 | FASTへの変更   | 難易度 |
| -------- | ------------------------------------ | -------------- | ------ |
| Phase 1  | FASTテンプレート動作確認             | なし           | ★☆☆    |
| Phase 2  | Gatewayツール3本＋システムプロンプト | あり（軽め）   | ★★☆    |
| Phase 3  | 抽出バッチLambda＋EventBridge        | あり（メイン） | ★★★    |
| Phase 4  | ポートフォリオ仕上げ                 | なし           | ★☆☆    |

### Phase 1：FASTテンプレートのセットアップ＆動作確認

**目的：ベースラインを動かす**

FASTのテンプレートをそのままデプロイして、チャットUIが動くことを確認する。CDKやAmplify・Cognito・AgentCore Runtimeの流れを把握するフェーズ。

**完了条件：** デフォルト状態のチャットUIがブラウザで動いている状態

### Phase 2：エージェント側の実装（インターフェース寄り）

**目的：チャットUIから日記のinsightを参照できるようにする**

| タスク                      | 変更対象                                       |
| --------------------------- | ---------------------------------------------- |
| `get_references` ツール実装 | `gateway/tools/get_references/` 新規           |
| `get_ideas` ツール実装      | `gateway/tools/get_ideas/` 新規                |
| `get_goals` ツール実装      | `gateway/tools/get_goals/` 新規                |
| Gatewayツール3本をCDK追加   | `infra-cdk/lib/backend-stack.ts`               |
| システムプロンプト変更      | `patterns/strands-single-agent/basic_agent.py` |
| サンプルデータで動作確認    | デモリポジトリ                                 |

**完了条件：** チャットで「今月のアイデアをまとめて」と聞くと、サンプルデータを参照して答えてくれる状態

> **Note:** この時点では抽出バッチは未実装。デモリポジトリに手動でサンプルMarkdownを置いて動作確認する。

### Phase 3：定期抽出バッチの実装

**目的：日記から自動でinsightを抽出できるようにする**

| タスク                            | 変更対象                         |
| --------------------------------- | -------------------------------- |
| 抽出バッチLambda実装              | `batch/extract_diary/` 新規      |
| EventBridge追加（毎日23:00 JST）  | `infra-cdk/lib/backend-stack.ts` |
| 抽出バッチLambdaをCDK追加         | `infra-cdk/lib/backend-stack.ts` |
| Secrets ManagerにGitHub Token登録 | AWSコンソール                    |
| バッチの手動実行テスト            | -                                |

**完了条件：** 毎晩バッチが走り、翌日チャットで参照できる状態

### Phase 4：仕上げ＆ポートフォリオ化

**目的：公開できる状態にする**

| タスク                                                                   |
| ------------------------------------------------------------------------ |
| `config.yaml.example` を作成（プレースホルダー）                         |
| `.gitignore` に `config.yaml`・`MEMO.md` を追加                          |
| `README.md` を日本語で書き直し（セットアップ手順・アーキテクチャ図含む） |
| デモリポジトリを整備（サンプルデータ込み）                               |

**完了条件：** READMEを読めばセットアップでき、Publicリポジトリとして公開できる状態
