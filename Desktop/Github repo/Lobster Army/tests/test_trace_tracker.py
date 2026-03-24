import pytest
import os
import json
import tempfile
from unittest.mock import patch, MagicMock
from workflows.orchestration.trace_tracker import build_trace_event, record_trace_event, run_orchestrated_task

def test_jsonl_append():
    with tempfile.NamedTemporaryFile(delete=False) as tmp:
        log_path = tmp.name
        
    event1 = {"incident_id": "1", "final_status": "SUCCESS"}
    event2 = {"incident_id": "2", "final_status": "CRITICAL_FAILURE"}
    
    record_trace_event(event1, log_path=log_path)
    record_trace_event(event2, log_path=log_path)
    
    with open(log_path, "r", encoding="utf-8") as f:
        lines = f.readlines()
        
    assert len(lines) == 2
    parsed1 = json.loads(lines[0])
    parsed2 = json.loads(lines[1])
    
    assert parsed1["incident_id"] == "1"
    assert parsed2["final_status"] == "CRITICAL_FAILURE"
    
    os.remove(log_path)

def test_trace_event_builder_counts():
    plan = {"task_summary": "Test Plan"}
    trace = [
        {"step_order": 1, "status": "success"},
        {"step_order": 2, "status": "failed"},
        {"step_order": 3, "status": "skipped"}
    ]
    
    event = build_trace_event(plan, trace)
    
    assert event["total_steps"] == 3
    assert event["successful_steps"] == 1
    assert event["failed_steps"] == 1
    assert event["skipped_steps"] == 1
    assert event["final_status"] == "COMPLETED_WITH_ERRORS"
    assert event["task_summary"] == "Test Plan"
    assert "incident_id" in event
    assert "timestamp" in event

def test_final_status_logic():
    plan = {"task_summary": "Test"}
    
    # All success
    trace1 = [
        {"step_order": 1, "status": "success"},
        {"step_order": 2, "status": "success"}
    ]
    ev1 = build_trace_event(plan, trace1)
    assert ev1["final_status"] == "SUCCESS"
    
    # Mixed
    trace2 = [
        {"step_order": 1, "status": "success"},
        {"step_order": 2, "status": "failed"}
    ]
    ev2 = build_trace_event(plan, trace2)
    assert ev2["final_status"] == "COMPLETED_WITH_ERRORS"
    
    # Empty trace edge case
    ev3 = build_trace_event(plan, [])
    assert ev3["final_status"] == "COMPLETED_WITH_ERRORS"

@patch("workflows.orchestration.pm_agent.generate_execution_plan")
def test_critical_failure_logging(mock_generate):
    mock_generate.side_effect = Exception("Total meltdown")
    llm_mock = MagicMock()
    
    with tempfile.NamedTemporaryFile(delete=False) as tmp:
        log_path = tmp.name
        
    event = run_orchestrated_task("Do task", llm_mock, {}, log_path=log_path)
    
    assert event["final_status"] == "CRITICAL_FAILURE"
    assert event["error"] == "Total meltdown"
    assert event["total_steps"] == 0
    
    with open(log_path, "r", encoding="utf-8") as f:
        lines = f.readlines()
        
    assert len(lines) == 1
    parsed = json.loads(lines[0])
    assert parsed["final_status"] == "CRITICAL_FAILURE"
    
    os.remove(log_path)
