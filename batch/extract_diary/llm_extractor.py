"""LLM抽出ロジック - Bedrock Converse API使用"""

import json
import logging
from typing import Dict, Any, List
import boto3

logger = logging.getLogger()
logger.setLevel(logging.INFO)


class LLMExtractor:
    """LLMを使って日記から知識・アイデア・目標を抽出"""

    def __init__(self):
        """LLM抽出器を初期化"""
        self.bedrock = boto3.client("bedrock-runtime")
        self.model_id = "jp.anthropic.claude-haiku-4-5-20251001-v1:0"

    def extract(self, diary_content: str) -> Dict[str, List[Dict[str, str]]]:
        """
        日記から3ジャンル（references, ideas, goals）を抽出

        Args:
            diary_content: 日記の内容

        Returns:
            抽出結果の辞書
            {
                "references": [{"topic": "...", "content": "..."}],
                "ideas": [{"content": "..."}],
                "goals": [{"content": "..."}]
            }
        """
        prompt = self._build_prompt(diary_content)

        try:
            # スキーマ定義
            schema = {
                "type": "object",
                "properties": {
                    "references": {
                        "type": "array",
                        "description": "客観的知識・学んだこと",
                        "items": {
                            "type": "object",
                            "properties": {
                                "topic": {
                                    "type": "string",
                                    "description": "知識の主題（例: AWS AgentCore Gateway）",
                                },
                                "content": {
                                    "type": "string",
                                    "description": "知識の内容",
                                },
                            },
                            "required": ["topic", "content"],
                            "additionalProperties": False,
                        },
                    },
                    "ideas": {
                        "type": "array",
                        "description": "アイデア・TODO",
                        "items": {
                            "type": "object",
                            "properties": {
                                "content": {
                                    "type": "string",
                                    "description": "アイデアの内容",
                                }
                            },
                            "required": ["content"],
                            "additionalProperties": False,
                        },
                    },
                    "goals": {
                        "type": "array",
                        "description": "中長期目標",
                        "items": {
                            "type": "object",
                            "properties": {
                                "content": {
                                    "type": "string",
                                    "description": "目標の内容",
                                }
                            },
                            "required": ["content"],
                            "additionalProperties": False,
                        },
                    },
                },
                "required": ["references", "ideas", "goals"],
                "additionalProperties": False,
            }

            # Bedrock Structured Outputs を使用 (Converse API)
            response = self.bedrock.converse(
                modelId=self.model_id,
                messages=[{"role": "user", "content": [{"text": prompt}]}],
                outputConfig={
                    "textFormat": {
                        "type": "json_schema",
                        "structure": {
                            "jsonSchema": {
                                "schema": json.dumps(schema),  # JSON文字列として渡す
                                "name": "diary_extraction_schema",  # 必須
                                "description": "日記から知識・アイデア・目標を抽出するスキーマ",
                            }
                        },
                    }
                },
            )

            # JSON レスポンスをパース
            output_text = response["output"]["message"]["content"][0]["text"]
            extracted_data = json.loads(output_text)

            logger.info(
                f"抽出完了: references={len(extracted_data.get('references', []))}, "
                f"ideas={len(extracted_data.get('ideas', []))}, "
                f"goals={len(extracted_data.get('goals', []))}"
            )
            return extracted_data

        except json.JSONDecodeError as e:
            logger.error(f"JSON パースエラー: {e}")
            # フォールバック: 空の結果を返す
            return {"references": [], "ideas": [], "goals": []}
        except Exception as e:
            logger.error(f"LLM抽出に失敗: {e}")
            raise

    def _build_prompt(self, diary_content: str) -> str:
        """抽出用のプロンプトを構築"""
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