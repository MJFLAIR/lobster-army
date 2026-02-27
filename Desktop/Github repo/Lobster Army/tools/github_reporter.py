import os
import json
import logging
from typing import Dict, Any, Optional
from tools.network_client import NetworkClient, NetworkPolicyError
from workflows.storage.db import DB
from workflows.models.task import Task
from google.api_core.exceptions import AlreadyExists
from google.cloud import firestore
from datetime import datetime, timezone

REPORTER_VERSION = "0.2.0"

class GitHubReporter:
    def __init__(self):
        self.enabled = os.environ.get("GITHUB_REPORTER_ENABLED", "0") in ("1", "true", "True")
        self.token = os.environ.get("GITHUB_TOKEN", "").strip()
        self.repo = os.environ.get("GITHUB_REPO", "").strip()
        self.api_base = os.environ.get("GITHUB_API_BASE", "https://api.github.com").rstrip("/")
        self.network_client = NetworkClient()

    def render_review_comment(self, task: Task, review_payload: dict) -> str:
        """
        Renders the review comment body from the ReviewAgent payload.
        """
        status = review_payload.get("status", "UNKNOWN")
        score = review_payload.get("score", "N/A")
        comments = review_payload.get("comments", "No comments provided.")
        
        meta = task.meta_json or {}
        head_sha = meta.get("head_sha") or meta.get("pull_request", {}).get("head", {}).get("sha")
        short_sha = head_sha[:7] if head_sha else "unknown"
        utc_iso_timestamp = datetime.now(timezone.utc).isoformat()
        
        body = (
            f"### 🦞 Lobster Army Review Report\n\n"
            f"**Status:** {status}\n"
            f"**Score:** {score}\n\n"
            f"**Comments:**\n{comments}\n\n"
            f"---\n"
            f"Lobster Army Review Bot v{REPORTER_VERSION}\n"
            f"task_id: {task.task_id}\n"
            f"commit: {short_sha}\n"
            f"generated_at: {utc_iso_timestamp}"
        )
        return body

    def post_pr_comment(self, pr_number: int, body: str, repo: Optional[str] = None) -> Dict[str, Any]:
        """
        Posts a comment to a GitHub PR using the NetworkClient.
        """
        if not self.enabled:
            return {"ok": False, "skipped": True, "reason": "reporter_disabled"}
            
        if not self.token:
            return {"ok": False, "skipped": True, "reason": "missing_token"}
            
        target_repo = repo or self.repo
        if not target_repo:
            return {"ok": False, "skipped": True, "reason": "missing_repo"}

        url = f"{self.api_base}/repos/{target_repo}/issues/{pr_number}/comments"
        headers = {
            "Authorization": f"Bearer {self.token}",
            "Accept": "application/vnd.github+json",
            "Content-Type": "application/json",
            "X-GitHub-Api-Version": "2022-11-28"
        }
        
        payload_bytes = json.dumps({"body": body}).encode("utf-8")
        
        try:
            response_bytes = self.network_client.request(
                method="POST",
                url=url,
                headers=headers,
                body=payload_bytes
            )
            response_data = json.loads(response_bytes.decode("utf-8"))
            return {"ok": True, "response": response_data}
        except NetworkPolicyError as e:
            return {"ok": False, "skipped": True, "error": str(e), "reason": "network_policy"}
        except Exception as e:
            return {"ok": False, "skipped": False, "error": str(e), "reason": "request_failed"}

    def run_hook(self, task: Task, review_payload: dict) -> None:
        """
        Main entrypoint to run after task is settled to DONE.
        """
        if task.source != "github_pr":
            return
            
        meta = task.meta_json or {}
        pr_info = meta.get("pull_request", {})
        repo_info = meta.get("repository", {})
        
        pr_number = pr_info.get("number")
        head_sha = pr_info.get("head", {}).get("sha")
        repo_full_name = repo_info.get("full_name") or self.repo
        
        if not pr_number or not head_sha or not repo_full_name:
            DB.emit_event(task.task_id, "GITHUB_REPORTER_ERROR", {
                "reason": "missing_metadata",
                "task_id": task.task_id
            })
            return
            
        # 1. Dedup Guard
        dedup_key = f"{repo_full_name}:{pr_number}:{head_sha}".replace("/", "_")
        dedup_ref = DB.get_client().collection("pr_report_dedup").document(dedup_key)
        
        try:
            dedup_ref.create({
                "task_id": task.task_id,
                "repo": repo_full_name,
                "pr_number": pr_number,
                "head_sha": head_sha,
                "created_at": firestore.SERVER_TIMESTAMP
            })
        except AlreadyExists:
            DB.emit_event(task.task_id, "GITHUB_REPORTER_SKIPPED", {
                "reason": "duplicate",
                "pr_number": pr_number,
                "repo": repo_full_name,
                "head_sha": head_sha,
                "task_id": task.task_id
            })
            return
            
        # 2. Render and Post
        body = self.render_review_comment(task, review_payload)
        res = self.post_pr_comment(pr_number, body, repo=repo_full_name)
        
        if res.get("ok"):
            DB.emit_event(task.task_id, "GITHUB_REPORTER_POSTED", {
                "pr_number": pr_number,
                "repo": repo_full_name,
                "head_sha": head_sha,
                "task_id": task.task_id
            })
        else:
            DB.emit_event(task.task_id, "GITHUB_REPORTER_SKIPPED" if res.get("skipped") else "GITHUB_REPORTER_ERROR", {
                "reason": res.get("reason"),
                "error": res.get("error"),
                "pr_number": pr_number,
                "repo": repo_full_name,
                "head_sha": head_sha,
                "task_id": task.task_id
            })
