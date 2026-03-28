import json
import os
from uuid import uuid4
from datetime import datetime, timezone

LOG_PATH = "logs/orchestration_traces.jsonl"

def build_trace_event(plan: dict, trace: list) -> dict:
    """
    Computes step counts and terminal status of an execution trace.
    Returns the standard event schema.
    """
    total_steps = len(trace)
    successful_steps = sum(1 for t in trace if t.get("status") == "success")
    failed_steps = sum(1 for t in trace if t.get("status") == "failed")
    skipped_steps = sum(1 for t in trace if t.get("status") == "skipped")
    
    if total_steps > 0 and successful_steps == total_steps:
        final_status = "SUCCESS"
    else:
        final_status = "COMPLETED_WITH_ERRORS"
        
    return {
        "incident_id": str(uuid4()),
        "task_summary": plan.get("task_summary", "unknown"),
        "total_steps": total_steps,
        "successful_steps": successful_steps,
        "failed_steps": failed_steps,
        "skipped_steps": skipped_steps,
        "final_status": final_status,
        "plan": plan,
        "execution_trace": trace,
        "timestamp": datetime.now(timezone.utc).isoformat()
    }

def record_trace_event(event: dict, log_path: str = LOG_PATH):
    """
    Appends the trace event to the JSONL log file securely.
    Ensures flush capability deterministic behavior.
    """
    os.makedirs(os.path.dirname(log_path), exist_ok=True)
    with open(log_path, "a", encoding="utf-8") as f:
        json.dump(event, f, ensure_ascii=False)
        f.write("\n")
        f.flush()

def run_orchestrated_task(task_description: str, llm_provider, agent_registry: dict, log_path: str = LOG_PATH) -> dict:
    """
    The main execution wrapper that safely calls the PM Agent, the Task Router,
    builds the trace tracker event, and persists it regardless of execution halts.
    """
    from workflows.orchestration.pm_agent import generate_execution_plan
    from workflows.orchestration.task_router import execute_plan
    
    event = None
    try:
        plan = generate_execution_plan(task_description, llm_provider)
        trace = execute_plan(plan, agent_registry)
        event = build_trace_event(plan, trace)
    except Exception as e:
        event = {
            "incident_id": str(uuid4()),
            "task_summary": "unknown",
            "total_steps": 0,
            "successful_steps": 0,
            "failed_steps": 0,
            "skipped_steps": 0,
            "final_status": "CRITICAL_FAILURE",
            "execution_trace": [],
            "error": str(e),
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
    finally:
        if event:
            record_trace_event(event, log_path=log_path)
            
    return event
