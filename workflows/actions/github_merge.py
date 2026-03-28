from __future__ import annotations
import os
from typing import Dict, Any
import logging

from tools.cost_tracker import DB
from tools.github_client import GitHubClient
from workflows.agents.llm_review_gate import merge_already_executed

log = logging.getLogger(__name__)

def is_merge_enabled() -> bool:
    return os.getenv("GITHUB_MERGE_ENABLED", "false").strip().lower() == "true"

def get_merge_method() -> str:
    m = os.getenv("GITHUB_MERGE_METHOD", "squash").strip().lower()
    return m if m in ("merge", "squash", "rebase") else "squash"

def try_merge_pr(task_id: str, meta_json: Dict[str, Any], review: Dict[str, Any]) -> None:
    """
    Idempotent external action:
    - gated by feature flag (default OFF)
    - once per merge_key (including SKIPPED/FAILED to avoid spam)
    - emits SKIPPED/EXECUTED/FAILED
    - must not raise to caller
    """
    merge_key = review.get("merge_key")
    if not merge_key:
        log.info("[GITHUB_MERGE_SKIP] missing merge_key")
        return

    if merge_already_executed(task_id, merge_key):
        log.info("[GITHUB_MERGE_SKIP] already handled merge_key=%s", merge_key)
        return

    repo = meta_json.get("repo")
    pr = meta_json.get("pr_number")
    if not repo or not pr:
        DB.emit_event(task_id, "GITHUB_MERGE_FAILED", {"merge_key": merge_key, "reason": "missing_repo_or_pr"})
        return

    if not is_merge_enabled():
        log.info("[GITHUB_MERGE_SKIPPED] merge disabled merge_key=%s", merge_key)
        DB.emit_event(task_id, "GITHUB_MERGE_SKIPPED", {"merge_key": merge_key, "reason": "disabled"})
        return

    method = get_merge_method()

    try:
        client = GitHubClient()
        resp = client.merge_pull_request(repo, int(pr), merge_method=method)

        DB.emit_event(
            task_id,
            "GITHUB_MERGE_EXECUTED",
            {
                "merge_key": merge_key,
                "merge_method": method,
                "sha": resp.get("sha"),
                "merged": resp.get("merged"),
                "message": resp.get("message"),
            },
        )
        log.info("[GITHUB_MERGE_EXECUTED] merge_key=%s method=%s", merge_key, method)

    except Exception as e:
        DB.emit_event(task_id, "GITHUB_MERGE_FAILED", {"merge_key": merge_key, "reason": str(e)})
        log.exception("[GITHUB_MERGE_FAILED] merge_key=%s", merge_key)
        # no raise
