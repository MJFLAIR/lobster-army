from __future__ import annotations

import logging
import os
import hashlib
import json
from typing import Any, Dict

# 移除了舊的 safe_parse_llm_review，只保留 clamp01
from workflows.models.llm_review import clamp01

# 引入 5.2 的神級 JSON Guard
from tools.llm_json_guard import LLMJSONGuard, require_pr_gate_schema
from tools.llm_client import LLMClient  # 使用既有 client
from tools.cost_tracker import DB

log = logging.getLogger(__name__)

DEFAULT_THRESHOLD = 0.75


def get_threshold() -> float:
    raw = os.getenv("GATE_SCORE_THRESHOLD", str(DEFAULT_THRESHOLD))
    try:
        return clamp01(float(raw))
    except Exception:
        return DEFAULT_THRESHOLD

POLICY_VERSION = "phase_b5"

def get_llm_snapshot() -> Dict[str, Any]:
    # 不依賴 LLMClient 內部實作，只從 ENV 取，保持 deterministic
    return {
        "policy_version": POLICY_VERSION,
        "llm_provider": os.getenv("LLM_REVIEW_PROVIDER", "unknown"),
        "llm_model": os.getenv("LLM_REVIEW_MODEL", "unknown"),
    }

def get_threshold_snapshot() -> Dict[str, Any]:
    raw = os.getenv("GATE_SCORE_THRESHOLD")
    return {
        "threshold": get_threshold(),   # 既有 clamp 後值
        "threshold_raw": raw,
    }

def build_policy_snapshot() -> Dict[str, Any]:
    snap = {}
    snap.update(get_llm_snapshot())
    snap.update(get_threshold_snapshot())
    return snap

def build_merge_key(
    task_id: str,
    decision: str,
    score: float,
    threshold: float,
    policy_snapshot: dict,
) -> str:
    """
    Deterministic merge proposal key.
    Must not rely on non-deterministic fields (e.g., timestamp).
    """
    payload = {
        "task_id": task_id,
        "decision": decision,
        "score": round(score, 6),
        "threshold": round(threshold, 6),
        "policy_version": policy_snapshot.get("policy_version"),
        "llm_model": policy_snapshot.get("llm_model"),
    }

    raw = json.dumps(payload, sort_keys=True)
    return hashlib.sha256(raw.encode()).hexdigest()

def merge_key_exists(task_id: str, merge_key: str) -> bool:
    """
    Check if MERGE_CANDIDATE with same merge_key already exists.
    """
    from tools.cost_tracker import DB

    db = DB.get_client()
    events_ref = db.collection("tasks").document(str(task_id)).collection("events")

    query = (
        events_ref
        .where("event_type", "==", "MERGE_CANDIDATE")
        .where("payload_json.merge_key", "==", merge_key)
        .limit(1)
    )

    docs = list(query.stream())
    return len(docs) > 0

def comment_already_posted(task_id: str, merge_key: str) -> bool:
    from tools.cost_tracker import DB
    db = DB.get_client()
    events_ref = db.collection("tasks").document(str(task_id)).collection("events")
    q = (
        events_ref
        .where("event_type", "==", "GITHUB_COMMENT_POSTED")
        .where("payload_json.merge_key", "==", merge_key)
        .limit(1)
    )
    return len(list(q.stream())) > 0

def label_already_applied(task_id: str, merge_key: str) -> bool:
    from tools.cost_tracker import DB
    db = DB.get_client()
    events_ref = db.collection("tasks").document(str(task_id)).collection("events")
    q = (
        events_ref
        .where("event_type", "==", "GITHUB_LABEL_APPLIED")
        .where("payload_json.merge_key", "==", merge_key)
        .limit(1)
    )
    return len(list(q.stream())) > 0

def merge_already_executed(task_id: str, merge_key: str) -> bool:
    from tools.cost_tracker import DB
    db = DB.get_client()
    events_ref = db.collection("tasks").document(str(task_id)).collection("events")
    q = (
        events_ref
        .where("event_type", "in", ["GITHUB_MERGE_EXECUTED", "GITHUB_MERGE_SKIPPED", "GITHUB_MERGE_FAILED"])
        .where("payload_json.merge_key", "==", merge_key)
        .limit(1)
    )
    return len(list(q.stream())) > 0


