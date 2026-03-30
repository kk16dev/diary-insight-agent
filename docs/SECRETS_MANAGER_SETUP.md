# Secrets Manager セットアップ手順

Phase 3の抽出バッチで使用するGitHub Personal Access Token (PAT) をAWS Secrets Managerに保存する手順。

## 前提条件

- AWS CLIがインストール済み
- AWS認証情報が設定済み（`aws configure`）
- GitHubアカウントにアクセス可能

---

## 1. GitHub Personal Access Token (PAT) の作成

### 1-1. GitHubにログイン

https://github.com にアクセスしてログイン

### 1-2. Settings → Developer settings → Personal access tokens

1. 右上のプロフィールアイコンをクリック
2. **Settings** を選択
3. 左サイドバーの一番下にある **Developer settings** をクリック
4. **Personal access tokens** → **Tokens (classic)** を選択
5. **Generate new token** → **Generate new token (classic)** をクリック

### 1-3. トークンの設定

| 項目 | 設定値 |
|------|--------|
| **Note** | `diary-insight-agent-extraction` |
| **Expiration** | `No expiration`（または適切な期限） |
| **Select scopes** | ✅ `repo`（Full control of private repositories） |

**Note**: `repo`スコープにチェックを入れると、プライベートリポジトリへのフルアクセスが許可されます。

### 1-4. トークンを生成

1. **Generate token** をクリック
2. 生成されたトークンをコピー（例: `ghp_xxxxxxxxxxxxxxxxxxxx`）
3. **重要**: このトークンは一度しか表示されないので、安全な場所にコピーしてください

---

## 2. AWS Secrets Manager にトークンを保存

### 2-1. AWS CLIでシークレットを作成

```bash
# シークレット名: diary-insight-agent/github-token
# 値: 先ほどコピーしたGitHub PAT

aws secretsmanager create-secret \
  --name diary-insight-agent/github-token \
  --description "GitHub PAT for diary extraction batch" \
  --secret-string '{"github_token":"ghp_xxxxxxxxxxxxxxxxxxxx"}'
```

**重要**: `ghp_xxxxxxxxxxxxxxxxxxxx` を実際のトークンに置き換えてください。

### 2-2. 保存確認

```bash
# シークレットが正しく保存されたか確認
aws secretsmanager describe-secret \
  --secret-id diary-insight-agent/github-token
```

**出力例**:
```json
{
  "ARN": "arn:aws:secretsmanager:ap-northeast-1:123456789012:secret:diary-insight-agent/github-token-AbCdEf",
  "Name": "diary-insight-agent/github-token",
  "Description": "GitHub PAT for diary extraction batch",
  "LastChangedDate": "2026-03-22T12:00:00.000000+09:00",
  "LastAccessedDate": "2026-03-22T00:00:00.000000+09:00"
}
```

---

## 3. （オプション）シークレットの値を確認

```bash
# シークレットの値を取得（デバッグ用）
aws secretsmanager get-secret-value \
  --secret-id diary-insight-agent/github-token \
  --query SecretString \
  --output text
```

**出力例**:
```json
{"github_token":"ghp_xxxxxxxxxxxxxxxxxxxx"}
```

---

## 4. CDKデプロイ

シークレットが作成されたら、CDKデプロイを実行します。

```bash
cd infra-cdk
cdk deploy
```

Lambda関数が自動的にこのシークレットを参照して、GitHub APIにアクセスします。

---

## トラブルシューティング

### エラー: `ResourceNotFoundException`

**原因**: シークレットが存在しない

**解決策**:
```bash
# シークレット一覧を確認
aws secretsmanager list-secrets | grep diary-insight-agent
```

### エラー: `AccessDeniedException`

**原因**: Lambda IAMロールにSecretsManager権限がない

**解決策**: extraction-stack.tsのIAMポリシーを確認
```typescript
extractionLambda.addToRolePolicy(
  new iam.PolicyStatement({
    effect: iam.Effect.ALLOW,
    actions: ["secretsmanager:GetSecretValue"],
    resources: [
      `arn:aws:secretsmanager:${this.region}:${this.account}:secret:diary-insight-agent/github-token-*`,
    ],
  })
);
```

### GitHub API エラー: `401 Unauthorized`

**原因**: トークンが無効または期限切れ

**解決策**:
```bash
# トークンを更新
aws secretsmanager update-secret \
  --secret-id diary-insight-agent/github-token \
  --secret-string '{"github_token":"ghp_NEW_TOKEN_HERE"}'
```

---

## セキュリティベストプラクティス

1. **トークンの定期的なローテーション**
   - 90日ごとにトークンを再生成することを推奨
   - AWS Secrets Managerの自動ローテーション機能は現在未対応（手動ローテーション）

2. **最小権限の原則**
   - `repo`スコープのみを付与（不要な権限は付与しない）

3. **トークンの安全な保管**
   - GitHub PATはSecrets Managerにのみ保存
   - `.env`ファイルやソースコードには含めない

4. **アクセスログの監視**
   - CloudWatch Logsで定期的にアクセスログを確認
   - 異常なアクセスがないかチェック

---

## 参考リンク

- [GitHub Personal Access Tokens](https://docs.github.com/en/authentication/keeping-your-account-and-data-secure/managing-your-personal-access-tokens)
- [AWS Secrets Manager](https://docs.aws.amazon.com/secretsmanager/)
