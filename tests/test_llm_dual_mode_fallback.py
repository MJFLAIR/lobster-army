import os
import pytest
from unittest.mock import patch
import json

# Force environment for this test explicitly


from tools.llm_client import LLMClient

def test_llm_dual_mode_fallback_api_error():
    os.environ["LLM_MODE"] = "real"
    client = LLMClient(provider="openai", model="gpt-4o-mini")
    
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
    client = LLMClient(provider="openai", model="gpt-4o-mini")
    
    # 🛡️ 戰術升級：拆除會漏水打到真實 API 的舊版 DummyClient
    # 我們直接在 real_adapter 的邊界佈下防線，精準模擬 JSON 解析失敗時的狀態
    with patch('workflows.storage.db.DB.emit_event'), \
         patch.object(client.real_adapter, 'complete', side_effect=ValueError("No JSON object found")):
        
        # 當 complete 拋出 ValueError 時，LLMClient 會安全接住並觸發 fallback
        result = client.complete("Fix the bug", system_prompt="You are a python engineer")
    
    assert "content" in result
    
    # 這裡解析的一定是 Mock Adapter 安全回傳的假 JSON 字串，絕對不會再炸了
    content_dict = json.loads(result["content"])
    
    assert "diff" in content_dict, "Should successfully fallback and return 'diff'"
    assert content_dict["diff"] == "mock-diff-content"