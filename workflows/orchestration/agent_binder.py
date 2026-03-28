import logging

def bind_stage_agent(stage: dict) -> dict:
    stage_agent = stage.get("agent")
    stage_action = stage.get("action")
    stage_index = stage.get("stage")
    
    logging.info("[AGENT_BINDING_START]", extra={
        "stage": stage_index,
        "stage_agent": stage_agent,
        "stage_action": stage_action
    })
    
    try:
        if stage_agent == "pm":
            bound_role = "pm"
        elif stage_agent == "code":
            bound_role = "code"
        elif stage_agent == "review":
            bound_role = "review"
        else:
            bound_role = "pm"
            logging.info("[AGENT_BINDING_FALLBACK]", extra={
                "stage": stage_index,
                "stage_agent": stage_agent,
                "bound_role": bound_role,
            })
            
        binding = {
            "stage_agent": stage_agent,
            "bound_role": bound_role,
            "stage_action": stage_action,
            "binding_source": "deterministic_v1"
        }
        
        logging.info("[AGENT_BINDING_SUCCESS]", extra={
            "stage": stage_index,
            "stage_agent": stage_agent,
            "bound_role": bound_role,
            "stage_action": stage_action
        })
        
        return binding
        
    except Exception as e:
        bound_role = "pm"
        binding = {
            "stage_agent": stage_agent,
            "bound_role": bound_role,
            "stage_action": stage_action,
            "binding_source": "fallback_on_error"
        }
        logging.info("[AGENT_BINDING_FALLBACK]", extra={
            "stage": stage_index,
            "stage_agent": stage_agent,
            "bound_role": bound_role,
            "error": str(e)
        })
        return binding
