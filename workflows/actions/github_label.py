from __future__ import annotations
import os
from typing import Dict, Any, List
import logging

from tools.cost_tracker import DB
from tools.github_client import GitHubClient
from workflows.agents.llm_review_gate import label_already_applied

log = logging.getLogger(__name__)

def is_label_enabled() -> bool:
    return os.getenv("GITHUB_LABEL_ENABLED", "0").strip() == "1"

def get_labels() -> List[str]:
    # 可用逗號設定多個 label
    raw = os.getenv("GITHUB_LABELS", "lobster:merge-candidate")
    labels = [x.strip() for x in raw.split(",") if x.strip()]
    return labels or ["lobster:merge-candidate"]

def try_apply_pr_labels(task_id: str, meta_json: Dict[str, Any], review: Dict[str, Any]) -> None:
    """
    Idempotent external action:
    - gated by feature flag
    - once per merge_key
    - emits success/failure events
    - must not raise to caller
    """
    if not is_label_enabled():
        log.info("[GITHUB_LABEL_SKIP] disabled")
        return

    merge_key = review.get("merge_key")
    if not merge_key:
        log.info("[GITHUB_LABEL_SKIP] missing merge_key")
        return

    if label_already_applied(task_id, merge_key):
        log.info("[GITHUB_LABEL_SKIP] already applied merge_key=%s", merge_key)
        return

    repo = meta_json.get("repo")
    pr = meta_json.get("pr_number")
    if not repo or not pr:
        DB.emit_event(task_id, "GITHUB_LABEL_FAILED", {"merge_key": merge_key, "reason": "missing_repo_or_pr"})
        return

    labels = get_labels()

    try:
        client = GitHubClient()
        resp = client.add_issue_labels(repo, int(pr), labels)

        # resp 通常會回傳 label objects array；我們只存 label names
        DB.emit_event(
            task_id,
            "GITHUB_LABEL_APPLIED",
            {
                "merge_key": merge_key,
                "labels": labels,
            },
        )
        log.info("[GITHUB_LABEL_APPLIED] merge_key=%s labels=%s", merge_key, labels)

    except Exception as e:
        DB.emit_event(task_id, "GITHUB_LABEL_FAILED", {"merge_key": merge_key, "reason": str(e)})
        log.exception("[GITHUB_LABEL_FAILED] merge_key=%s", merge_key)
        # no raise
