import logging
from workflows.task_manager import TaskManager

def pm_handler(task_id, context):
    local_context = {**context, "execution_mode": "pm"}
    try:
        from workflows.orchestration.behavior_builder import build_behavior_context
        behavior_context = build_behavior_context(local_context)
    except Exception as e:
        behavior_context = {}
        logging.error(f"[BEHAVIOR_BUILD_ERROR] {e}")

    final_context = {**local_context, **behavior_context}
    return TaskManager().execute(task_id, context=final_context)

def code_handler(task_id, context):
    local_context = {**context, "execution_mode": "code"}
    try:
        from workflows.orchestration.behavior_builder import build_behavior_context
        behavior_context = build_behavior_context(local_context)
    except Exception as e:
        behavior_context = {}
        logging.error(f"[BEHAVIOR_BUILD_ERROR] {e}")

    final_context = {**local_context, **behavior_context}
    return TaskManager().execute(task_id, context=final_context)

def review_handler(task_id, context):
    local_context = {**context, "execution_mode": "review"}
    try:
        from workflows.orchestration.behavior_builder import build_behavior_context
        behavior_context = build_behavior_context(local_context)
    except Exception as e:
        behavior_context = {}
        logging.error(f"[BEHAVIOR_BUILD_ERROR] {e}")

    final_context = {**local_context, **behavior_context}
    return TaskManager().execute(task_id, context=final_context)

AGENT_REGISTRY = {
    "pm": pm_handler,
    "code": code_handler,
    "review": review_handler
}

def dispatch_agent_execution(task_id, context: dict):
    role = context.get("bound_role", "pm")
    
    logging.info("[AGENT_DISPATCH_START]", extra={
        "bound_role": role,
        "task_id": task_id
    })
    
    handler = AGENT_REGISTRY.get(role)
    
    if not handler:
        logging.info("[AGENT_DISPATCH_FALLBACK]", extra={
            "requested_role": role,
            "fallback_role": "pm"
        })
        handler = pm_handler
        role = "pm"
        
    result = handler(task_id, context)
    
    logging.info("[AGENT_DISPATCH_SUCCESS]", extra={
        "bound_role": role,
        "task_id": task_id
    })
    
    return result
