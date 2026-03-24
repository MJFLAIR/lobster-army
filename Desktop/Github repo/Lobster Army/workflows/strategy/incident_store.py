import os
import json
import logging
from datetime import datetime, timezone

STORE_PATH = ".incident_store.json"
MAX_INCIDENTS = 5000

def load_store() -> dict:
    if not os.path.exists(STORE_PATH):
        return {"incidents": {}}
        
    try:
        with open(STORE_PATH, "r") as f:
            data = json.load(f)
            
        if not isinstance(data, dict) or "incidents" not in data:
            logging.warning("[INCIDENT_STORE_CORRUPTED] Resetting store")
            return {"incidents": {}}
            
        for k, v in data["incidents"].items():
            v.setdefault("last_seen_interval_sec", 0)
            v.setdefault("priority_score", 0)
            v.setdefault("priority_level", "P4")
            v.setdefault("priority_reason", "unclassified")
            
        return data
    except Exception as e:
        logging.warning("[INCIDENT_STORE_FATAL] Resetting store", extra={"error": str(e)})
        return {"incidents": {}}

def save_store(data: dict) -> None:
    try:
        incidents = data.get("incidents", {})
        
        if len(incidents) > MAX_INCIDENTS:
            sorted_incidents = sorted(
                incidents.items(), 
                key=lambda x: x[1].get("last_seen", ""), 
                reverse=True
            )
            data["incidents"] = dict(sorted_incidents[:MAX_INCIDENTS])
            logging.info("[INCIDENT_STORE_TRIM]", extra={"trimmed_to": MAX_INCIDENTS})
            
        with open(STORE_PATH, "w") as f:
            json.dump(data, f, indent=2)
    except Exception as e:
        logging.error("[INCIDENT_STORE_SAVE_FATAL]", extra={"error": str(e)})

def get_incident(incident_hash: str) -> dict:
    data = load_store()
    return data.get("incidents", {}).get(incident_hash)
