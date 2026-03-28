METRICS_SCHEMA = {
    "type": "object",
    "properties": {
        "task_id": {"type": ["string", "integer"]},
        "final_status": {"type": "string", "enum": ["SUCCESS", "FAILED"]},
        "total_steps": {"type": "integer"},
        "self_healing_cycles": {"type": "integer"},
        "self_healing_triggered": {"type": "boolean"},
        "agent_metrics": {
            "type": "object",
            "additionalProperties": {
                "type": "object",
                "properties": {
                    "calls": {"type": "integer"},
                    "failures": {"type": "integer"}
                },
                "required": ["calls", "failures"]
            }
        },
        "tool_metrics": {
            "type": "object",
            "additionalProperties": {
                "type": "object",
                "properties": {
                    "calls": {"type": "integer"},
                    "failures": {"type": "integer"}
                },
                "required": ["calls", "failures"]
            }
        }
    },
    "required": [
        "task_id", 
        "final_status", 
        "total_steps", 
        "self_healing_cycles", 
        "self_healing_triggered", 
        "agent_metrics", 
        "tool_metrics"
    ]
}
