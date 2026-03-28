def build_healing_record(stage: dict, failure_info: dict, retry_info: dict, retry_count: int, error: str) -> dict:
    return {
        "stage": stage.get("stage"),
        "agent": stage.get("agent"),
        "action": stage.get("action"),
        "failure_type": failure_info.get("failure_type", "unknown"),
        "retryable": failure_info.get("retryable", False),
        "retry_attempted": retry_count > 0,
        "retry_count": retry_count,
        "reason": failure_info.get("reason", ""),
        "error": error
    }
