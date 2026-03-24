import json
from workflows.orchestration.task_router import execute_plan
from workflows.orchestration.trace_tracker import build_trace_event, record_trace_event

LOG_PATH = "logs/orchestration_traces.jsonl"

def load_trace_event(incident_id: str, log_path: str = LOG_PATH) -> dict:
    """Reads JSONL file, finds matching incident_id, returns full event."""
    try:
        with open(log_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    event = json.loads(line)
                    if event.get("incident_id") == incident_id:
                        return event
                except json.JSONDecodeError:
                    continue
    except FileNotFoundError:
        pass
    
    raise ValueError(f"Trace event not found for incident_id: {incident_id}")

def build_replay_plan(trace_event: dict) -> dict:
    """
    Constructs a new execution plan containing ONLY failed or skipped steps 
    from the original plan, using the status map from the trace.
    """
    if "plan" not in trace_event or "execution_plan" not in trace_event["plan"]:
        raise ValueError("Invalid trace_event: missing 'plan' structure")
        
    original_plan = trace_event["plan"]["execution_plan"]
    trace = trace_event.get("execution_trace", [])
    
    status_map = {step.get("step_order"): step.get("status") for step in trace}
    
    new_plan_steps = []
    
    for step in original_plan:
        order = step.get("step_order")
        status = status_map.get(order)
        
        if status == "success":
            continue
            
        if status in ["failed", "skipped"] or status is None:
            new_plan_steps.append(step)
            
    return {
        "task_summary": trace_event["plan"].get("task_summary", "Replay run"),
        "complexity": trace_event["plan"].get("complexity", "low"),
        "execution_plan": new_plan_steps
    }

def replay_incident(incident_id: str, agent_registry: dict, log_path: str = LOG_PATH):
    """
    Loads historic trace, builds filtered replay plan, and re-executes via Task Router.
    Automatically persists this logic with parent tracing identifiers downstream natively.
    """
    trace_event = load_trace_event(incident_id, log_path=log_path)
    new_plan = build_replay_plan(trace_event)
    
    if not new_plan["execution_plan"]:
        return []
    
    trace = execute_plan(new_plan, agent_registry)
    
    # Store replay history natively identifying lineage back to parent.
    new_event = build_trace_event(new_plan, trace)
    new_event["parent_incident_id"] = incident_id
    
    record_trace_event(new_event, log_path=log_path)
    
    return trace
