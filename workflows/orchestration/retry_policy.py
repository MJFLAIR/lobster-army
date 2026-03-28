import logging

def should_retry(stage: dict, failure_info: dict, retry_count: int) -> dict:
    retryable = failure_info.get("retryable", False)
    allow_retry = retryable and retry_count < 1

    try:
        from workflows.learning.learning_policy import get_retry_adjustment
        adjustment = get_retry_adjustment(failure_info.get("failure_type", "unknown"))
        if adjustment.get("override_retry") is not None:
            allow_retry = adjustment["override_retry"] and retry_count < 1
            logging.info("[LEARNING_RETRY_ADJUSTMENT]", extra={
                "failure_type": failure_info.get("failure_type", "unknown"),
                "override": adjustment["override_retry"],
                "reason": adjustment["reason"]
            })
    except Exception as e:
        logging.warning("[RETRY_POLICY_LEARNING_FAIL]", extra={"error": str(e)})

    if allow_retry:
        reason = "retry allowed"
    elif retryable:
        reason = "max retries reached"
    else:
        reason = "non-retryable error"

    return {
        "allow_retry": allow_retry,
        "max_retries": 1,
        "reason": reason
    }
