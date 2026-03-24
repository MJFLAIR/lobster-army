import os
import json
import logging

STORE_PATH = ".learning_store.json"

def get_routing_hint(pipeline: str) -> dict:
    if pipeline != "review_only":
        return {"override_pipeline": None, "reason": "no rule defined"}
        
    if not os.path.exists(STORE_PATH):
        return {"override_pipeline": None, "reason": "no data"}
        
    try:
        with open(STORE_PATH, "r") as f:
            data = json.load(f)
            
        records = data.get("records", [])
        
        count = 0
        failed = 0
        for r in records:
            if r.get("pipeline") == pipeline:
                count += 1
                if r.get("outcome") in ["failed", "unknown"]:
                    failed += 1
                    
        if count >= 5:
            failure_rate = failed / count
            if failure_rate > 0.7:
                return {
                    "override_pipeline": "planning_pipeline",
                    "reason": f"high failure rate ({failure_rate:.2f}) for {pipeline}"
                }
                
        return {"override_pipeline": None, "reason": "stable failure rate"}
    except Exception as e:
        logging.warning("[LEARNING_ADAPTER_FAIL]", extra={"error": str(e)})
        return {"override_pipeline": None, "reason": "evaluation failed"}
