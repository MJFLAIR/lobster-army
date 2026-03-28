import logging

def create_sitrep(task_id: str, failure_info: dict, context: dict) -> dict:
    stage_outputs = context.get("stage_outputs", [])
    
    last_failed_stage = {}
    for stage_out in reversed(stage_outputs):
        if stage_out.get("status") == "failed":
            last_failed_stage = stage_out
            break

    pipeline = (
        context.get("pipeline")
        or context.get("execution_plan", {}).get("pipeline")
        or context.get("router_decision")
        or "unknown"
    )
            
    sitrep = {
        "type": "SITREP",
        "task_id": task_id,
        "risk_level": "high",
        "summary": "Complex failure detected requiring diagnostic review",
        "failure_type": failure_info.get("failure_type", "unknown"),
        "error": failure_info.get("error", "unknown error context"),
        "pipeline": pipeline,
        "agent": last_failed_stage.get("agent", "unknown"),
        "execution_mode": context.get("execution_mode", "dispatcher"),
        "recommended_action": "manual intervention required"
    }
    
    logging.warning("[ESCALATION_TRIGGERED]", extra=sitrep)
    
    return sitrep
