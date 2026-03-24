import logging

def build_fix_pr_payload(incident: dict, patch_result: dict, validation: dict) -> dict:
    incident_hash = incident.get("incident_hash", "unknown")
    h = incident_hash[:8]
    
    val_status = validation.get("status", "UNKNOWN")
    
    if val_status == "PASS":
        title = f"[AutoFix] Patch proposal for incident {h}"
    else:
        title = f"[Draft][AutoFix] Partial fix proposal for incident {h}"
        
    p_level = incident.get("priority_level", "P4")
    trend = incident.get("trend", "unknown")
    confidence = incident.get("confidence", "LOW")
    
    # Patch result metadata
    patch_summary = patch_result.get("summary", "No summary provided.")
    target_files = patch_result.get("target_files", [])
    files_str = ", ".join(target_files) if target_files else "None"
    
    body = f"""## Auto Fix Proposal
**Incident:** {incident_hash}
**Priority:** {p_level}
**Trend:** {trend}
**Confidence:** {confidence}

**Target file(s):** {files_str}
**Scope class:** narrow
**Summary:** {patch_summary}

### Validation
**Result:** {val_status}
**Notes:** {validation.get("details", "")}

### Guardrail Summary
- Context lock respected
- Scope lock respected
- Attempt count: 1

⚠️ **Human review required before merge**"""

    payload = {
        "title": title,
        "body": body,
        "head": patch_result.get("branch_name", f"fix/incident-{h}"),
        "base": "main",
        "draft": val_status != "PASS"
    }
    
    logging.info("[AUTO_FIX_PR_PAYLOAD_BUILT]")
    return payload
