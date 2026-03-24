import time
import logging
import subprocess
import sys

from workflows.strategy.auto_fix_policy import is_auto_fix_eligible, classify_fix_scope
from workflows.strategy.auto_fix_context import build_auto_fix_context
from workflows.strategy.auto_fix_patch import generate_patch_proposal
from workflows.strategy.auto_fix_git import (
    create_fix_branch_name,
    validate_patch_applicability,
    apply_patch_in_sandbox,
    commit_sandbox_fix
)
from workflows.strategy.auto_fix_pr import build_fix_pr_payload
from workflows.strategy.incident_store import load_store, save_store

def validate_patch_result(repo_path: str, target_files: list) -> dict:
    # A minimal syntax/static check layer
    # For *.py files, we can run python -m py_compile
    bad_files = []
    for f in target_files:
        if f.endswith(".py"):
            try:
                subprocess.run([sys.executable, "-m", "py_compile", f], cwd=repo_path, check=True, capture_output=True)
            except subprocess.CalledProcessError as e:
                bad_files.append((f, e.stderr.decode("utf-8", errors="ignore")))
    
    if bad_files:
        logging.warning("[AUTO_FIX_VALIDATION_RESULT]", extra={"status": "FAIL"})
        details = "\\n".join(f"{f}: {err[:100]}" for f, err in bad_files)
        return {"status": "FAIL", "summary": "Syntax validation failed", "details": details}
        
    logging.info("[AUTO_FIX_VALIDATION_RESULT]", extra={"status": "PASS"})
    return {"status": "PASS", "summary": "Minimal syntax check passed", "details": ""}


def mark_attempt(incident_hash: str):
    data = load_store()
    if incident_hash in data.get("incidents", {}):
        data["incidents"][incident_hash]["auto_fix_last_attempt_ts"] = time.time()
        save_store(data)

def mark_c11_state(incident_hash: str, status: str, reason: str, branch: str = None):
    data = load_store()
    if incident_hash in data.get("incidents", {}):
        data["incidents"][incident_hash]["auto_fix_status"] = status
        data["incidents"][incident_hash]["auto_fix_reason"] = reason
        if branch:
            data["incidents"][incident_hash]["auto_fix_branch"] = branch
        save_store(data)


def run_auto_fix_for_incident(incident: dict, repo_adapter, llm_client, repo_path: str) -> dict:
    incident_hash = incident.get("incident_hash")
    
    eligible, reason = is_auto_fix_eligible(incident)
    if not eligible:
        if reason == "cooldown_active":
            logging.info("[AUTO_FIX_COOLDOWN_BLOCKED]", extra={"hash": incident_hash})
        logging.info("[AUTO_FIX_ABORTED]", extra={"hash": incident_hash, "reason": reason})
        mark_c11_state(incident_hash, "BLOCKED", reason)
        return {"status": "BLOCKED", "reason": reason}

    logging.info("[AUTO_FIX_TRIGGER_POINT_CONFIRMED]", extra={"hash": incident_hash})
    
    # IMPORTANT: Start evaluating policy => apply cooldown logic constraint
    mark_attempt(incident_hash)

    # Context Builder
    logging.info("[AUTO_FIX_CONTEXT_BUILT]")
    context = build_auto_fix_context(incident, repo_adapter)
    if context.get("status") == "BLOCKED":
        logging.warning("[AUTO_FIX_SCOPE_BLOCKED]", extra={"reason": context.get("reason", "unknown")})
        mark_c11_state(incident_hash, "BLOCKED", context.get("reason", "unknown"))
        return {"status": "BLOCKED", "reason": context.get("reason", "unknown")}

    scope = classify_fix_scope(context)
    if scope == "wide":
        logging.warning("[AUTO_FIX_SCOPE_BLOCKED]", extra={"reason": "scope_too_wide"})
        mark_c11_state(incident_hash, "BLOCKED", "scope_too_wide")
        return {"status": "BLOCKED", "reason": "scope_too_wide"}

    # Patch Proposal
    logging.info("[AUTO_FIX_PATCH_READY]")
    patch_result = generate_patch_proposal(context, llm_client)
    if patch_result.get("status") != "PATCH_READY":
        logging.warning("[AUTO_FIX_PATCH_FAILED]", extra={"reason": patch_result.get("reason")})
        mark_c11_state(incident_hash, "FAILED", patch_result.get("reason", "patch_gen_failed"))
        return {"status": patch_result.get("status", "FAILED"), "reason": patch_result.get("reason", "patch_gen_failed")}

    patch_text = patch_result.get("diff", "")
    
    # Dry Run Validation!
    dryrun_result = validate_patch_applicability(repo_path, patch_text)
    if dryrun_result.get("status") != "PASS":
        # Missing applicability marks failed safely, block no retries.
        mark_c11_state(incident_hash, "BLOCKED", "patch_invalid")
        return {"status": "BLOCKED", "reason": "patch_invalid"}
        
    # Sandbox branch
    branch_name = create_fix_branch_name(incident)
    patch_result["branch_name"] = branch_name
    
    apply_result = apply_patch_in_sandbox(repo_path, patch_text)
    if apply_result.get("status") != "PASS":
        logging.error("[AUTO_FIX_PATCH_FAILED]")
        mark_c11_state(incident_hash, "FAILED", apply_result.get("reason"))
        return {"status": "FAILED", "reason": apply_result.get("reason")}
        
    commit_result = commit_sandbox_fix(repo_path, branch_name, patch_result.get("summary", "Fix applied"))
    if commit_result.get("status") != "PASS":
        mark_c11_state(incident_hash, "FAILED", commit_result.get("reason"))
        return {"status": "FAILED", "reason": commit_result.get("reason")}

    # Validate
    val_result = validate_patch_result(repo_path, patch_result.get("target_files", []))
    
    # PR
    pr_payload = build_fix_pr_payload(incident, patch_result, val_result)
    
    final_status = "PR_READY" if val_result.get("status") == "PASS" else "DRAFT_PR_READY"
    logging.info(f"[AUTO_FIX_{final_status}]")
    
    mark_c11_state(incident_hash, final_status, "success", branch_name)
    
    return {
        "status": final_status,
        "incident_hash": incident_hash,
        "reason": "success",
        "branch_name": branch_name,
        "validation_status": val_result.get("status"),
        "pr_payload": pr_payload
    }
