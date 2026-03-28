from __future__ import annotations
import os
import requests
from typing import Dict, Any, Optional

class GitHubClient:
    def __init__(self, token: Optional[str] = None):
        self.token = token or os.getenv("GITHUB_TOKEN")
        if not self.token:
            raise RuntimeError("missing_github_token")
        self.base = "https://api.github.com"

    def post_pr_comment(self, repo: str, pr_number: int, body: str) -> Dict[str, Any]:
        """
        POST /repos/{owner}/{repo}/issues/{issue_number}/comments
        PR comments are issue comments.
        """
        url = f"{self.base}/repos/{repo}/issues/{pr_number}/comments"
        headers = {
            "Authorization": f"token {self.token}",
            "Accept": "application/vnd.github+json",
            "User-Agent": "lobster-army",
        }
        resp = requests.post(url, headers=headers, json={"body": body}, timeout=15)
        resp.raise_for_status()
        return resp.json()

    def add_issue_labels(self, repo: str, pr_number: int, labels: list[str]) -> Dict[str, Any]:
        """
        POST /repos/{owner}/{repo}/issues/{issue_number}/labels
        PR labels are issue labels.
        """
        url = f"{self.base}/repos/{repo}/issues/{pr_number}/labels"
        headers = {
            "Authorization": f"token {self.token}",
            "Accept": "application/vnd.github+json",
            "User-Agent": "lobster-army",
        }
        resp = requests.post(url, headers=headers, json={"labels": labels}, timeout=15)
        resp.raise_for_status()
        return resp.json()

    def merge_pull_request(self, repo: str, pr_number: int, merge_method: str = "squash") -> Dict[str, Any]:
        """
        PUT /repos/{owner}/{repo}/pulls/{pull_number}/merge
        merge_method: merge | squash | rebase
        """
        url = f"{self.base}/repos/{repo}/pulls/{pr_number}/merge"
        headers = {
            "Authorization": f"token {self.token}",
            "Accept": "application/vnd.github+json",
            "User-Agent": "lobster-army",
        }
        payload = {"merge_method": merge_method}
        resp = requests.put(url, headers=headers, json=payload, timeout=20)
        resp.raise_for_status()
        return resp.json()
