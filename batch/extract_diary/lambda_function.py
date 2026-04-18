"""日記抽出Lambda - GitHub Webhook対応"""

import os
import json
import logging
import hmac
import hashlib
import re
from typing import List, Dict, Any
import boto3
from github_client import GitHubClient
from llm_extractor import LLMExtractor
from s3_handler import S3Handler

# ロガー設定
logger = logging.getLogger()
logger.setLevel(logging.INFO)


def handler(event, context):
    """
    GitHub WebhookまたはAPI Gatewayから起動される日記抽出処理

    Args:
        event: API Gateway イベント
        context: Lambda context

    Returns:
        実行結果の辞書
    """
    logger.info("日記抽出Lambda開始")

    # 環境変数から設定を取得
    github_token_secret = os.environ["GITHUB_TOKEN_SECRET_NAME"]
    github_owner = os.environ["GITHUB_OWNER"]
    github_repo = os.environ["GITHUB_REPO"]
    s3_bucket = os.environ["S3_BUCKET_NAME"]
    webhook_secret_name = os.environ.get("GITHUB_WEBHOOK_SECRET_NAME")

    try:
        # 1. GitHub署名検証（セキュリティ）
        if webhook_secret_name and not verify_github_signature(event, webhook_secret_name):
            logger.warning("GitHub署名検証に失敗")
            return {
                "statusCode": 401,
                "body": json.dumps({"error": "Invalid signature"}),
            }

        # 2. Pushイベントのみ処理
        event_type = event.get("headers", {}).get("X-GitHub-Event", "")
        if event_type == "ping":
            logger.info("Ping イベントを受信（Webhook設定確認）")
            return {
                "statusCode": 200,
                "body": json.dumps({"message": "pong"}),
            }
        elif event_type != "push":
            logger.info(f"Push以外のイベントをスキップ: {event_type}")
            return {
                "statusCode": 200,
                "body": json.dumps({"message": "Event type ignored"}),
            }

        # 3. Payloadパース
        body = event.get("body", "{}")
        if event.get("isBase64Encoded"):
            import base64
            body = base64.b64decode(body).decode("utf-8")
        payload = json.loads(body)

        # 4. 日記ファイルのパスを抽出
        diary_dates = extract_diary_dates_from_commits(payload)
        if not diary_dates:
            logger.info("日記ファイルの変更が検出されませんでした")
            return {
                "statusCode": 200,
                "body": json.dumps({"message": "No diary files modified"}),
            }

        logger.info(f"検出された日記日付: {diary_dates}")

        # 5. クライアント初期化
        github_client = GitHubClient(github_token_secret, github_owner, github_repo)
        llm_extractor = LLMExtractor()
        s3_handler = S3Handler(s3_bucket)

        # 6. 各日記を抽出
        results = []
        for date_str in diary_dates:
            result = process_single_date(
                date_str, github_client, llm_extractor, s3_handler
            )
            results.append(result)

        # 7. 結果集計
        success_count = sum(1 for r in results if r["status"] == "success")
        skip_count = sum(1 for r in results if r["status"] == "skip")
        error_count = sum(1 for r in results if r["status"] == "error")

        logger.info(
            f"抽出完了: 成功={success_count}, スキップ={skip_count}, エラー={error_count}"
        )

        return {
            "statusCode": 200,
            "body": json.dumps({
                "message": "Extraction completed",
                "total": len(diary_dates),
                "success": success_count,
                "skip": skip_count,
                "error": error_count,
                "results": results,
            }),
        }

    except Exception as e:
        logger.error(f"処理でエラー発生: {e}", exc_info=True)
        return {
            "statusCode": 500,
            "body": json.dumps({"error": str(e)}),
        }


def verify_github_signature(event: Dict[str, Any], secret_name: str) -> bool:
    """
    GitHub Webhook署名を検証

    Args:
        event: API Gateway イベント
        secret_name: Secrets Manager のシークレット名

    Returns:
        署名が有効ならTrue
    """
    signature_header = event.get("headers", {}).get("X-Hub-Signature-256", "")

    if not signature_header:
        logger.warning("X-Hub-Signature-256 ヘッダーが見つかりません")
        return False

    # Secrets Managerからシークレット取得
    secrets_client = boto3.client("secretsmanager")
    try:
        response = secrets_client.get_secret_value(SecretId=secret_name)
        secret_data = json.loads(response["SecretString"])
        webhook_secret = secret_data.get("webhook_secret", "")
    except Exception as e:
        logger.error(f"Webhook Secretの取得に失敗: {e}")
        return False

    # HMAC署名計算
    body = event.get("body", "")
    if event.get("isBase64Encoded"):
        import base64
        body = base64.b64decode(body)
    else:
        body = body.encode("utf-8")

    expected_signature = "sha256=" + hmac.new(
        webhook_secret.encode("utf-8"), body, hashlib.sha256
    ).hexdigest()

    # タイミング攻撃対策の等値比較
    return hmac.compare_digest(expected_signature, signature_header)


def extract_diary_dates_from_commits(payload: Dict[str, Any]) -> List[str]:
    """
    Push eventのcommitsから日記ファイルパスを抽出し、日付リストを返す

    日記パス形式: daily/{YYYY}/{MM}/{YYYY-MM-DD}.md

    Args:
        payload: GitHub Push event payload

    Returns:
        日付リスト（YYYY-MM-DD形式）
    """
    diary_dates = set()
    diary_path_pattern = re.compile(r"^daily/(\d{4})/(\d{2})/(\d{4}-\d{2}-\d{2})\.md$")

    commits = payload.get("commits", [])

    for commit in commits:
        # added, modified, removed ファイルをチェック
        all_files = (
            commit.get("added", [])
            + commit.get("modified", [])
            + commit.get("removed", [])
        )

        for file_path in all_files:
            match = diary_path_pattern.match(file_path)
            if match:
                date_str = match.group(3)  # YYYY-MM-DD
                diary_dates.add(date_str)
                logger.info(f"日記ファイル検出: {file_path} -> {date_str}")

    return sorted(list(diary_dates))


def process_single_date(
    date_str: str,
    github_client: GitHubClient,
    llm_extractor: LLMExtractor,
    s3_handler: S3Handler,
) -> Dict[str, Any]:
    """
    単一日付の日記を抽出してS3に保存

    Args:
        date_str: YYYY-MM-DD形式の日付
        github_client: GitHubクライアント
        llm_extractor: LLM抽出器
        s3_handler: S3ハンドラー

    Returns:
        {"date": str, "status": "success|skip|error", "message": str}
    """
    try:
        # 日記取得
        diary_content = github_client.get_diary_content(date_str)
        if not diary_content:
            logger.info(f"日記が存在しません: {date_str}")
            return {
                "date": date_str,
                "status": "skip",
                "message": "日記ファイルが見つかりません",
            }

        # LLM抽出
        logger.info(f"抽出開始: {date_str}")
        extracted = llm_extractor.extract(diary_content)

        # S3保存
        s3_handler.save_draft(date_str, diary_content, extracted)

        logger.info(
            f"抽出完了: {date_str}, "
            f"references={len(extracted.get('references', []))}, "
            f"ideas={len(extracted.get('ideas', []))}, "
            f"goals={len(extracted.get('goals', []))}"
        )

        return {
            "date": date_str,
            "status": "success",
            "message": "抽出成功",
        }

    except Exception as e:
        logger.error(f"抽出失敗: {date_str}, error={e}")
        return {
            "date": date_str,
            "status": "error",
            "message": str(e),
        }