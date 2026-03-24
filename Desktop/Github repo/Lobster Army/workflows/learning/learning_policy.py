import logging

def get_retry_adjustment(failure_type: str) -> dict:
    try:
        from workflows.learning.learning_query import query_learning_by_failure
        stats = query_learning_by_failure(failure_type)
        
        count = stats.get("count", 0)
        if count < 5:
            return {"override_retry": None, "reason": "insufficient data"}
            
        rate = stats.get("recovery_rate", 0.0)
        if rate < 0.2:
            return {"override_retry": False, "reason": f"low recovery rate ({rate})"}
        elif rate > 0.8:
            return {"override_retry": True, "reason": f"high recovery rate ({rate})"}
            
        return {"override_retry": None, "reason": f"average recovery rate ({rate})"}
    except Exception as e:
        logging.warning("[LEARNING_POLICY_FAIL]", extra={"error": str(e)})
        return {"override_retry": None, "reason": "policy evaluation failed"}
