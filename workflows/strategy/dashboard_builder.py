import json
import logging
from datetime import datetime, timezone
from workflows.strategy.incident_report import summarize_incident_report

def build_dashboard_snapshot(limit: int = 10) -> dict:
    try:
        summary = summarize_incident_report(limit)
        
        try:
            from workflows.strategy.incident_trend import compute_system_status
            system_status = compute_system_status(summary)
            logging.info("[SYSTEM_STATUS_COMPUTED]", extra={"status": system_status})
        except Exception as e:
            logging.warning("[SYSTEM_STATUS_FAIL]", extra={"error": str(e)})
            system_status = "HEALTHY"
            
        top_incidents = summary.get("top_incidents", [])
        high_confidence_count = sum(1 for inc in top_incidents if str(inc.get("confidence", "")).upper() == "HIGH")
        auto_fix_pr_count = sum(1 for inc in top_incidents if inc.get("auto_fix_status") in ["PR_READY", "DRAFT_PR_READY"])
        
        snapshot = {
            "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "system_status": system_status,
            "total_open_incidents": summary.get("total_open_incidents", 0),
            "high_confidence_count": high_confidence_count,
            "auto_fix_pr_count": auto_fix_pr_count,
            "p1": summary.get("p1", 0),
            "p2": summary.get("p2", 0),
            "p3": summary.get("p3", 0),
            "p4": summary.get("p4", 0),
            "top_incidents": summary.get("top_incidents", [])
        }
        
        logging.info("[DASHBOARD_SNAPSHOT_BUILT]", extra={
            "total_open_incidents": snapshot["total_open_incidents"],
            "top_count": len(snapshot["top_incidents"])
        })
        
        try:
            with open(".dashboard_snapshot.json", "w") as f:
                json.dump(snapshot, f, indent=2)
        except Exception as e:
            logging.warning("[DASHBOARD_SNAPSHOT_WRITE_FAILED]", extra={"error": str(e)})
            
        return snapshot
    except Exception as e:
        logging.error("[DASHBOARD_SNAPSHOT_FAILED] Returning empty snapshot", extra={"error": str(e)})
        return {
            "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "system_status": "HEALTHY",
            "total_open_incidents": 0,
            "p1": 0, "p2": 0, "p3": 0, "p4": 0,
            "top_incidents": []
        }
