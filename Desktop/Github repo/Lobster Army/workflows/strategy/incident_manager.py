import logging
from workflows.strategy.incident_hash import generate_incident_hash
from workflows.strategy.incident_store import load_store, save_store
from datetime import datetime, timezone

def classify_severity(sitrep: dict, occurrence_count: int) -> str:
    failure_type = sitrep.get("failure_type", "unknown")
    if failure_type in ["database", "schema", "migration"] or occurrence_count >= 10:
        return "high"
    if occurrence_count >= 3:
        return "medium"
    return "low"

def attach_github_issue(incident_hash: str, issue_number: int) -> None:
    try:
        data = load_store()
        incidents = data.get("incidents", {})
        if incident_hash in incidents:
            incidents[incident_hash]["github_issue_number"] = issue_number
            save_store(data)
            logging.info("[INCIDENT_LINKED_GITHUB]", extra={
                "hash": incident_hash,
                "issue_number": issue_number
            })
    except Exception as e:
        logging.warning("[INCIDENT_LINK_FAIL]", extra={"error": str(e)})

def update_last_synced(incident_hash: str, count: int) -> None:
    try:
        data = load_store()
        incidents = data.get("incidents", {})
        if incident_hash in incidents:
            incidents[incident_hash]["last_synced_count"] = count
            save_store(data)
    except Exception:
        pass

def process_incident(sitrep: dict) -> dict:
    incident_hash = generate_incident_hash(sitrep)
    
    try:
        data = load_store()
        incidents = data.setdefault("incidents", {})
        
        now = datetime.now(timezone.utc)
        now_str = now.isoformat()
        
        if incident_hash in incidents:
            inc = incidents[incident_hash]
            
            prev_last_seen = inc.get("last_seen")
            if prev_last_seen:
                try:
                    prev_dt = datetime.fromisoformat(prev_last_seen)
                    if prev_dt.tzinfo is None:
                        prev_dt = prev_dt.replace(tzinfo=timezone.utc)
                    interval = (now - prev_dt).total_seconds()
                except Exception:
                    interval = 0
            else:
                interval = 0
                
            inc["last_seen_interval_sec"] = interval
            inc["last_seen"] = now_str
            inc["count"] = inc.get("count", 0) + 1
            is_new = False
            logging.info("[INCIDENT_REUSED]", extra={"hash": incident_hash, "count": inc["count"]})
            logging.info("[INCIDENT_FREQUENCY]", extra={"hash": incident_hash, "interval_sec": interval})
        else:
            inc = {
                "count": 1,
                "first_seen": now_str,
                "last_seen": now_str,
                "last_seen_interval_sec": 0,
                "github_issue_number": None,
                "last_synced_count": 0,
                "status": "open",
                "count_24h_snapshot": 1,
                "snapshot_timestamp": now.timestamp()
            }
            incidents[incident_hash] = inc
            is_new = True
            logging.info("[INCIDENT_CREATED]", extra={"hash": incident_hash})
            
        inc["failure_type"] = str(inc.get("failure_type") or sitrep.get("failure_type") or "unknown").strip() or "unknown"
        inc["pipeline"] = str(inc.get("pipeline") or sitrep.get("pipeline") or "unknown").strip() or "unknown"
        
        logging.info("[INCIDENT_NORMALIZED]", extra={
            "hash": incident_hash,
            "failure_type": inc["failure_type"],
            "pipeline": inc["pipeline"]
        })
            
        current_time = now.timestamp()
        
        if "snapshot_timestamp" not in inc:
            inc["snapshot_timestamp"] = current_time
            inc["count_24h_snapshot"] = inc["count"]
            
        if (current_time - inc["snapshot_timestamp"]) >= 86400:
            inc["count_24h_snapshot"] = inc["count"]
            inc["snapshot_timestamp"] = current_time
            
        delta_24h = inc["count"] - inc.get("count_24h_snapshot", inc["count"])
        
        try:
            from workflows.strategy.incident_trend import classify_trend
            trend = classify_trend(delta_24h)
        except Exception:
            trend = "unknown"
            
        inc["delta_24h"] = delta_24h
        inc["trend"] = trend
        
        try:
            from workflows.strategy.incident_confidence import classify_confidence
            confidence = classify_confidence(inc["priority_level"], trend)
        except Exception:
            confidence = "LOW"
            
        inc["confidence"] = confidence
        
        logging.info("[INCIDENT_DELTA]", extra={"hash": incident_hash, "delta_24h": delta_24h})
        logging.info("[INCIDENT_TREND]", extra={"hash": incident_hash, "trend": trend})
        logging.info("[INCIDENT_CONFIDENCE]", extra={"hash": incident_hash, "confidence": confidence})
            
        severity = classify_severity(sitrep, inc["count"])
        inc["severity"] = severity
        logging.info("[INCIDENT_SEVERITY]", extra={
            "hash": incident_hash,
            "severity": severity,
            "count": inc["count"]
        })
        
        try:
            from workflows.strategy.incident_priority import calculate_priority
            priority = calculate_priority(sitrep, inc)
            inc["priority_score"] = priority.get("priority_score", 0)
            inc["priority_level"] = priority.get("priority_level", "P4")
            inc["priority_reason"] = priority.get("priority_reason", "unclassified")
            logging.info("[INCIDENT_PRIORITY_COMPUTED]", extra={
                "score": inc["priority_score"],
                "level": inc["priority_level"]
            })
        except Exception as e:
            logging.warning("[INCIDENT_PRIORITY_FAIL]", extra={"error": str(e)})
            inc["priority_score"] = inc.get("priority_score", 0)
            inc["priority_level"] = inc.get("priority_level", "P4")
            inc["priority_reason"] = inc.get("priority_reason", "unclassified")
            
        save_store(data)
        
        return {
            "incident_hash": incident_hash,
            "is_new": is_new,
            "occurrence_count": inc["count"],
            "existing_issue_number": inc.get("github_issue_number"),
            "severity": severity,
            "last_synced_count": inc.get("last_synced_count", 0),
            "priority_level": inc["priority_level"],
            "priority_score": inc["priority_score"],
            "priority_reason": inc["priority_reason"],
            "error": sitrep.get("error", "unknown"),
            "pipeline": inc["pipeline"],
            "agent": sitrep.get("agent", "unknown"),
            "failure_type": inc["failure_type"],
            "delta_24h": delta_24h,
            "trend": trend,
            "confidence": confidence
        }
    except Exception as e:
        logging.error("[INCIDENT_MANAGER_FATAL]", extra={"error": str(e)})
        return {
            "incident_hash": incident_hash,
            "is_new": True,
            "occurrence_count": 1,
            "existing_issue_number": None,
            "severity": "low",
            "last_synced_count": 0,
            "priority_level": "P4",
            "priority_score": 0,
            "priority_reason": "unclassified",
            "error": sitrep.get("error", "unknown"),
            "pipeline": "unknown",
            "agent": sitrep.get("agent", "unknown"),
            "failure_type": "unknown",
            "delta_24h": 0,
            "trend": "unknown",
            "confidence": "LOW"
        }
