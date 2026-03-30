"""GitHub API クライアント - 日記取得用"""

import os
import json
import logging
from datetime import datetime, timedelta
from typing import List, Optional
import boto3
import requests

logger = logging.getLogger()
logger.setLevel(logging.INFO)


class GitHubClient:
    """GitHub APIを使って日記を取得するクライアント"""

    def __init__(self, token_secret_name: str, owner: str, repo: str):
        """
        GitHub API クライアントを初期化

        Args:
            token_secret_name: AWS Secrets ManagerのGitHub PAT シークレット名
            owner: GitHubリポジトリオーナー
            repo: GitHubリポジトリ名
        """
        self.owner = owner
        self.repo = repo
        self.base_url = f"https://api.github.com/repos/{owner}/{repo}"
        self.token = self._get_token_from_secrets_manager(token_secret_name)
        self.headers = {
            "Authorization": f"Bearer {self.token}",
            "Accept": "application/vnd.github.v3+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }

    def _get_token_from_secrets_manager(self, secret_name: str) -> str:
        """AWS Secrets ManagerからGitHub PATを取得"""
        secrets_client = boto3.client("secretsmanager")
        try:
            response = secrets_client.get_secret_value(SecretId=secret_name)
            secret_data = json.loads(response["SecretString"])
            # Secretは {"github_token": "ghp_..."} または plain string で保存される
            if isinstance(secret_data, dict):
                return secret_data.get("github_token", secret_data.get("token", ""))
            return secret_data
        except Exception as e:
            logger.error(f"GitHub トークンの取得に失敗: {e}")
            raise

    def get_diary_dates(self, lookback_days: int) -> List[str]:
        """
        過去N日分の日記日付リストを取得

        Args:
            lookback_days: 遡る日数

        Returns:
            YYYY-MM-DD形式の日付文字列のリスト
        """
        dates = []
        today = datetime.now().date()

        for i in range(lookback_days):
            date = today - timedelta(days=i)
            dates.append(date.strftime("%Y-%m-%d"))

        return dates

    def diary_exists(self, date_str: str) -> bool:
        """
        指定日付の日記ファイルが存在するかチェック

        Args:
            date_str: YYYY-MM-DD形式の日付

        Returns:
            日記が存在すればTrue、存在しなければFalse
        """
        diary_path = self._get_diary_path(date_str)
        url = f"{self.base_url}/contents/{diary_path}"

        try:
            response = requests.get(url, headers=self.headers, timeout=10)
            return response.status_code == 200
        except requests.RequestException as e:
            logger.warning(f"日記の存在確認エラー ({date_str}): {e}")
            return False

    def get_diary_content(self, date_str: str) -> Optional[str]:
        """
        GitHubから日記内容を取得

        Args:
            date_str: YYYY-MM-DD形式の日付（例: "2026-03-22"）

        Returns:
            日記の内容（文字列）、存在しない場合はNone
        """
        diary_path = self._get_diary_path(date_str)
        url = f"{self.base_url}/contents/{diary_path}"

        try:
            # Raw content をリクエスト
            headers = {**self.headers, "Accept": "application/vnd.github.v3.raw"}
            response = requests.get(url, headers=headers, timeout=10)

            if response.status_code == 404:
                logger.info(f"日記が見つかりません: {date_str}")
                return None

            response.raise_for_status()
            return response.text

        except requests.RequestException as e:
            logger.error(f"日記の取得に失敗 ({date_str}): {e}")
            return None

    def _get_diary_path(self, date_str: str) -> str:
        """
        日付文字列をGitHubファイルパスに変換

        Args:
            date_str: YYYY-MM-DD形式の日付

        Returns:
            GitHubファイルパス（例: "daily/2026/03/2026-03-22.md"）
        """
        date_obj = datetime.strptime(date_str, "%Y-%m-%d")
        year = date_obj.strftime("%Y")
        month = date_obj.strftime("%m")
        filename = f"{date_str}.md"

        return f"daily/{year}/{month}/{filename}"