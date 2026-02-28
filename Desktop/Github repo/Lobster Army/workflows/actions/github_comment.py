from __future__ import annotations
import os
from typing import Dict, Any
import logging

from tools.cost_tracker import DB
from tools.github_client import GitHubClient
from workflows.agents.llm_review_gate import comment_already_posted

log = logging.getLogger(__name__)

def is_comment_enabled() -> bool:
    return os.getenv("GITHUB_COMMENT_ENABLED", "0").strip() == "1"

def build_comment_body(meta_json: Dict[str, Any], review: Dict[str, Any]) -> str:
    repo = meta_json.get("repo")
    pr = meta_json.get("pr_number")
    score = review.get("score")
    threshold = review.get("threshold")
    merge_key = review.get("merge_key")
    policy = review.get("policy_snapshot") or {}

    # 短、可審計、避免敏感資訊
    return (
        f"🦞 Lobster Review (skeleton)\n"
        f"- repo: {repo}\n"
        f"- pr: {pr}\n"
        f"- decision: {review.get('decision')}\n"
        f"- score: {score} (threshold {threshold})\n"
        f"- merge_key: {merge_key}\n"
        f"- policy: v={policy.get('policy_version')} model={policy.get('llm_model')}\n"
        f"- note: no auto-merge; proposal only.\n"
    )

def try_post_pr_comment(task_id: str, meta_json: Dict[str, Any], review: Dict[str, Any]) -> None:
    """
    Idempotent external action:
    - Only run when enabled
    - Only once per merge_key
    - Emits success/failure events
    - Must not raise to caller (no bubble)
    """
    if not is_comment_enabled():
        log.info("[GITHUB_COMMENT_SKIP] disabled")
        return

    merge_key = review.get("merge_key")
    if not merge_key:
        log.info("[GITHUB_COMMENT_SKIP] missing merge_key")
        return

    if comment_already_posted(task_id, merge_key):
        log.info("[GITHUB_COMMENT_SKIP] already posted merge_key=%s", merge_key)
        return

    repo = meta_json.get("repo")
    pr = meta_json.get("pr_number")
    if not repo or not pr:
        DB.emit_event(task_id, "GITHUB_COMMENT_FAILED", {"merge_key": merge_key, "reason": "missing_repo_or_pr"})
        return

    try:
        body = build_comment_body(meta_json, review)
        client = GitHubClient()
        resp = client.post_pr_comment(repo, int(pr), body)

        DB.emit_event(
            task_id,
            "GITHUB_COMMENT_POSTED",
            {
                "merge_key": merge_key,
                "comment_id": resp.get("id"),
                "url": resp.get("html_url"),
            },
        )
        log.info("[GITHUB_COMMENT_POSTED] merge_key=%s", merge_key)

    except Exception as e:
        DB.emit_event(task_id, "GITHUB_COMMENT_FAILED", {"merge_key": merge_key, "reason": str(e)})
        log.exception("[GITHUB_COMMENT_FAILED] merge_key=%s", merge_key)
        # no raise