def run_llm_review(task_id: str, meta_json: Dict[str, Any]) -> Dict[str, Any]:
    """
    Skeleton version.
    Never raises.
    Never modifies state.
    Returns dict:
        {
            "decision": "...",
            "score": ...,
            "reason": "...",
            "error": optional str
        }
    """

    log.info("[PR_LLM_REVIEW] starting")
    DB.emit_event(
        task_id,
        "PR_LLM_REVIEW",
        {
            "stage": "start",
            "policy_snapshot": build_policy_snapshot(),
        },
    )

    try:
        from llm.role_config import get_role_config
        from llm.factory import create_llm
        
        cfg = get_role_config("pr_gate")
        client = create_llm(cfg["provider"], cfg["model"])
        logging.info(f"[PR_GATE_LLM_PROVIDER] {cfg['provider']}")

        # 強化版 Prompt：嚴格規定 JSON 格式，並附上 meta_json 讓它有東西可以看
        prompt = (
            "Review this PR. You MUST return ONLY a JSON object containing exactly three keys:\n"
            "- 'decision': strictly 'approve' or 'reject'\n"
            "- 'score': a float number between 0.0 and 1.0\n"
            "- 'reason': a string explaining why\n\n"
            f"PR Metadata: {json.dumps(meta_json)}"
        )

        response = client.complete(prompt)

        # ==========================================
        # 🛡️ 啟動 5.2 的 LLM JSON Guard 安檢門 🛡️
        # ==========================================
        guard = LLMJSONGuard(allow_root_object=True, allow_root_array=False)
        raw = response["content"] if isinstance(response, dict) else str(response)
        parsed = guard.parse_object(raw, validator=require_pr_gate_schema)

        if not parsed.ok:
            log.warning("[PR_LLM_SCHEMA_ERROR] %s", parsed.error)
            DB.emit_event(
                task_id,
                "PR_LLM_REJECT",
                {
                    "reason": f"schema_invalid: {parsed.error}",
                    "score": 0.0,
                    "policy_snapshot": build_policy_snapshot(),
                },
            )
            return {
                "decision": "reject",
                "score": 0.0,
                "reason": f"schema invalid: {parsed.error}",
            }

        # 取得純淨、合法、帶有完整欄位的 Python 字典
        data = parsed.data
        # ==========================================

        threshold = get_threshold()
        
        # 從 parsed data 中提取變數，取代原本的 result.decision
        decision = data["decision"]
        score = data["score"]
        reason = data["reason"]

        if decision == "approve" and score >= threshold:
            log.info("[PR_LLM_APPROVE]")
            
            policy_snapshot = build_policy_snapshot()

            DB.emit_event(
                task_id,
                "PR_LLM_APPROVE",
                {
                    "score": score,
                    "threshold": threshold,
                    "policy_snapshot": policy_snapshot,
                },
            )

            merge_key = build_merge_key(
                task_id=task_id,
                decision=decision,
                score=score,
                threshold=threshold,
                policy_snapshot=policy_snapshot,
            )

            if not merge_key_exists(task_id, merge_key):
                DB.emit_event(
                    task_id,
                    "MERGE_CANDIDATE",
                    {
                        "score": score,
                        "threshold": threshold,
                        "proposal": "deterministic_llm_pass",
                        "policy_snapshot": policy_snapshot,
                        "merge_key": merge_key,
                    },
                )
            else:
                log.info("[MERGE_CANDIDATE_SKIPPED] duplicate merge_key=%s", merge_key)
        else:
            log.info("[PR_LLM_REJECT]")
            DB.emit_event(
                task_id,
                "PR_LLM_REJECT",
                {
                    "score": score,
                    "threshold": threshold,
                    "reason": reason,
                    "policy_snapshot": build_policy_snapshot(),
                },
            )

        return {
            "decision": decision,
            "score": score,
            "reason": reason,
        }

    except Exception as e:
        log.exception("[PR_LLM_REJECT] exception")
        DB.emit_event(
            task_id,
            "PR_LLM_EXCEPTION",
            {
                "reason": str(e),
                "policy_snapshot": build_policy_snapshot(),
            },
        )
        return {
            "decision": "reject",
            "score": 0.0,
            "reason": "llm_exception",
            "error": str(e),
        }