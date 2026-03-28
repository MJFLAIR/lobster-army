import pytest
import json
import os
import tempfile
from scripts.analyze_trace_diff import analyze_diff

def test_analyze_diff_recovery():
    with tempfile.NamedTemporaryFile(delete=False) as tmp:
        log_path = tmp.name
        
    original = {
        "incident_id": "orig-123",
        "final_status": "COMPLETED_WITH_ERRORS",
        "timestamp": "2026-03-23T10:00:00Z",
        "execution_trace": [
            {"step_order": 1, "agent": "A", "status": "success"},
            {"step_order": 2, "agent": "B", "status": "failed"},
            {"step_order": 3, "agent": "C", "status": "failed"}
        ]
    }
    
    replay1 = {
        "incident_id": "rep-1",
        "parent_incident_id": "orig-123",
        "final_status": "COMPLETED_WITH_ERRORS",
        "timestamp": "2026-03-23T10:05:00Z",
        "execution_trace": [
            {"step_order": 2, "agent": "B", "status": "success"},
            {"step_order": 3, "agent": "C", "status": "failed"}
        ]
    }
    
    with open(log_path, "w", encoding="utf-8") as f:
        f.write(json.dumps(original) + "\n")
        f.write(json.dumps(replay1) + "\n")
        
    res = analyze_diff("orig-123", print_cli=False, log_path=log_path)
    
    assert res["original_incident_id"] == "orig-123"
    assert res["replay_incident_id"] == "rep-1"
    assert res["recovered_steps"] == 1
    assert res["regressed_steps"] == 0
    assert len(res["step_diffs"]) == 2
    
    assert res["step_diffs"][0]["step_order"] == 2
    assert res["step_diffs"][0]["type"] == "RECOVERED"
    
    assert res["step_diffs"][1]["step_order"] == 3
    assert res["step_diffs"][1]["type"] == "UNCHANGED"
    
    assert res["agent_stats"]["B"]["recovered"] == 1
    
    os.remove(log_path)

def test_multiple_replays():
    with tempfile.NamedTemporaryFile(delete=False) as tmp:
        log_path = tmp.name
        
    original = {
        "incident_id": "orig-100",
        "final_status": "COMPLETED_WITH_ERRORS",
        "timestamp": "2026-03-23T10:00:00Z",
        "execution_trace": [
            {"step_order": 1, "agent": "X", "status": "failed"}
        ]
    }
    
    replay_old = {
        "incident_id": "rep-old",
        "parent_incident_id": "orig-100",
        "timestamp": "2026-03-23T10:05:00Z",
        "execution_trace": [
            {"step_order": 1, "agent": "X", "status": "failed"}
        ]
    }

    replay_new = {
        "incident_id": "rep-new",
        "parent_incident_id": "orig-100",
        "timestamp": "2026-03-23T10:10:00Z",
        "execution_trace": [
            {"step_order": 1, "agent": "X", "status": "success"}
        ]
    }
    
    with open(log_path, "w", encoding="utf-8") as f:
        f.write(json.dumps(original) + "\n")
        f.write(json.dumps(replay_old) + "\n")
        f.write(json.dumps(replay_new) + "\n")
        
    res = analyze_diff("orig-100", print_cli=False, log_path=log_path)
    
    # Needs to match the latest ISO logic correctly.
    assert res["replay_incident_id"] == "rep-new"
    assert res["recovered_steps"] == 1
    
    os.remove(log_path)

def test_missing_incident():
    with pytest.raises(ValueError):
        analyze_diff("nonexistent", print_cli=False, log_path="not_appplicable.jsonl")
