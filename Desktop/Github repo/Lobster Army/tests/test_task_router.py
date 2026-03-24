import pytest
from unittest.mock import MagicMock
from workflows.orchestration.task_router import execute_plan

def test_execute_plan_returns_trace(caplog):
    plan = {
        "execution_plan": [
            {"step_order": 1, "assigned_agent": "Terminal_Operator", "instruction": "Step 1"}
        ]
    }
    registry = {"Terminal_Operator": MagicMock()}
    
    trace = execute_plan(plan, registry)
    
    assert isinstance(trace, list)
    assert len(trace) == 1
    assert "step_order" in trace[0]
    assert "agent" in trace[0]
    assert "status" in trace[0]

def test_status_success(caplog):
    plan = {
        "execution_plan": [
            {"step_order": 1, "assigned_agent": "Terminal_Operator", "instruction": "Step 1"}
        ]
    }
    mock_agent = MagicMock()
    registry = {"Terminal_Operator": mock_agent}
    
    trace = execute_plan(plan, registry)
    
    assert trace[0]["status"] == "success"
    mock_agent.assert_called_once_with("Step 1")

def test_status_failed(caplog):
    plan = {
        "execution_plan": [
            {"step_order": 2, "assigned_agent": "Failing_Agent", "instruction": "Crash now"}
        ]
    }
    mock_failing = MagicMock(side_effect=Exception("Crash occurred"))
    registry = {"Failing_Agent": mock_failing}
    
    trace = execute_plan(plan, registry)
    
    assert trace[0]["status"] == "failed"
    assert trace[0]["error"] == "Crash occurred"
    
    logs = caplog.text
    assert "[TASK_ROUTER_STEP_ERROR]" in logs

def test_status_skipped_unknown_agent():
    plan = {
        "execution_plan": [
            {"step_order": 3, "assigned_agent": "Unknown_Agent", "instruction": "Missing"}
        ]
    }
    registry = {}
    
    trace = execute_plan(plan, registry)
    
    assert trace[0]["status"] == "skipped"

def test_status_skipped_invalid_step():
    plan = {
        "execution_plan": [
            {"step_order": None, "assigned_agent": "Terminal_Operator", "instruction": "No order"},
            {"step_order": 2, "assigned_agent": "", "instruction": "No agent"},
            {"step_order": 3, "assigned_agent": "Terminal_Operator", "instruction": ""}
        ]
    }
    registry = {"Terminal_Operator": MagicMock()}
    
    trace = execute_plan(plan, registry)
    
    assert len(trace) == 3
    assert trace[0]["status"] == "skipped"
    assert trace[1]["status"] == "skipped"
    assert trace[2]["status"] == "skipped"

def test_trace_order_preserved():
    plan = {
        "execution_plan": [
            {"step_order": 1, "assigned_agent": "Agent_A", "instruction": "Inst A"},
            {"step_order": 2, "assigned_agent": "Agent_B", "instruction": "Inst B"},
            {"step_order": 3, "assigned_agent": "Agent_A", "instruction": "Inst C"}
        ]
    }
    registry = {
        "Agent_A": MagicMock(),
        "Agent_B": MagicMock()
    }
    
    trace = execute_plan(plan, registry)
    
    assert len(trace) == 3
    assert trace[0]["step_order"] == 1
    assert trace[1]["step_order"] == 2
    assert trace[2]["step_order"] == 3
