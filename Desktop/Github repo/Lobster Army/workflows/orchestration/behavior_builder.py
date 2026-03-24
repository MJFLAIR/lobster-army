import logging
from workflows.orchestration.behavior_registry import BEHAVIOR_REGISTRY

def build_behavior_context(context: dict) -> dict:
    mode = context.get("execution_mode", "pm")
    config = BEHAVIOR_REGISTRY.get(mode, BEHAVIOR_REGISTRY["pm"])
    
    logging.info("[BEHAVIOR_CONTEXT_BUILD]", extra={
        "execution_mode": mode,
        "role": config.get("role"),
        "style": config.get("style")
    })
    
    behavior_context = {
        "behavior_role": config.get("role"),
        "behavior_style": config.get("style"),
        "behavior_instruction": config.get("instruction")
    }
    
    logging.info("[BEHAVIOR_CONTEXT_APPLIED]", extra={
        "execution_mode": mode,
        "role": config.get("role")
    })
    
    return behavior_context
