import logging
from datetime import datetime, timezone

def extract_learning_records(task: dict) -> list[dict]:
    logging.info("[LEARNING_EXTRACTION_START]")
    try:
        meta = task.get("meta", {})
        healing_log = meta.get("healing_log", [])
        
        if not healing_log:
            return []
            
        pipeline_name = (
            meta.get("execution_plan", {}).get("pipeline")
            or meta.get("plan", {}).get("pipeline")
            or meta.get("pipeline")
            or "unknown"
        )
        
        execution_context = meta.get("execution_context", {})
        execution_mode = execution_context.get("execution_mode", "unknown")
        
        records = []
        for row in healing_log:
            record = {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "pipeline": pipeline_name,
                "stage": row.get("stage"),
                "agent": row.get("agent"),
                "action": row.get("action"),
                "failure_type": row.get("failure_type", "unknown"),
                "retryable": row.get("retryable", False),
                "retry_attempted": row.get("retry_attempted", False),
                "retry_count": row.get("retry_count", 0),
                "outcome": row.get("outcome", "unknown"),
                "error": row.get("error", ""),
                "execution_mode": execution_mode
            }
            records.append(record)
            logging.info("[LEARNING_RECORD_CREATED]", extra={"stage": record["stage"], "failure_type": record["failure_type"]})
            
        return records
    except Exception as e:
        logging.error(f"[LEARNING_EXTRACTION_FATAL] {str(e)}")
        return []
