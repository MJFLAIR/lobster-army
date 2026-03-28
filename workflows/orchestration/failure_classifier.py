def classify_failure(error: Exception | str) -> dict:
    error_str = str(error).lower()
    
    if any(k in error_str for k in ["timeout", "connection", "network", "unavailable"]):
        return {"failure_type": "network", "retryable": True, "reason": "transient connectivity issue"}
    if any(k in error_str for k in ["rate limit", "too many requests", "429"]):
        return {"failure_type": "rate_limit", "retryable": True, "reason": "API rate limit reached"}
    if any(k in error_str for k in ["invalid", "schema", "validation", "missing required"]):
        return {"failure_type": "validation", "retryable": False, "reason": "data validation failure"}
    if any(k in error_str for k in ["unauthorized", "forbidden", "permission", "401", "403"]):
        return {"failure_type": "auth", "retryable": False, "reason": "authentication or permission error"}
        
    return {"failure_type": "unknown", "retryable": False, "reason": "unclassified failure"}
