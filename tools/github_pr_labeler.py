import os
import json
import logging
from typing import Dict, Any, Optional, List
from tools.network_client import NetworkClient, NetworkPolicyError
from workflows.storage.db import DB
from workflows.models.task import Task
from google.api_core.exceptions import AlreadyExists
from google.cloud import firestore

LABELER_VERSION = "0.3.0"

class GitHubPRLabeler:
    def __init__(self):
        self.enabled = os.environ.get("GITHUB_LABELER_ENABLED", "0") in ("1", "true", "True")
        self.token = os.environ.get("GITHUB_TOKEN", "").strip()
        self.default_repo = os.environ.get("GITHUB_REPO", "").strip()
        self.api_base = os.environ.get("GITHUB_API_BASE", "https://api.github.com").rstrip("/")
        self.network_client = NetworkClient()

    def resolve_repo(self, task: Task) -> Optional[str]:
        meta = task.meta_json or {}
        repo_info = meta.get("repository", {})
        return repo_info.get("full_name") or self.default_repo

    def resolve_pr_number(self, task: Task) -> Optional[int]:
        meta = task.meta_json or {}
        pr_info = meta.get("pull_request", {})
        return pr_info.get("number")

    def resolve_head_sha(self, task: Task) -> Optional[str]:
        meta = task.meta_json or {}
        return meta.get("head_sha") or meta.get("pull_request", {}).get("head", {}).get("sha")

    def decide_labels(self, review_result: dict) -> List[str]:
        labels = ["lobster:reviewed"]
        
        status = review_result.get("status")
        if status is not None:
            if isinstance(status, str) and status.lower() in ("pass", "approved", "ok"):
                labels.append("lobster:approved")
            else:
                labels.append("lobster:changes-requested")
        else:
            score = review_result.get("score")
            if score is not None and isinstance(score, (int, float)) and score >= 0.8:
                labels.append("lobster:approved")
            else:
                labels.append("lobster:changes-requested")
                
        return labels

    def post_labels(self, repo_full_name: str, pr_number: int, labels: List[str]) -> Dict[str, Any]:
        if not self.enabled:
            return {"ok": False, "skipped": True, "reason": "labeler_disabled"}
            
        if not self.token:
            return {"ok": False, "skipped": True, "reason": "missing_token"}
            
        url = f"{self.api_base}/repos/{repo_full_name}/issues/{pr_number}/labels"
        headers = {
            "Authorization": f"Bearer {self.token}",
            "Accept": "application/vnd.github+json",
            "Content-Type": "application/json",
            "X-GitHub-Api-Version": "2022-11-28"
        }
        
        payload_bytes = json.dumps({"labels": labels}).encode("utf-8")
        
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

    def run_hook(self, task: Task, review_result: dict) -> None:
        if task.source != "github_pr":
            return
            
        repo_full_name = self.resolve_repo(task)
        pr_number = self.resolve_pr_number(task)
        head_sha = self.resolve_head_sha(task)
        
        if not self.enabled or not self.token:
            DB.emit_event(task.task_id, "GITHUB_PR_LABELER_SKIPPED", {
                "reason": "disabled_or_missing_token",
                "task_id": task.task_id
            })
            return

        if not pr_number or not head_sha or not repo_full_name:
            DB.emit_event(task.task_id, "GITHUB_PR_LABELER_ERROR", {
                "reason": "missing_metadata",
                "task_id": task.task_id
            })
            return

        decided_labels = self.decide_labels(review_result)
        labels_to_post = []
        
        for label in decided_labels:
            dedup_key = f"{repo_full_name}:{pr_number}:{head_sha}:{label}".replace("/", "_")
            dedup_ref = DB.get_client().collection("pr_label_dedup").document(dedup_key)
            
            try:
                dedup_ref.create({
                    "task_id": task.task_id,
                    "repo": repo_full_name,
                    "pr_number": pr_number,
                    "head_sha": head_sha,
                    "label": label,
                    "version": LABELER_VERSION,
                    "created_at": firestore.SERVER_TIMESTAMP
                })
                labels_to_post.append(label)
            except AlreadyExists:
                DB.emit_event(task.task_id, "GITHUB_PR_LABELER_SKIPPED", {
                    "reason": "duplicate",
                    "pr_number": pr_number,
                    "repo": repo_full_name,
                    "head_sha": head_sha,
                    "label": label,
                    "task_id": task.task_id
                })
                continue
                
        if labels_to_post:
            res = self.post_labels(repo_full_name, pr_number, labels_to_post)
            if res.get("ok"):
                DB.emit_event(task.task_id, "GITHUB_PR_LABELER_POSTED", {
                    "pr_number": pr_number,
                    "repo": repo_full_name,
                    "head_sha": head_sha,
                    "labels": labels_to_post,
                    "task_id": task.task_id
                })
            else:
                DB.emit_event(task.task_id, "GITHUB_PR_LABELER_SKIPPED" if res.get("skipped") else "GITHUB_PR_LABELER_ERROR", {
                    "reason": res.get("reason"),
                    "error": res.get("error"),
                    "pr_number": pr_number,
                    "repo": repo_full_name,
                    "head_sha": head_sha,
                    "task_id": task.task_id
                })
