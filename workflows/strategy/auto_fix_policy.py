import time

def is_auto_fix_eligible(incident: dict) -> tuple[bool, str]:
    if not incident:
        return False, "missing_incident_data"

    incident_hash = incident.get("incident_hash")
    if not incident_hash:
        return False, "missing_incident_hash"

    priority_level = incident.get("priority_level", "P4")
    if priority_level != "P1":
        return False, "not_p1"

    trend = incident.get("trend")
    if trend != "spiking":
        return False, "trend_not_spiking"

    confidence = incident.get("confidence")
    if str(confidence).upper() != "HIGH":
        return False, "confidence_not_high"

    if not incident.get("error"):
        return False, "missing_error_context"

    last_ts = incident.get("auto_fix_last_attempt_ts")
    if last_ts:
        try:
            now = time.time()
            if now - float(last_ts) < 3600:
                return False, "cooldown_active"
        except Exception:
            pass

    return True, "eligible"


def classify_fix_scope(candidate: dict) -> str:
    """
    Returns 'narrow', 'wide', or 'unknown'
    candidate should be the result from build_auto_fix_context
    """
    if not candidate:
        return "unknown"

    target_files = candidate.get("allowed_files", [])
    
    if len(target_files) > 2:
        return "wide"

    if not target_files:
        return "wide"

    failure_type = candidate.get("failure_type", "").lower()
    if failure_type in ["database", "schema", "migration", "infra", "secret"]:
        return "wide"
        
    error_summary = candidate.get("error_summary", "").lower()
    if any(kw in error_summary for kw in ["npm install", "pip install", "dependency", "package-lock.json", "requirements.txt"]):
        return "wide"

    return "narrow"
