import json
import logging
import os
from datetime import datetime
from typing import List, Optional

import boto3

logger = logging.getLogger()
logger.setLevel(logging.INFO)

s3_client = boto3.client("s3")


def filter_by_date(
    file_keys: List[str], date_from: Optional[str] = None, date_to: Optional[str] = None
) -> List[str]:
    """
    日付プレフィックス（YYYY-MM-DD）でS3ファイルキーをフィルタリング

    Args:
        file_keys: S3オブジェクトキーのリスト（例: "draft/2026-02-10/ideas.md"）
        date_from: 開始日（YYYY-MM-DD形式、この日を含む）
        date_to: 終了日（YYYY-MM-DD形式、この日を含む）

    Returns:
        フィルタリングされたファイルキーのリスト
    """
    if not date_from and not date_to:
        return file_keys

    filtered = []
    for key in file_keys:
        # パスの2番目のセグメントから日付を抽出: "draft/YYYY-MM-DD/ideas.md"
        parts = key.split("/")
        if len(parts) < 3:
            continue
        date_segment = parts[1]
        if len(date_segment) < 10:
            continue

        try:
            file_date = date_segment  # "YYYY-MM-DD"を抽出
            datetime.strptime(file_date, "%Y-%m-%d")  # フォーマット検証

            # 日付フィルタを適用
            if date_from and file_date < date_from:
                continue
            if date_to and file_date > date_to:
                continue

            filtered.append(key)
        except ValueError:
            # 無効な日付形式のファイルはスキップ
            logger.warning(f"Skipping file with invalid date format: {key}")
            continue

    return filtered


def get_file_contents(bucket: str, file_keys: List[str]) -> str:
    """
    複数のS3ファイルの内容を取得

    Args:
        bucket: S3バケット名
        file_keys: S3オブジェクトキーのリスト

    Returns:
        改行で区切られた結合されたファイル内容
    """
    if not file_keys:
        return ""

    contents = []
    for key in file_keys:
        try:
            response = s3_client.get_object(Bucket=bucket, Key=key)
            content = response["Body"].read().decode("utf-8")
            contents.append(f"# ファイル: {key}\n\n{content}")
        except Exception as e:
            logger.error(f"Error reading file {key}: {str(e)}")
            contents.append(
                f"# ファイル: {key}\n\nエラー: ファイルの読み取りに失敗しました"
            )

    return "\n\n---\n\n".join(contents)


def handler(event, context):
    """
    日記インサイト用のアイデア・目標取得Lambda関数

    このLambdaはget_ideasとget_goalsの両ツールを実装し、以下を実行します：
    1. S3のideas/またはgoals/ディレクトリからファイル一覧を取得（ツール名に基づく）
    2. 日付範囲でフィルタリング（オプション）
    3. マッチした全ファイルの内容を返す

    Args:
        event (dict): ツール引数（date_from, date_to）
        context: AgentCoreメタデータを含むLambdaコンテキスト

    Returns:
        dict: 'content'配列または'error'文字列を含むレスポンス
    """
    logger.info(f"Received event: {json.dumps(event)}")

    try:
        # 環境変数からS3バケット名を取得
        bucket_name = os.environ.get("S3_BUCKET_NAME")
        if not bucket_name:
            return {"error": "S3_BUCKET_NAME environment variable not set"}

        # コンテキストからツール名を取得
        delimiter = "___"
        original_tool_name = context.client_context.custom["bedrockAgentCoreToolName"]
        tool_name = original_tool_name[
            original_tool_name.index(delimiter) + len(delimiter) :
        ]

        logger.info(f"Processing tool: {tool_name}")

        # ツール名に基づきファイルサフィックスを決定
        if tool_name == "get_ideas":
            file_suffix = "/ideas.md"
            content_type = "アイデア・TODO"
        elif tool_name == "get_goals":
            file_suffix = "/goals.md"
            content_type = "中長期目標"
        elif tool_name == "get_references":
            file_suffix = "/references.md"
            content_type = "参考情報・知識"
        else:
            logger.error(f"Unexpected tool name: {tool_name}")
            return {
                "error": f"This Lambda only supports 'get_ideas', 'get_goals', and 'get_references', received: {tool_name}"
            }

        # 引数を取得
        date_from = event.get("date_from")
        date_to = event.get("date_to")

        # S3からファイル一覧を取得
        logger.info(f"Listing files from s3://{bucket_name}/draft/")
        response = s3_client.list_objects_v2(Bucket=bucket_name, Prefix="draft/")

        if "Contents" not in response:
            return {
                "content": [
                    {
                        "type": "text",
                        "text": f"{content_type}ファイルが見つかりませんでした。",
                    }
                ]
            }

        file_keys = [
            obj["Key"]
            for obj in response["Contents"]
            if obj["Key"].endswith(file_suffix)
        ]

        # 日付でフィルタリング
        filtered_keys = filter_by_date(file_keys, date_from, date_to)
        logger.info(f"Files after date filter: {len(filtered_keys)}")

        if not filtered_keys:
            return {
                "content": [
                    {
                        "type": "text",
                        "text": f"指定期間内の{content_type}ファイルが見つかりませんでした。",
                    }
                ]
            }

        # 全ファイルの内容を取得
        contents = get_file_contents(bucket_name, filtered_keys)

        if not contents:
            return {
                "content": [
                    {"type": "text", "text": f"{content_type}が見つかりませんでした。"}
                ]
            }

        return {"content": [{"type": "text", "text": contents}]}

    except Exception as e:
        logger.error(f"Error processing request: {str(e)}", exc_info=True)
        return {"error": f"Internal server error: {str(e)}"}
