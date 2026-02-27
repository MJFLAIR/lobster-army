import os
import json
import logging
import urllib.parse
from typing import Dict, Any, Optional

from tools.network_client import NetworkClient, NetworkPolicyError
from workflows.storage.db import DB
from workflows.models.task import Task
from google.api_core.exceptions import AlreadyExists
from google.cloud import firestore

PROPOSAL_VERSION = "0.5.0"

class GitHubPRMergeProposal:
    def __init__(self):
        self.enabled = os.environ.get("GITHUB_MERGE_PROPOSAL_ENABLED", "0") in ("1", "true", "True")
        self.token = os.environ.get("GITHUB_TOKEN", "").strip()
        self.default_repo = os.environ.get("GITHUB_REPO", "").strip()
        self.api_base = os.environ.get("GITHUB_API_BASE", "https://api.github.com").rstrip("/")
        self.candidate_label = os.environ.get("GITHUB_MERGE_CANDIDATE_LABEL", "lobster:merge-candidate").strip()
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

    def decide_gate_outcome(self, review_result: dict) -> str:
        status = review_result.get("status")
        if status is not None and isinstance(status, str):
            if status.lower() in {"pass", "passed", "approve", "approved", "ok"}:
                return "PASS"
            return "BLOCK"
        
        score = review_result.get("score")
        if score is not None and isinstance(score, (int, float)):
            if score >= 0.8:
                return "PASS"
                
        return "BLOCK"

    def add_label(self, repo_full_name: str, pr_number: int, label_name: str) -> None:
        url = f"{self.api_base}/repos/{repo_full_name}/issues/{pr_number}/labels"
        headers = {
            "Authorization": f"Bearer {self.token}",
            "Accept": "application/vnd.github+json",
            "Content-Type": "application/json",
            "X-GitHub-Api-Version": "2022-11-28"
        }
        
        payload_bytes = json.dumps({"labels": [label_name]}).encode("utf-8")
        
        self.network_client.request(
            method="POST",
            url=url,
            headers=headers,
            body=payload_bytes
        )

    def delete_label(self, repo_full_name: str, pr_number: int, label_name: str) -> None:
        encoded_label = urllib.parse.quote(label_name, safe='')
        url = f"{self.api_base}/repos/{repo_full_name}/issues/{pr_number}/labels/{encoded_label}"
        headers = {
            "Authorization": f"Bearer {self.token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28"
        }
        
        try:
            self.network_client.request(
                method="DELETE",
                url=url,
                headers=headers
            )
        except NetworkPolicyError as e:
            logging.error(f"NetworkPolicyError deleting merge label {label_name}: {e}")
        except Exception as e:
            # Can be 404 (not found), safe to ignore
            logging.debug(f"Exception deleting merge label {label_name} (likely not present): {e}")

    def run_hook(self, task: Task, review_result: dict) -> None:
        if task.source != "github_pr":
            DB.emit_event(task.task_id, "GITHUB_PR_MERGE_PROPOSAL_SKIPPED", {
                "reason": "non_pr_source",
                "task_id": task.task_id
            })
            return
            
        repo_full_name = self.resolve_repo(task)
        pr_number = self.resolve_pr_number(task)
        head_sha = self.resolve_head_sha(task)
        
        if not self.enabled:
            DB.emit_event(task.task_id, "GITHUB_PR_MERGE_PROPOSAL_SKIPPED", {
                "reason": "disabled",
                "task_id": task.task_id
            })
            return
            
        if not self.token:
            DB.emit_event(task.task_id, "GITHUB_PR_MERGE_PROPOSAL_SKIPPED", {
                "reason": "missing_token",
                "task_id": task.task_id
            })
            return

        if not pr_number or not head_sha or not repo_full_name:
            DB.emit_event(task.task_id, "GITHUB_PR_MERGE_PROPOSAL_SKIPPED", {
                "reason": "missing_pr_metadata",
                "task_id": task.task_id
            })
            return

        outcome = self.decide_gate_outcome(review_result)
        
        if outcome == "PASS":
            dedup_key = f"{repo_full_name}:{pr_number}:{head_sha}:{self.candidate_label}:{PROPOSAL_VERSION}".replace("/", "_")
            dedup_ref = DB.get_client().collection("pr_merge_candidate_dedup").document(dedup_key)
            
            try:
                dedup_ref.create({
                    "task_id": task.task_id,
                    "repo": repo_full_name,
                    "pr_number": pr_number,
                    "head_sha": head_sha,
                    "label": self.candidate_label,
                    "version": PROPOSAL_VERSION,
                    "created_at": firestore.SERVER_TIMESTAMP
                })
                
                try:
                    self.add_label(repo_full_name, pr_number, self.candidate_label)
                    DB.emit_event(task.task_id, "GITHUB_PR_MERGE_PROPOSAL_POSTED", {
                        "pr_number": pr_number,
                        "repo": repo_full_name,
                        "head_sha": head_sha,
                        "label": self.candidate_label,
                        "task_id": task.task_id
                    })
                except Exception as e:
                    DB.emit_event(task.task_id, "GITHUB_PR_MERGE_PROPOSAL_ERROR", {
                        "error": str(e),
                        "task_id": task.task_id
                    })
            except AlreadyExists:
                DB.emit_event(task.task_id, "GITHUB_PR_MERGE_PROPOSAL_SKIPPED", {
                    "reason": "duplicate",
                    "task_id": task.task_id
                })
        else:
            # BLOCK scenario -> Attempt deletion best effort without required dedup guard
            try:
                self.delete_label(repo_full_name, pr_number, self.candidate_label)
                DB.emit_event(task.task_id, "GITHUB_PR_MERGE_PROPOSAL_REMOVED", {
                    "pr_number": pr_number,
                    "repo": repo_full_name,
                    "head_sha": head_sha,
                    "label": self.candidate_label,
                    "task_id": task.task_id
                })
            except Exception as e:
                DB.emit_event(task.task_id, "GITHUB_PR_MERGE_PROPOSAL_ERROR", {
                    "error": str(e),
                    "task_id": task.task_id
                })
