import pytest
import json
import os
import tempfile
from unittest.mock import patch, MagicMock

from workflows.orchestration.replay_engine import (
    load_trace_event,
    build_replay_plan,
    replay_incident
)

def test_load_trace_event_not_found():
    with tempfile.NamedTemporaryFile(delete=False) as tmp:
        log_path = tmp.name
        
    # Write a dummy entry
    with open(log_path, "w", encoding="utf-8") as f:
        f.write(json.dumps({"incident_id": "123"}) + "\\n")
        
    with pytest.raises(ValueError, match="Trace event not found"):
        load_trace_event("456", log_path=log_path)
        
    os.remove(log_path)
    
def test_build_replay_plan_filters_correctly():
    trace_event = {
        "incident_id": "uuid-123",
        "plan": {
            "task_summary": "Original Task",
            "complexity": "medium",
            "execution_plan": [
                {"step_order": 1, "assigned_agent": "A", "instruction": "Inst 1"},
                {"step_order": 2, "assigned_agent": "B", "instruction": "Inst 2"},
                {"step_order": 3, "assigned_agent": "C", "instruction": "Inst 3"},
                {"step_order": 4, "assigned_agent": "D", "instruction": "Inst 4"}
            ]
        },
        "execution_trace": [
            {"step_order": 1, "agent": "A", "status": "success"},
            {"step_order": 2, "agent": "B", "status": "failed"},
            {"step_order": 3, "agent": "C", "status": "skipped"}
            # step 4 didn't execute yet
        ]
    }
    
    new_plan = build_replay_plan(trace_event)
    steps = new_plan["execution_plan"]
    
    assert len(steps) == 3
    # 2 (failed), 3 (skipped), 4 (none) should be kept. 1 (success) removed.
    assert steps[0]["step_order"] == 2
    assert steps[1]["step_order"] == 3
    assert steps[2]["step_order"] == 4

def test_replay_uses_original_instruction():
    trace_event = {
        "incident_id": "uuid-1",
        "plan": {
            "task_summary": "Preserve",
            "complexity": "low",
            "execution_plan": [
                {"step_order": 1, "assigned_agent": "A", "instruction": "Must Keep This Exact String"}
            ]
        },
        "execution_trace": [
            {"step_order": 1, "agent": "A", "status": "failed"}
        ]
    }
    
    new_plan = build_replay_plan(trace_event)
    assert new_plan["execution_plan"][0]["instruction"] == "Must Keep This Exact String"

@patch("workflows.orchestration.replay_engine.record_trace_event")
@patch("workflows.orchestration.replay_engine.build_trace_event")
@patch("workflows.orchestration.replay_engine.execute_plan")
@patch("workflows.orchestration.replay_engine.load_trace_event")
def test_replay_execution_flow(mock_load, mock_execute, mock_build, mock_record):
    trace_event = {
        "incident_id": "uuid-000",
        "plan": {
            "task_summary": "Flow",
            "complexity": "low",
            "execution_plan": [
                {"step_order": 1, "assigned_agent": "A", "instruction": "I1"}
            ]
        },
        "execution_trace": [
            {"step_order": 1, "agent": "A", "status": "failed"}
        ]
    }
    mock_load.return_value = trace_event
    mock_execute.return_value = [{"step_order": 1, "status": "success"}]
    mock_build.return_value = {"incident_id": "rep-uuid", "final_status": "SUCCESS"}
    
    registry = {"A": MagicMock()}
    
    result = replay_incident("uuid-000", registry)
    
    # Assert load called
    mock_load.assert_called_once_with("uuid-000", log_path="logs/orchestration_traces.jsonl")
    
    # Assert execute_plan called with FILTERED plan
    args, kwargs = mock_execute.call_args
    called_plan = args[0]
    called_registry = args[1]
    
    assert called_plan["execution_plan"][0]["step_order"] == 1
    assert called_registry == registry
    assert result == [{"step_order": 1, "status": "success"}]
    
    # Assert parent_incident_id is attached and recorded
    mock_build.assert_called_once()
    recorded_event = mock_record.call_args[0][0]
    assert recorded_event["parent_incident_id"] == "uuid-000"
