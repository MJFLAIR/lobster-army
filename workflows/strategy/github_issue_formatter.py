import json

def format_sitrep_issue(sitrep: dict, incident_info: dict = None) -> dict:
    failure_type = sitrep.get("failure_type", "unknown")
    pipeline = sitrep.get("pipeline", "unknown")
    
    if incident_info:
        count = incident_info.get("occurrence_count", 1)
        incident_hash = incident_info.get("incident_hash", "unknown")
        severity = incident_info.get("severity", "LOW").upper()
        p_level = incident_info.get("priority_level", "P4")
        p_score = incident_info.get("priority_score", 0)
        p_reason = incident_info.get("priority_reason", "unclassified")
        
        title = f"[SITREP][{p_level}][{severity}][x{count}] {failure_type} in {pipeline}"
        incident_section = f"""## Incident Intelligence
- **Incident Hash:** {incident_hash}
- **Occurrence Count:** {count}
- **Severity:** {severity}

## Priority
- **Level:** {p_level}
- **Score:** {p_score}
- **Reason:** {p_reason}
"""
    else:
        title = f"[SITREP] {failure_type} in {pipeline}"
        incident_section = ""
    
    sitrep_json = json.dumps(sitrep, indent=2)
    
    body = f"""## Summary
- **Summary:** {sitrep.get("summary", "")}
- **Risk Level:** {sitrep.get("risk_level", "unknown")}
- **Recommended Action:** {sitrep.get("recommended_action", "manual intervention required")}

{incident_section}
## Failure Context
- **Task ID:** {sitrep.get("task_id", "unknown")}
- **Failure Type:** {failure_type}
- **Error:** {sitrep.get("error", "unknown")}
- **Pipeline:** {pipeline}
- **Agent:** {sitrep.get("agent", "unknown")}
- **Execution Mode:** {sitrep.get("execution_mode", "unknown")}

## Suggested Operator Response
- Inspect runtime logs
- Reproduce locally if needed
- Review architectural dependencies before applying fixes

## Raw SITREP JSON
```json
{sitrep_json}
```
"""
    
    return {
        "title": title,
        "body": body
    }
