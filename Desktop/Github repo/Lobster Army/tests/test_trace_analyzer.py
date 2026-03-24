import pytest
from workflows.analytics.trace_analyzer import validate_trace, analyze_trace, compute_score

# Case A — SUCCESS
SUCCESS_TRACE = {
    "task_id": "1001",
    "final_status": "SUCCESS",
    "self_healing_triggered": False,
    "steps": [
        {"agent": "PMAgent", "status": "success"},
        {"agent": "Feature_Coder", "status": "success"},
        {"agent": "Reviewer", "status": "success"}
    ],
    "tool_actions": [
        {"tool_name": "write_file", "status": "success"}
    ]
}

# Case B — HEALED
HEALED_TRACE = {
    "task_id": "1002",
    "final_status": "SUCCESS",
    "self_healing_triggered": True,
    "steps": [
        {"agent": "PMAgent", "status": "success"},
        {"agent": "Feature_Coder", "status": "success"},
        {"agent": "Reviewer", "status": "failed"},
        {"agent": "AutoFix_Medic", "status": "success"},
        {"agent": "Reviewer", "status": "success"}
    ],
    "tool_actions": [
        {"tool_name": "write_file", "status": "success"}
    ]
}

# Case C — FAILED
FAILED_TRACE = {
    "task_id": "1003",
    "final_status": "FAILED",
    "self_healing_triggered": True,
    "steps": [
        {"agent": "PMAgent", "status": "success"},
        {"agent": "Feature_Coder", "status": "success"},
        {"agent": "Reviewer", "status": "failed"},
        {"agent": "AutoFix_Medic", "status": "failed"}
    ],
    "tool_actions": [
        {"tool_name": "write_file", "status": "failed"},
        {"tool_name": "write_file", "status": "failed"}
    ]
}

# INVALID SCHEMA
INVALID_TRACE = {
    "task_id": "1004",
    # missing steps, final_status
}

def test_validate_trace():
    # Should not raise
    validate_trace(SUCCESS_TRACE)
    
    with pytest.raises(ValueError, match="Missing required key"):
        validate_trace(INVALID_TRACE)
        
    bad_step_trace = {
        "task_id": "1",
        "final_status": "SUCCESS",
        "steps": [{"agent": "A"}] # Missing status
    }
    with pytest.raises(ValueError, match="missing required key: 'status'"):
        validate_trace(bad_step_trace)

def test_analyze_trace_success():
    metrics = analyze_trace(SUCCESS_TRACE)
    
    assert metrics["final_status"] == "SUCCESS"
    assert metrics["total_steps"] == 3
    assert metrics["self_healing_cycles"] == 0
    assert metrics["self_healing_triggered"] is False
    assert metrics["agent_metrics"]["Feature_Coder"]["calls"] == 1
    assert metrics["agent_metrics"]["Feature_Coder"]["failures"] == 0
    assert metrics["tool_metrics"]["write_file"]["calls"] == 1
    assert metrics["tool_metrics"]["write_file"]["failures"] == 0
    
    score = compute_score(metrics)
    assert score == 100.0, "Success without healing/failures should be 100"

def test_analyze_trace_healed():
    metrics = analyze_trace(HEALED_TRACE)
    
    assert metrics["final_status"] == "SUCCESS"
    assert metrics["total_steps"] == 5
    assert metrics["self_healing_cycles"] == 1
    assert metrics["self_healing_triggered"] is True
    assert metrics["agent_metrics"]["Reviewer"]["failures"] == 1
    assert metrics["agent_metrics"]["AutoFix_Medic"]["calls"] == 1
    
    score = compute_score(metrics)
    # 100 - (1 cycle * 15) - 0 tool fails = 85
    assert score == 85.0

def test_analyze_trace_failed():
    metrics = analyze_trace(FAILED_TRACE)
    score = compute_score(metrics)
    
    # 100 - (1 cycle * 15) - (2 tool errors * 20) = 45
    assert score == 45.0
