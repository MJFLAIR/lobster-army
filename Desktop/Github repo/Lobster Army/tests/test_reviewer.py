import pytest
from unittest.mock import MagicMock
from workflows.agents.reviewer import ReviewerAgent # or equivalent based on my implementation

def test_reviewer_pass():
    # Test 4 — Reviewer Pass
    llm = MagicMock()
    llm.complete.return_value = '{"status": "success", "notes": "LGTM"}'
    
    agent = ReviewerAgent(llm)
    result = agent.handle_reviewer("Review this code")
    
    assert result["status"] == "success"
    assert "target_file" not in result
    assert "code" not in result
    assert result.get("notes") == "LGTM"

def test_reviewer_fail():
    # Test 5 — Reviewer Fail
    llm = MagicMock()
    llm.complete.return_value = '{"status": "failed", "error": "Missing input validation"}'
    
    agent = ReviewerAgent(llm)
    result = agent.handle_reviewer("Review this code")
    
    assert result["status"] == "failed"
    assert "error" in result
    assert result["error"] == "Missing input validation"
    assert "target_file" not in result
    assert "code" not in result

def test_reviewer_rejects_writing_code():
    llm = MagicMock()
    llm.complete.return_value = '{"status": "success", "target_file": "a.py", "code": "clean code"}'
    
    agent = ReviewerAgent(llm)
    result = agent.handle_reviewer("Review this code")
    
    assert result["status"] == "failed"
    assert "returned target_file or code" in result["error"]
