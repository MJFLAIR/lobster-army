import os
import json
from datetime import datetime, timezone
import logging

def record_failure_event(event: dict, log_path: str = "logs/failure_patterns.jsonl") -> None:
    """Appends a structured event to the tracking JSONL file synchronously and atomically."""
    # Ensure directory exists
    dir_name = os.path.dirname(os.path.abspath(log_path))
    if dir_name:
        os.makedirs(dir_name, exist_ok=True)
    
    # Enforce constraints
    if "timestamp" not in event:
        event["timestamp"] = datetime.now(timezone.utc).isoformat()
        
    if "template_used" not in event:
        event["template_used"] = "NONE"

    # Append safely ensuring it's durable
    try:
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(event) + "\n")
            f.flush()
    except Exception as e:
        # Failsafe logging if disk fails
        logging.error("[PATTERN_TRACKER_WRITE_FAIL]", extra={"error": str(e)})

def summarize_failure_stats(events: list[dict]) -> dict:
    """Deterministically aggregates statistics from tracking events."""
    summary = {
        "total_events": len(events),
        "total_retry_triggered": 0,
        "total_retry_success": 0,
        "retry_success_rate": 0.0,
        "failures_by_type": {},
        "template_usage_count": {},
        "final_status_count": {}
    }
    
    for e in events:
        if e.get("retry_triggered"):
            summary["total_retry_triggered"] += 1
            if e.get("retry_success"):
                summary["total_retry_success"] += 1
        
        f_type = e.get("initial_failure_type", "unknown")
        summary["failures_by_type"][f_type] = summary["failures_by_type"].get(f_type, 0) + 1
        
        t_used = e.get("template_used", "NONE")
        summary["template_usage_count"][t_used] = summary["template_usage_count"].get(t_used, 0) + 1
        
        f_status = e.get("final_status", "unknown")
        summary["final_status_count"][f_status] = summary["final_status_count"].get(f_status, 0) + 1
        
    if summary["total_retry_triggered"] > 0:
        summary["retry_success_rate"] = summary["total_retry_success"] / summary["total_retry_triggered"]
        
    return summary
