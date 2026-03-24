import os
import json
import logging

STORE_PATH = ".learning_store.json"

def query_learning_by_failure(failure_type: str) -> dict:
    result = {
        "count": 0,
        "recovered": 0,
        "failed": 0,
        "recovery_rate": 0.0
    }
    
    if not os.path.exists(STORE_PATH):
        return result
        
    try:
        with open(STORE_PATH, "r") as f:
            data = json.load(f)
            
        records = data.get("records", [])
        
        for r in records:
            if r.get("failure_type") == failure_type:
                result["count"] += 1
                if r.get("outcome") == "recovered":
                    result["recovered"] += 1
                elif r.get("outcome") in ["failed", "unknown"]:
                    result["failed"] += 1
                    
        if result["count"] > 0:
            result["recovery_rate"] = round(result["recovered"] / result["count"], 2)
            
        logging.info("[LEARNING_QUERY_RESULT]", extra={
            "failure_type": failure_type,
            "count": result["count"],
            "recovery_rate": result["recovery_rate"]
        })
        
        return result
    except Exception as e:
        logging.error(f"[LEARNING_QUERY_FATAL] {str(e)}")
        return result
