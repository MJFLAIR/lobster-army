import os
import json
import logging
import urllib.parse
from typing import Dict, Any, Optional, Tuple
from datetime import datetime, timezone

from tools.network_client import NetworkClient, NetworkPolicyError
from workflows.storage.db import DB
from workflows.models.task import Task
from google.api_core.exceptions import AlreadyExists
from google.cloud import firestore

GATE_VERSION = "0.4.0"
DEFAULT_GATE_THRESHOLD = 0.8
DEFAULT_STATUS_ALLOWLIST = {"pass", "passed", "approve", "approved", "ok"}

class GitHubPRGate:
    def __init__(self):
        self.gate_enabled = os.environ.get("GITHUB_GATE_ENABLED", "0") in ("1", "true", "True")
        self.note_enabled = os.environ.get("GITHUB_GATE_NOTE_ENABLED", "0") in ("1", "true", "True")
        self.token = os.environ.get("GITHUB_TOKEN", "").strip()
        self.default_repo = os.environ.get("GITHUB_REPO", "").strip()
        self.api_base = os.environ.get("GITHUB_API_BASE", "https://api.github.com").rstrip("/")
        self.network_client = NetworkClient()

        self.gate_threshold = DEFAULT_GATE_THRESHOLD
        threshold_env = os.environ.get("GATE_SCORE_THRESHOLD")
        if threshold_env is not None:
            try:
                parsed = float(threshold_env)
                clamped = max(0.0, min(parsed, 1.0))
                if clamped != parsed:
                    logging.warning(f"GATE_SCORE_THRESHOLD {parsed} out of range, clamped to {clamped}")
                self.gate_threshold = clamped
            except ValueError:
                logging.warning(f"Invalid GATE_SCORE_THRESHOLD '{threshold_env}', falling back to default {DEFAULT_GATE_THRESHOLD}.")

        self.status_allowlist = DEFAULT_STATUS_ALLOWLIST
        allowlist_env = os.environ.get("GATE_STATUS_ALLOWLIST")
        if allowlist_env is not None:
            parts = [p.strip().lower() for p in allowlist_env.split(",") if p.strip()]
            if parts:
                self.status_allowlist = set(parts)
            else:
                logging.warning(f"Empty GATE_STATUS_ALLOWLIST parsed from '{allowlist_env}', falling back to default.")

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

    def decide_gate(self, review_result: dict) -> Tuple[str, str, str]:
        status = review_result.get("status")
        if status is not None and isinstance(status, str):
            if status.lower() in self.status_allowlist:
                return "lobster:gate-pass", f"status={status}", "status"
            else:
                return "lobster:gate-block", f"status={status}", "status"
        
        score = review_result.get("score")
        if score is not None and isinstance(score, (int, float)):
            if score >= self.gate_threshold:
                return "lobster:gate-pass", f"score={score}", "score"
            else:
                return "lobster:gate-block", f"score={score}", "score"
                
        return "lobster:gate-block", "no_status_or_score", "none"

    def build_policy_snapshot(self, task: Task, review_result: dict, gate_label: str, decision_basis: str, repo: str, pr_number: int, head_sha: str) -> dict:
        decision = "PASS" if gate_label == "lobster:gate-pass" else "BLOCK"
        
        issue_count = None
        issues = review_result.get("issues")
        if isinstance(issues, list):
            issue_count = len(issues)
        else:
            findings = review_result.get("findings")
            if isinstance(findings, list):
                issue_count = len(findings)

        input_summary = {
            "repo": repo,
            "pr_number": pr_number,
            "head_sha": head_sha,
            "review_status": review_result.get("status"),
            "score": review_result.get("score"),
            "issue_count": issue_count,
            "task_id": task.task_id
        }

        return {
            "policy_version": GATE_VERSION,
            "decision": decision,
            "decision_basis": decision_basis,
            "threshold": self.gate_threshold,
            "status_allowlist": sorted(list(self.status_allowlist)),
            "input_summary": input_summary
        }

    def delete_label(self, repo_full_name: str, pr_number: int, label_name: str) -> None:
        if not self.gate_enabled or not self.token:
            return
            
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
            logging.error(f"NetworkPolicyError deleting label {label_name}: {e}")
        except Exception as e:
            # Can be 404 (not found), safe to ignore
            logging.debug(f"Exception deleting label {label_name} (likely not present): {e}")

    def post_gate_label(self, repo_full_name: str, pr_number: int, gate_label: str) -> Dict[str, Any]:
        url = f"{self.api_base}/repos/{repo_full_name}/issues/{pr_number}/labels"
        headers = {
            "Authorization": f"Bearer {self.token}",
            "Accept": "application/vnd.github+json",
            "Content-Type": "application/json",
            "X-GitHub-Api-Version": "2022-11-28"
        }
        
        payload_bytes = json.dumps({"labels": [gate_label]}).encode("utf-8")
        
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

    def maybe_post_gate_note(self, task: Task, repo_full_name: str, pr_number: int, head_sha: str, gate_label: str, reason: str) -> Dict[str, Any]:
        if not self.note_enabled:
            return {"ok": False, "skipped": True, "reason": "note_disabled"}
            
        short_sha = head_sha[:7] if head_sha else "unknown"
        utc_iso = datetime.now(timezone.utc).isoformat()
        
        decision = "PASS" if "gate-pass" in gate_label else "BLOCK"
        
        body = (
            f"Gate Decision: {decision}\n"
            f"label: {gate_label}\n"
            f"reason: {reason}\n"
            f"task_id: {task.task_id}\n"
            f"commit: {short_sha}\n"
            f"generated_at: {utc_iso}\n"
            f"Lobster Army Gate v{GATE_VERSION}"
        )
        
        url = f"{self.api_base}/repos/{repo_full_name}/issues/{pr_number}/comments"
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

    def run_hook(self, task: Task, review_result: dict) -> None:
        if task.source != "github_pr":
            return
            
        repo_full_name = self.resolve_repo(task)
        pr_number = self.resolve_pr_number(task)
        head_sha = self.resolve_head_sha(task)
        
        if not self.gate_enabled or not self.token:
            reason = "disabled" if not self.gate_enabled else "missing_token"
            DB.emit_event(task.task_id, "GITHUB_PR_GATE_SKIPPED", {
                "reason": reason,
                "task_id": task.task_id
            })
            return

        if not pr_number or not head_sha or not repo_full_name:
            DB.emit_event(task.task_id, "GITHUB_PR_GATE_SKIPPED", {
                "reason": "missing_pr_metadata",
                "task_id": task.task_id
            })
            return

        gate_label, reason, decision_basis = self.decide_gate(review_result)
        
        try:
            snapshot = self.build_policy_snapshot(
                task, review_result, gate_label, decision_basis,
                repo_full_name, pr_number, head_sha
            )
            DB.emit_event(task.task_id, "PR_GATE_POLICY_SNAPSHOT", snapshot)
        except Exception as e:
            logging.error(f"Failed to emit PR_GATE_POLICY_SNAPSHOT for task {task.task_id}: {e}")
        
        # 1. Gate Label Dedup & Post
        dedup_label_key = f"{repo_full_name}:{pr_number}:{head_sha}:{gate_label}".replace("/", "_")
        dedup_label_ref = DB.get_client().collection("pr_gate_dedup").document(dedup_label_key)
        
        try:
            dedup_label_ref.create({
                "task_id": task.task_id,
                "repo": repo_full_name,
                "pr_number": pr_number,
                "head_sha": head_sha,
                "gate_label": gate_label,
                "reason": reason,
                "version": GATE_VERSION,
                "created_at": firestore.SERVER_TIMESTAMP
            })
            
            # Mutual exclusion removal
            opposite_label = "lobster:gate-block" if gate_label == "lobster:gate-pass" else "lobster:gate-pass"
            self.delete_label(repo_full_name, pr_number, opposite_label)
            
            res_label = self.post_gate_label(repo_full_name, pr_number, gate_label)
            if res_label.get("ok"):
                DB.emit_event(task.task_id, "GITHUB_PR_GATE_POSTED", {
                    "gate_label": gate_label,
                    "reason": reason,
                    "pr_number": pr_number,
                    "repo": repo_full_name,
                    "head_sha": head_sha,
                    "task_id": task.task_id
                })
            else:
                DB.emit_event(task.task_id, "GITHUB_PR_GATE_ERROR", {
                    "reason": res_label.get("reason"),
                    "error": res_label.get("error"),
                    "task_id": task.task_id
                })
        except AlreadyExists:
            DB.emit_event(task.task_id, "GITHUB_PR_GATE_SKIPPED", {
                "reason": "duplicate_label",
                "gate_label": gate_label,
                "task_id": task.task_id
            })

        # 2. Optional Gate Note Dedup & Post
        if self.note_enabled:
            dedup_note_key = f"{repo_full_name}:{pr_number}:{head_sha}:{gate_label}:{GATE_VERSION}".replace("/", "_")
            dedup_note_ref = DB.get_client().collection("pr_gate_note_dedup").document(dedup_note_key)
            try:
                dedup_note_ref.create({
                    "task_id": task.task_id,
                    "version": GATE_VERSION,
                    "gate_label": gate_label,
                    "created_at": firestore.SERVER_TIMESTAMP
                })
                self.maybe_post_gate_note(task, repo_full_name, pr_number, head_sha, gate_label, reason)
            except AlreadyExists:
                pass
