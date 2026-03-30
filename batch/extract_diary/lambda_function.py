"""日記抽出バッチLambda - メインハンドラー"""

import os
import logging
from typing import List
from github_client import GitHubClient
from llm_extractor import LLMExtractor
from s3_handler import S3Handler

# ロガー設定
logger = logging.getLogger()
logger.setLevel(logging.INFO)


def handler(event, context):
    """
    EventBridgeから起動される抽出バッチ

    Args:
        event: EventBridgeイベント
        context: Lambda context

    Returns:
        実行結果の辞書
    """
    logger.info("日記抽出バッチを開始")

    # 環境変数から設定を取得
    github_token_secret = os.environ["GITHUB_TOKEN_SECRET_NAME"]
    github_owner = os.environ["GITHUB_OWNER"]
    github_repo = os.environ["GITHUB_REPO"]
    s3_bucket = os.environ["S3_BUCKET_NAME"]
    lookback_days = int(os.environ.get("LOOKBACK_DAYS", "7"))

    # クライアント初期化
    github_client = GitHubClient(github_token_secret, github_owner, github_repo)
    llm_extractor = LLMExtractor()
    s3_handler = S3Handler(s3_bucket)

    try:
        # 1. 未抽出の日記を検出
        unextracted_dates = get_unextracted_dates(
            github_client, s3_handler, lookback_days
        )

        logger.info(f"未抽出の日記: {len(unextracted_dates)}件")

        if not unextracted_dates:
            logger.info("抽出対象の日記がありません")
            return {"statusCode": 200, "body": "抽出対象なし"}

        # 2. 各日記を抽出
        success_count = 0
        skip_count = 0
        error_count = 0

        for date_str in unextracted_dates:
            try:
                # 日記取得
                diary_content = github_client.get_diary_content(date_str)
                if not diary_content:
                    logger.info(f"日記が存在しないためスキップ: {date_str}")
                    skip_count += 1
                    continue

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
                success_count += 1

            except Exception as e:
                logger.error(f"抽出失敗: {date_str}, error={e}")
                error_count += 1
                continue

        # 3. 結果サマリー
        result = {
            "statusCode": 200,
            "body": {
                "total": len(unextracted_dates),
                "success": success_count,
                "skip": skip_count,
                "error": error_count,
            },
        }

        logger.info(
            f"バッチ完了: 成功={success_count}, スキップ={skip_count}, エラー={error_count}"
        )
        return result

    except Exception as e:
        logger.error(f"バッチ処理でエラー発生: {e}")
        return {"statusCode": 500, "body": f"エラー: {str(e)}"}


def get_unextracted_dates(
    github_client: GitHubClient, s3_handler: S3Handler, lookback_days: int
) -> List[str]:
    """
    未抽出の日記日付リストを取得

    Args:
        github_client: GitHubクライアント
        s3_handler: S3ハンドラー
        lookback_days: 遡る日数

    Returns:
        未抽出の日付リスト（YYYY-MM-DD形式）
    """
    # 過去N日分の日付リスト
    diary_dates = github_client.get_diary_dates(lookback_days)
    logger.info(f"対象期間: 過去{lookback_days}日")

    # 既にdraftが存在する日付リスト
    draft_dates = s3_handler.get_draft_dates()
    logger.info(f"既存draft: {len(draft_dates)}件")

    # 差分を計算（日記は存在するが、draftがない日付）
    unextracted = [date for date in diary_dates if date not in draft_dates]

    return unextracted