import pytest
from unittest.mock import MagicMock
from workflows.agents.autofix_medic import AutoFixMedicAgent

def test_autofix_medic_schema():
    # Test 6 — AutoFix_Medic Schema
    llm = MagicMock()
    llm.complete.return_value = '{"status": "success", "target_file": "src/main.py", "code": "clean code", "notes": "fixed syntax error"}'
    
    agent = AutoFixMedicAgent(llm)
    result = agent.handle_autofix_medic("Fix the crash")
    
    assert result["status"] == "success"
    assert "target_file" in result
    assert "code" in result
    assert "notes" in result
    assert "file_path" not in result
    assert "content" not in result

def test_autofix_medic_rejects_file_path():
    llm = MagicMock()
    llm.complete.return_value = '{"status": "success", "file_path": "src/main.py", "code": "clean code"}'
    
    agent = AutoFixMedicAgent(llm)
    result = agent.handle_autofix_medic("Fix")
    
    assert result["status"] == "failed"
    assert "missing target_file or code" in result["error"]
