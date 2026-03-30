"""S3ハンドラー - draft保存用"""

import json
import logging
from datetime import datetime
from typing import List, Dict, Any
import boto3

logger = logging.getLogger()
logger.setLevel(logging.INFO)


class S3Handler:
    """S3にdraftを保存・管理するハンドラー"""

    def __init__(self, bucket_name: str):
        """
        S3ハンドラーを初期化

        Args:
            bucket_name: S3バケット名
        """
        self.s3 = boto3.client("s3")
        self.bucket = bucket_name

    def get_draft_dates(self) -> List[str]:
        """
        draft/に存在する日付リストを取得

        Returns:
            YYYY-MM-DD形式の日付文字列のリスト
        """
        try:
            response = self.s3.list_objects_v2(
                Bucket=self.bucket, Prefix="draft/", Delimiter="/"
            )

            if "CommonPrefixes" not in response:
                return []

            # draft/YYYY-MM-DD/ のディレクトリ一覧から日付を抽出
            dates = []
            for prefix in response["CommonPrefixes"]:
                # "draft/2026-03-22/" -> "2026-03-22"
                date_str = prefix["Prefix"].replace("draft/", "").replace("/", "")
                if date_str:  # 空文字列を除外
                    dates.append(date_str)

            return dates

        except Exception as e:
            logger.error(f"draft一覧の取得に失敗: {e}")
            return []

    def save_draft(
        self, date_str: str, diary_content: str, extracted: Dict[str, Any]
    ) -> None:
        """
        抽出結果をdraftとしてS3に保存

        Args:
            date_str: YYYY-MM-DD形式の日付
            diary_content: 元の日記内容
            extracted: 抽出結果（references, ideas, goalsを含む辞書）
        """
        prefix = f"draft/{date_str}/"

        try:
            # metadata.json
            metadata = {
                "diary_date": date_str,
                "extracted_at": datetime.utcnow().isoformat() + "Z",
                "diary_path": self._get_diary_path(date_str),
                "model_id": "jp.anthropic.claude-haiku-4-5-20251001-v1:0",
                "extraction_status": "success",
            }
            self._put_object(
                prefix + "metadata.json", json.dumps(metadata, ensure_ascii=False, indent=2)
            )

            # original.md（元の日記）
            self._put_object(prefix + "original.md", diary_content)

            # references.md
            refs_md = self._format_references(date_str, extracted.get("references", []))
            if refs_md:  # 空でない場合のみ保存
                self._put_object(prefix + "references.md", refs_md)

            # ideas.md
            ideas_md = self._format_ideas(date_str, extracted.get("ideas", []))
            if ideas_md:
                self._put_object(prefix + "ideas.md", ideas_md)

            # goals.md
            goals_md = self._format_goals(date_str, extracted.get("goals", []))
            if goals_md:
                self._put_object(prefix + "goals.md", goals_md)

            logger.info(f"draftを保存: {date_str}")

        except Exception as e:
            logger.error(f"draftの保存に失敗 ({date_str}): {e}")
            raise

    def _put_object(self, key: str, body: str) -> None:
        """S3にオブジェクトを保存"""
        self.s3.put_object(Bucket=self.bucket, Key=key, Body=body.encode("utf-8"))

    def _get_diary_path(self, date_str: str) -> str:
        """日付文字列からGitHubファイルパスを生成"""
        year, month, _ = date_str.split("-")
        return f"daily/{year}/{month}/{date_str}.md"

    def _format_references(self, date_str: str, references: List[Dict[str, str]]) -> str:
        """references を Markdown 形式にフォーマット"""
        if not references:
            return ""

        lines = [f"# {date_str} 参考情報\n"]
        for ref in references:
            topic = ref.get("topic", "")
            content = ref.get("content", "")
            if topic and content:
                lines.append(f"## {topic}\n{content}\n")

        return "\n".join(lines)

    def _format_ideas(self, date_str: str, ideas: List[Dict[str, str]]) -> str:
        """ideas を Markdown 形式にフォーマット"""
        if not ideas:
            return ""

        lines = [f"# {date_str} アイデア\n"]
        for idea in ideas:
            content = idea.get("content", "")
            if content:
                lines.append(f"- {content}\n")

        return "\n".join(lines)

    def _format_goals(self, date_str: str, goals: List[Dict[str, str]]) -> str:
        """goals を Markdown 形式にフォーマット"""
        if not goals:
            return ""

        lines = [f"# {date_str} 中長期目標\n"]
        for goal in goals:
            content = goal.get("content", "")
            if content:
                lines.append(f"- {content}\n")

        return "\n".join(lines)