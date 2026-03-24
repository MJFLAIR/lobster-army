import logging
from workflows.strategy.incident_store import load_store

def get_top_incidents(limit: int = 10) -> list[dict]:
    try:
        data = load_store()
        incidents = data.get("incidents", {})
        
        open_incidents = {h: inc for h, inc in incidents.items() if str(inc.get("status", "open")).lower() == "open"}
        
        sorted_incidents = sorted(
            open_incidents.items(),
            key=lambda x: (
                x[1].get("priority_score", 0),
                x[1].get("count", x[1].get("occurrence_count", 1)),
                x[1].get("last_seen", "")
            ),
            reverse=True
        )
        
        result = []
        for h, inc in sorted_incidents[:limit]:
            result.append({
                "incident_hash": h,
                "priority_level": str(inc.get("priority_level", "P4")),
                "priority_score": int(inc.get("priority_score", 0)),
                "severity": str(inc.get("severity", "low")),
                "count": int(inc.get("count", inc.get("occurrence_count", 1))),
                "failure_type": str(inc.get("failure_type") or "unknown").strip() or "unknown",
                "pipeline": str(inc.get("pipeline") or "unknown").strip() or "unknown",
                "last_seen": str(inc.get("last_seen", "")),
                "github_issue_number": inc.get("github_issue_number", inc.get("existing_issue_number")),
                "delta_24h": int(inc.get("delta_24h", 0)),
                "trend": str(inc.get("trend", "unknown")),
                "confidence": str(inc.get("confidence", "LOW")),
                "auto_fix_status": inc.get("auto_fix_status"),
                "auto_fix_reason": inc.get("auto_fix_reason"),
                "auto_fix_branch": inc.get("auto_fix_branch")
            })
            
        return result
    except Exception as e:
        logging.warning("[INCIDENT_REPORT_WARNING] get_top_incidents failed", extra={"error": str(e)})
        return []

def summarize_incident_report(limit: int = 10) -> dict:
    try:
        data = load_store()
        incidents = data.get("incidents", {})
        
        open_incidents = [inc for inc in incidents.values() if str(inc.get("status", "open")).lower() == "open"]
        total_open = len(open_incidents)
        
        summary = {
            "total_open_incidents": total_open,
            "p1": 0,
            "p2": 0,
            "p3": 0,
            "p4": 0
        }
        
        for inc in open_incidents:
            level = str(inc.get("priority_level", "P4")).lower()
            if level in summary:
                summary[level] += 1
                
        summary["top_incidents"] = get_top_incidents(limit)
        logging.info("[INCIDENT_REPORT_GENERATED]", extra={"total_open": total_open, "top_limit": limit})
        return summary
    except Exception as e:
        logging.warning("[INCIDENT_REPORT_WARNING] summarize_incident_report failed", extra={"error": str(e)})
        return {
            "total_open_incidents": 0,
            "p1": 0, "p2": 0, "p3": 0, "p4": 0,
            "top_incidents": []
        }
