def calculate_priority(sitrep: dict, incident: dict) -> dict:
    score = 0
    reasons = []

    severity = incident.get("severity", "low")
    count = incident.get("count", 1)
    pipeline = incident.get("pipeline", "")
    failure_type = incident.get("failure_type", "")
    interval = incident.get("last_seen_interval_sec", 0)

    # Severity
    if severity == "high":
        score += 50
        reasons.append("high severity")
    elif severity == "medium":
        score += 30
    else:
        score += 10

    # Occurrence
    if count >= 20:
        score += 25
        reasons.append("frequent failures")
    elif count >= 10:
        score += 15
    elif count >= 5:
        score += 10
    elif count >= 2:
        score += 5

    # Pipeline
    if "prod" in pipeline or "production" in pipeline:
        score += 20
        reasons.append("production impact")
    elif "code_pipeline_with_tests" in pipeline:
        score += 10

    # Failure type
    if failure_type in ["database", "schema", "migration"]:
        score += 20
        reasons.append("data risk")
    elif failure_type in ["auth", "permission"]:
        score += 15
    elif failure_type in ["network", "rate_limit"]:
        score += 8

    # Frequency boost (NEW from C10.6.4)
    if interval > 0 and interval < 300:
        score += 15
        reasons.append("high frequency")

    # Priority mapping
    if score >= 80:
        level = "P1"
    elif score >= 60:
        level = "P2"
    elif score >= 35:
        level = "P3"
    else:
        level = "P4"

    reason = " + ".join(reasons[:3]) if reasons else "baseline"

    return {
        "priority_score": score,
        "priority_level": level,
        "priority_reason": reason
    }
