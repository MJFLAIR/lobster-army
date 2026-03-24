import pytest
from unittest.mock import MagicMock
from workflows.agents.feature_coder import FeatureCoderAgent

def test_feature_coder_schema():
    # Test 3 — Feature_Coder Schema
    llm = MagicMock()
    # Mock Feature_Coder response
    llm.complete.return_value = '{"status": "success", "target_file": "src/main.py", "code": "print(1)"}'
    
    agent = FeatureCoderAgent(llm)
    result = agent.handle_feature_coder("write code")
    
    assert result["status"] == "success"
    assert "target_file" in result
    assert "code" in result
    assert "file_path" not in result
    assert "content" not in result

def test_feature_coder_rejects_file_path():
    llm = MagicMock()
    llm.complete.return_value = '{"status": "success", "file_path": "src/main.py", "code": "print(1)"}'
    
    agent = FeatureCoderAgent(llm)
    result = agent.handle_feature_coder("write code")
    
    assert result["status"] == "failed"
    assert "missing target_file or code" in result["error"]

def test_feature_coder_rejects_unrelated_keys():
    llm = MagicMock()
    llm.complete.return_value = '{"status": "success", "target_file": "a", "code": "b", "content": "c"}'
    
    agent = FeatureCoderAgent(llm)
    result = agent.handle_feature_coder("write code")
    
    assert result["status"] == "failed"
    assert "returned file_path or content" in result["error"]
