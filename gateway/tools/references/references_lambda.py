import json
import logging
import os
from datetime import datetime
from typing import List, Optional

import boto3

logger = logging.getLogger()
logger.setLevel(logging.INFO)

s3_client = boto3.client("s3")
bedrock_client = boto3.client("bedrock-runtime")


def filter_by_date(
    file_keys: List[str], date_from: Optional[str] = None, date_to: Optional[str] = None
) -> List[str]:
    """
    日付プレフィックス（YYYY-MM-DD）でS3ファイルキーをフィルタリング

    Args:
        file_keys: S3オブジェクトキーのリスト（例: "draft/2026-02-10/references.md"）
        date_from: 開始日（YYYY-MM-DD形式、この日を含む）
        date_to: 終了日（YYYY-MM-DD形式、この日を含む）

    Returns:
        フィルタリングされたファイルキーのリスト
    """
    if not date_from and not date_to:
        return file_keys

    filtered = []
    for key in file_keys:
        # パスの2番目のセグメントから日付を抽出: "draft/YYYY-MM-DD/references.md"
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


def select_files_with_llm(file_keys: List[str], query: str, max_files: int = 3) -> List[str]:
    """
    LLMを使用してクエリに基づき関連ファイルを選択（構造化出力版）

    Args:
        file_keys: S3オブジェクトキーのリスト
        query: ユーザーの検索クエリ
        max_files: 選択する最大ファイル数

    Returns:
        選択されたファイルキーのリスト
    """
    if not file_keys:
        return []

    # LLM用に日付を抽出（全ファイルが "references.md" という同名のため日付で区別）
    dates = [key.split("/")[1] for key in file_keys]

    # シンプルなプロンプト（構造化出力がスキーマを強制）
    prompt = f"""以下の日記知識ファイルから、ユーザーのクエリに関連するものを最大{max_files}個選択してください。

クエリ: {query}

ファイル一覧（日付形式: YYYY-MM-DD）:
{chr(10).join(f"{i+1}. {d}" for i, d in enumerate(dates))}"""

    # 構造化出力のJSONスキーマ
    json_schema = {
        "type": "object",
        "properties": {
            "selected_file_indices": {
                "type": "array",
                "items": {"type": "integer", "minimum": 1, "maximum": len(file_keys)},
                "maxItems": max_files,
                "description": "選択されたファイルの番号（1ベース）",
            }
        },
        "required": ["selected_file_indices"],
        "additionalProperties": False,
    }

    # Bedrock Haiku 4.5を呼び出し（Structured Outputs）
    response = bedrock_client.invoke_model(
        modelId="jp.anthropic.claude-haiku-4-5-20251001-v1:0",
        body=json.dumps(
            {
                "anthropic_version": "bedrock-2023-05-31",
                "max_tokens": 200,
                "messages": [{"role": "user", "content": prompt}],
                "output_config": {"format": {"type": "json_schema", "schema": json_schema}},
            }
        ),
    )

    result = json.loads(response["body"].read())
    llm_output = result["content"][0]["text"]

    logger.info(f"LLM response: {llm_output}")

    data = json.loads(llm_output)
    selected_indices = data["selected_file_indices"]

    # 1ベースのインデックスをファイルキーに変換
    selected_keys = []
    for idx in selected_indices:
        if 1 <= idx <= len(file_keys):
            selected_keys.append(file_keys[idx - 1])

    logger.info(f"Selected {len(selected_keys)} files from {len(file_keys)} candidates")

    return selected_keys[:max_files]


def get_file_contents(bucket: str, file_keys: List[str]) -> str:
    """
    複数のS3ファイルの内容を取得

    Args:
        bucket: S3バケット名
        file_keys: S3オブジェクトキーのリスト

    Returns:
        改行で区切られた結合されたファイル内容
    """
    contents = []
    for key in file_keys:
        try:
            response = s3_client.get_object(Bucket=bucket, Key=key)
            content = response["Body"].read().decode("utf-8")
            contents.append(f"# ファイル: {key}\n\n{content}")
        except Exception as e:
            logger.error(f"Error reading file {key}: {str(e)}")
            contents.append(f"# ファイル: {key}\n\nエラー: ファイルの読み取りに失敗しました")

    return "\n\n---\n\n".join(contents)


def handler(event, context):
    """
    日記インサイト用の参考情報検索Lambda関数

    このLambdaはget_referencesツールを実装し、以下を実行します：
    1. S3のreferences/ディレクトリからファイル一覧を取得
    2. 日付範囲でフィルタリング（オプション）
    3. クエリに基づきLLMで関連ファイルを選択
    4. 選択されたファイルの内容を返す

    Args:
        event (dict): ツール引数（query, date_from, date_to）
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

        if tool_name == "get_references":
            # 引数を取得
            query = event.get("query")
            if not query:
                return {"error": "query parameter is required"}

            date_from = event.get("date_from")
            date_to = event.get("date_to")

            # S3からファイル一覧を取得
            logger.info(f"Listing files from s3://{bucket_name}/draft/")
            response = s3_client.list_objects_v2(Bucket=bucket_name, Prefix="draft/")

            if "Contents" not in response:
                return {"content": [{"type": "text", "text": "知識ファイルが見つかりませんでした。"}]}

            file_keys = [obj["Key"] for obj in response["Contents"] if obj["Key"].endswith("/references.md")]

            # 日付でフィルタリング
            filtered_keys = filter_by_date(file_keys, date_from, date_to)
            logger.info(f"Files after date filter: {len(filtered_keys)}")

            if not filtered_keys:
                return {"content": [{"type": "text", "text": "指定期間内の知識ファイルが見つかりませんでした。"}]}

            # LLMでファイルを選択
            selected_keys = select_files_with_llm(filtered_keys, query)
            logger.info(f"Selected files: {selected_keys}")

            if not selected_keys:
                return {"content": [{"type": "text", "text": f"クエリ「{query}」に関連する知識ファイルが見つかりませんでした。"}]}

            # ファイル内容を取得
            contents = get_file_contents(bucket_name, selected_keys)

            return {"content": [{"type": "text", "text": contents}]}
        else:
            logger.error(f"Unexpected tool name: {tool_name}")
            return {"error": f"This Lambda only supports 'get_references', received: {tool_name}"}

    except Exception as e:
        logger.error(f"Error processing request: {str(e)}", exc_info=True)
        return {"error": f"Internal server error: {str(e)}"}