import os
import pytest
from unittest.mock import patch
import json

# Force environment for this test explicitly


from tools.llm_client import LLMClient

def test_llm_dual_mode_fallback_api_error():
    os.environ["LLM_MODE"] = "real"
    client = LLMClient()
    
    assert client.mode == "real", "Mode should be initialized as real based on env var"
    assert client.real_adapter is not None, "Real adapter should be instantiated"

    with patch('workflows.storage.db.DB.emit_event'), patch.object(client.real_adapter, 'complete', side_effect=ValueError("Simulated 429 Too Many Requests")):
        result = client.complete("Write a python script", system_prompt="You are a python engineer")
        
        assert "content" in result
        assert "usage" in result
        
        content_dict = json.loads(result["content"])
        
        assert "diff" in content_dict, "Fallback should return valid mock schema ('diff' for code agent)"
        assert content_dict["diff"] == "mock-diff-content"

def test_llm_dual_mode_fallback_json_extract_error():
    """Verify that if extract_json fails, we still fallback safely to mock"""
    os.environ["LLM_MODE"] = "real"
    client = LLMClient()
    
    # We bypass openai check by providing a dummy client implementation
    class DummyMessage:
        content = "Not valid JSON output here"
    class DummyChoice:
        message = DummyMessage()
    class DummyUsage:
        total_tokens = 50
    class DummyResponse:
        choices = [DummyChoice()]
        usage = DummyUsage()
    
    class DummyCompletions:
        def create(self, **kwargs):
            return DummyResponse()
            
    class DummyChat:
        completions = DummyCompletions()
        
    class DummyClient:
        chat = DummyChat()
    
    # Mock the internal object directly
    client.real_adapter.client = DummyClient()
    
    # It will hit DummyResponse, which has content="Not valid JSON output here"
    # extract_json will RAISE ValueError("No JSON object found")
    # which will be caught in complete() and trigger fallback!
    with patch('workflows.storage.db.DB.emit_event'):
        result = client.complete("Fix the bug", system_prompt="You are a python engineer")
    
    assert "content" in result
    content_dict = json.loads(result["content"])
    
    assert "diff" in content_dict, "Should successfully fallback and return 'diff'"
    assert content_dict["diff"] == "mock-diff-content"
