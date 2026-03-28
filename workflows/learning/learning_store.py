import os
import json
import logging

STORE_PATH = ".learning_store.json"
MAX_RECORDS = 10000

def apply_corrupt_reset():
    logging.warning("[LEARNING_STORE_CORRUPTED_RESET]")
    return {"records": []}

def append_learning_records(records: list[dict]) -> None:
    if not records:
        return
        
    try:
        if not os.path.exists(STORE_PATH):
            data = {"records": []}
        else:
            try:
                with open(STORE_PATH, "r") as f:
                    data = json.load(f)
                if not isinstance(data, dict) or "records" not in data:
                    data = apply_corrupt_reset()
            except Exception:
                data = apply_corrupt_reset()
                
        data["records"].extend(records)
        
        if len(data["records"]) > MAX_RECORDS:
            data["records"] = data["records"][-MAX_RECORDS:]
            
            logging.info("[LEARNING_STORE_TRIM]", extra={
                "max_records": MAX_RECORDS,
                "current_size": len(data["records"])
            })
        
        with open(STORE_PATH, "w") as f:
            json.dump(data, f, indent=2)
            
        logging.info("[LEARNING_STORE_APPEND]", extra={"count": len(records)})
    except Exception as e:
        logging.error(f"[LEARNING_STORE_FATAL] {str(e)}")
